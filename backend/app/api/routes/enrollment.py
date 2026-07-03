import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep, client_source
from app.ca.step_ca_client import sign_device_csr
from app.core.config import settings
from app.core.ratelimit import (
    enforce_enrollment_confirm_rate,
    enforce_enrollment_create_rate,
)
from app.models.enrollment import (
    EnrollmentAudit,
    EnrollmentAuditEvent,
    EnrollmentRequest,
    EnrollmentResponse,
    EnrollmentSession,
    EnrollmentSessionCreate,
    EnrollmentToken,
)
from app.models.station import Station

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
    # DB-backed per-user quotas (design D2), enforced before any write.
    # Always on (unlike the fail-open rate limit); superusers are exempt.
    if not current_user.is_superuser:
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        active_sessions = session.exec(
            select(func.count())
            .select_from(EnrollmentToken)
            .where(
                EnrollmentToken.owner_id == current_user.id,
                col(EnrollmentToken.claimed).is_(False),
                col(EnrollmentToken.expires_at) > now_naive,
            )
        ).one()
        if active_sessions >= settings.MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="active enrollment session limit reached",
            )
        # Owned, non-revoked stations — a revoked station frees a quota slot (D1).
        # This is a create-time gate (per spec), so the true station count can
        # overshoot MAX_STATIONS_PER_USER by at most the active-session ceiling
        # (a user may confirm sessions opened while under the cap); the active-
        # session quota bounds that slack.
        owned_stations = session.exec(
            select(func.count())
            .select_from(Station)
            .where(
                Station.owner_id == current_user.id,
                col(Station.revoked_at).is_(None),
            )
        ).one()
        if owned_stations >= settings.MAX_STATIONS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="station limit reached",
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
            source=client_source(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    session.commit()

    return EnrollmentSession(
        session_id=session_id,
        auth_token=auth_token,
        expires_at=expires_at,
        ca_pin=ca_pin,
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
    elif enrollment_session.latitude is None or enrollment_session.longitude is None:
        # Coordinates are only needed to create a new station; a refresh keeps
        # the station's existing location (relocation is a station-management
        # operation, not a side effect of re-enrolling).
        session.add(enrollment_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="enrollment session is missing coordinates",
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
            source=client_source(request),
            user_agent=request.headers.get("user-agent"),
            spki_sha256=station.spki_sha256,
            station_id=station.id,
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
