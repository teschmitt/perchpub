import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select

from app.api.deps import (
    CurrentStation,
    CurrentUser,
    SessionDep,
    audit_provenance,
    presented_client_cert,
)
from app.ca.step_ca_client import sign_device_csr
from app.core.config import settings
from app.core.quotas import enforce_active_session_quota, enforce_station_quota
from app.core.ratelimit import (
    enforce_enrollment_confirm_rate,
    enforce_enrollment_create_rate,
    enforce_enrollment_renew_rate,
)
from app.models.enrollment import (
    EnrollmentAudit,
    EnrollmentAuditEvent,
    EnrollmentRequest,
    EnrollmentResponse,
    EnrollmentSession,
    EnrollmentSessionCreate,
    EnrollmentToken,
    RenewalRequest,
    RenewalResponse,
)
from app.models.station import Station
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_ENROLLMENT_ATTEMPTS = 3

# TODO: use a real secrets manager instead of env files like an amateur
HMAC_KEY_ID = "2025-12-rot1"
HMAC_KEY = bytes.fromhex(settings.ENROLLMENT_HMAC_KEY_HEX)

router = APIRouter(prefix="/enrollment", tags=["enrollment"])


def generate_token(auth_token: str) -> bytes:
    return hmac.new(HMAC_KEY, auth_token.encode("utf-8"), hashlib.sha256).digest()


def _csr_spki_sha256_hex(
    cert: x509.Certificate | x509.CertificateSigningRequest,
) -> str:
    """SHA-256(SPKI, DER) of a cert or CSR's public key.

    Works on either because step-ca copies the CSR's public key verbatim into
    the signed leaf, so ``SPKI(csr) == SPKI(leaf)`` — letting the station pin be
    derived from the CSR before signing.
    """
    spki_der = cert.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(spki_der).hexdigest()


@lru_cache(maxsize=1)
def _device_ca_root_pem() -> str:
    """Read the device-CA root cert PEM once.

    Read-on-first-use (lazy) so a missing/placeholder cert path fails loudly
    only when enrollment is exercised, not at import.
    """
    return Path(settings.STEP_CA_ROOT_CERT_PATH).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _device_ca_pin() -> str:
    """Lowercase-hex SHA-256(SPKI, DER) of the device-CA root certificate.

    This is the QR's out-of-band integrity commitment: a station verifies the
    ``ca_chain_pem`` returned by ``/confirm`` against it. Reuses the same
    SPKI-SHA256 construction used for ``Station.spki_sha256``.
    """
    root = x509.load_pem_x509_certificate(_device_ca_root_pem().encode("utf-8"))
    return _csr_spki_sha256_hex(root)


def _append_root_to_chain(intermediate_pem: str) -> str:
    """Return the full device-CA chain: issuing intermediate first, root last.

    step-ca's sign response carries the issuing intermediate; the station needs
    the root to build ``leaf -> intermediate -> root`` and check it against the
    pinned root. Both the pin and this appended root read from the same file
    (``STEP_CA_ROOT_CERT_PATH``), so they are DER-equal by construction.

    An empty intermediate (step-ca returned no chain) fails loudly with a 502
    rather than silently degrading to a root-only chain a station cannot use.
    """
    intermediate = intermediate_pem.strip()
    if not intermediate:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="certificate issuance failed",
        )
    return intermediate + "\n" + _device_ca_root_pem().strip() + "\n"


@router.post(
    "/create",
    response_model=EnrollmentSession,
    dependencies=[Depends(enforce_enrollment_create_rate)],
)
def create_enrollment_session(
    session: SessionDep,
    request: Request,
    current_user: CurrentUser,
    create_in: EnrollmentSessionCreate,
) -> EnrollmentSession:
    # Per-user active-session quota (design D2), enforced before any write and
    # race-safe. The owned-station ceiling is NOT checked here: it is enforced
    # where a new station is actually created (enroll_station / POST /station/),
    # so re-enrolling to refresh an existing station's cert is never blocked.
    # Superusers are exempt.
    enforce_active_session_quota(
        session, current_user.id, is_superuser=current_user.is_superuser
    )

    session_id = uuid.uuid4()
    auth_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.ENROLLMENT_TTL_SECONDS
    )
    # Read/hash the device-CA root BEFORE any DB write, so a missing/placeholder
    # root fails loudly here without committing an orphan enrollment token.
    ca_pin = _device_ca_pin()

    enrollment_token = EnrollmentToken(
        session_id=session_id,
        expires_at=expires_at,
        claimed=False,
        token_tag=generate_token(auth_token),
        key_id=HMAC_KEY_ID,
        owner_id=current_user.id,
        latitude=create_in.latitude,
        longitude=create_in.longitude,
        is_private=create_in.is_private,
    )

    session.add(enrollment_token)
    session.add(
        EnrollmentAudit(
            event=EnrollmentAuditEvent.session_created,
            session_id=session_id,
            actor_user_id=current_user.id,
            **audit_provenance(request),
        )
    )
    session.commit()

    return EnrollmentSession(
        session_id=session_id,
        auth_token=auth_token,
        expires_at=expires_at,
        ca_pin=ca_pin,
        # The public station-facing enrollment origin (`:443` edge), emitted so a
        # station enrolls with zero pre-configuration. Non-secret; never redacted.
        perchpub_url=settings.STATION_EDGE_URL,
    )


@router.post(
    "/confirm/{session_id}",
    response_model=EnrollmentResponse,
    dependencies=[Depends(enforce_enrollment_confirm_rate)],
)
async def enroll_station(
    session: SessionDep,
    request: Request,
    session_id: uuid.UUID,
    enrollment_req: EnrollmentRequest,
) -> EnrollmentResponse:
    enrollment_session = session.get(EnrollmentToken, session_id)
    if enrollment_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown enrollment session",
        )

    if enrollment_session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session expired."
        )

    if enrollment_session.attempts >= MAX_ENROLLMENT_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Too many retries."
        )

    if enrollment_session.claimed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Already enrolled."
        )

    enrollment_session.attempts += 1

    recv_token_tag = generate_token(enrollment_req.auth_token)
    verified = hmac.compare_digest(recv_token_tag, enrollment_session.token_tag)
    if not verified:
        session.add(enrollment_session)
        session.commit()
        session.refresh(enrollment_session)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid auth token."
        )

    # Reject malformed CSRs with a generic 400 — do not leak parser detail.
    try:
        csr = x509.load_pem_x509_csr(enrollment_req.csr_pem.encode("utf-8"))
    except ValueError:
        session.add(enrollment_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid CSR"
        )

    # Resolve identity and the existing-station decision BEFORE signing. The pin
    # is SHA-256(SPKI) of the CSR's public key, which step-ca copies verbatim
    # into the leaf (CSR pin == leaf pin, get_current_station resolves SPKI-
    # uniquely). Doing the reject checks here means a re-enrollment that cannot
    # succeed (revoked pin, cross-owner, missing coords) is refused without a
    # step-ca signing round-trip or a throwaway cert, and — like the other
    # failure paths — charges the attempt so the ≤3 cap bounds retries (D1).
    spki_pin = _csr_spki_sha256_hex(csr)
    existing = session.exec(
        select(Station).where(Station.spki_sha256 == spki_pin)
    ).first()
    if existing is not None:
        # A revoked pin is not reusable (D1): re-enrolling the revoked key does
        # not reactivate the station. Recovery is a fresh device key -> new SPKI
        # -> new Station. Refuse regardless of owner.
        if existing.revoked_at is not None:
            session.add(enrollment_session)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="device certificate has been revoked",
            )
        # Refuse to silently move a device between accounts. Re-enrollment
        # refreshes the cert for the *same* owner; cross-owner transfer is not
        # a silent side effect of re-enrolling.
        if existing.owner_id != enrollment_session.owner_id:
            session.add(enrollment_session)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="device already enrolled to another account",
            )
    else:
        # New station. Coordinates are required (a refresh keeps the existing
        # station's location), and the owned-station ceiling applies here — where
        # a station is actually created — not at /create, so refresh is exempt.
        # Both checks run BEFORE signing, so a rejected new enrollment never
        # mints a throwaway cert (D1/D2).
        if enrollment_session.latitude is None or enrollment_session.longitude is None:
            session.add(enrollment_session)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="enrollment session is missing coordinates",
            )
        owner = session.get(User, enrollment_session.owner_id)
        enforce_station_quota(
            session,
            enrollment_session.owner_id,
            is_superuser=owner.is_superuser if owner is not None else False,
        )

    # Sign with step-ca. Map any signing failure to a generic 502 — do not
    # leak step-ca exception messages to the client.
    try:
        signed = await sign_device_csr(enrollment_req.csr_pem)
    except (httpx.HTTPError, ValueError):
        session.add(enrollment_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="certificate issuance failed",
        )

    # Build the full response chain (intermediate + root) BEFORE mutating state,
    # so a missing root / empty intermediate fails loudly with the session left
    # unclaimed and retryable — no orphaned, un-redeemable Station.
    ca_chain_pem = _append_root_to_chain(signed.ca_chain_pem)

    if existing is not None:
        station = existing
    else:
        station = Station(
            latitude=enrollment_session.latitude,
            longitude=enrollment_session.longitude,
            owner_id=enrollment_session.owner_id,
            spki_sha256=spki_pin,
            is_private=enrollment_session.is_private,
        )
        session.add(station)
        session.flush()

    enrollment_session.claimed = True
    enrollment_session.station_id = station.id
    session.add(enrollment_session)
    session.add(
        EnrollmentAudit(
            event=EnrollmentAuditEvent.confirm_succeeded,
            session_id=session_id,
            actor_user_id=enrollment_session.owner_id,
            spki_sha256=station.spki_sha256,
            station_id=station.id,
            **audit_provenance(request),
        )
    )
    session.commit()
    session.refresh(station)

    return EnrollmentResponse(
        success=True,
        certificate_pem=signed.certificate_pem,
        ca_chain_pem=ca_chain_pem,
        station_id=station.id,
    )


@router.post(
    "/renew",
    response_model=RenewalResponse,
    dependencies=[Depends(enforce_enrollment_renew_rate)],
)
async def renew_station_certificate(
    session: SessionDep,
    request: Request,
    station: CurrentStation,
    renewal_req: RenewalRequest,
) -> RenewalResponse:
    """Unattended certificate renewal over mTLS (perchstation contract §4).

    The mTLS sibling of /confirm: same step-ca issuance, no session — the
    caller is identified ONLY by the presented client certificate
    (``CurrentStation``, SPKI-pin resolution; unknown/revoked/absent all
    collapse to its generic 401). The CSR must be over the station's EXISTING
    key: a new-SPKI CSR is not renewal but re-enrollment, which stays
    operator-gated. The recorded pin is never updated here, and the appended
    root is the same enrollment root the station pinned at setup — this
    endpoint can never rotate a key or migrate a trust anchor.
    """
    # 422 for an unusable CSR, per the renewal contract (any 4xx is terminal
    # for the station's attempt). Proof of possession: the CSR self-signature
    # must verify — /confirm delegates that to step-ca, but here the CSR's key
    # feeds the SPKI equality check below, so prove possession first.
    try:
        csr = x509.load_pem_x509_csr(renewal_req.csr_pem.encode("utf-8"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid CSR"
        )
    if not csr.is_signature_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid CSR"
        )

    # SPKI equality — THE check that makes unattended renewal safe. Both sides
    # are SHA-256(SPKI DER): Station.spki_sha256 was recorded from the leaf at
    # enrollment and step-ca copies the CSR's key verbatim into the new leaf,
    # so equal pins == same key == the station renews only its own cert.
    if _csr_spki_sha256_hex(csr) != station.spki_sha256:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSR public key does not match the presented client certificate",
        )

    # Sign via the same step-ca path as /confirm, with the same generic 502 on
    # failure (transient for the station; it retries with bounded backoff).
    try:
        signed = await sign_device_csr(renewal_req.csr_pem)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="certificate issuance failed",
        )

    ca_chain_pem = _append_root_to_chain(signed.ca_chain_pem)

    # The audit line needs the new leaf's serial/not_after; a leaf that does
    # not parse is a failed issuance (502, retryable), not a 200 the station's
    # validation would reject anyway.
    try:
        new_leaf = x509.load_pem_x509_certificate(
            (signed.certificate_pem or "").encode("utf-8")
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="certificate issuance failed",
        )

    session.add(
        EnrollmentAudit(
            event=EnrollmentAuditEvent.renewal_succeeded,
            station_id=station.id,
            spki_sha256=station.spki_sha256,
            **audit_provenance(request),
        )
    )
    session.commit()

    # One line per issuance; serials in hex. Never log the CSR or key material.
    presented = presented_client_cert(request)
    logger.info(
        "station certificate renewed: station_id=%s spki_sha256=%s "
        "old_serial=%s new_serial=%x not_after=%s",
        station.id,
        station.spki_sha256,
        f"{presented.serial_number:x}" if presented is not None else "unavailable",
        new_leaf.serial_number,
        new_leaf.not_valid_after_utc.isoformat(),
    )

    return RenewalResponse(
        certificate_pem=signed.certificate_pem,
        ca_chain_pem=ca_chain_pem,
    )
