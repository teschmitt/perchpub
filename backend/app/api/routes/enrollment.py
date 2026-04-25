import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.ca.step_ca_client import sign_device_csr
from app.core.config import settings
from app.models.enrollment import (
    EnrollmentRequest,
    EnrollmentResponse,
    EnrollmentSession,
    EnrollmentSessionCreate,
    EnrollmentToken,
)
from app.models.station import Station

TTL_SECONDS = 300
MAX_ENROLLMENT_ATTEMPTS = 3

# TODO: use a real secrets manager instead of env files like an amateur
HMAC_KEY_ID = "2025-12-rot1"
HMAC_KEY = bytes.fromhex(settings.ENROLLMENT_HMAC_KEY_HEX)

router = APIRouter(prefix="/enrollment", tags=["enrollment"])


def generate_token(auth_token: str) -> bytes:
    return hmac.new(HMAC_KEY, auth_token.encode("utf-8"), hashlib.sha256).digest()


def _csr_spki_sha256_hex(cert: x509.Certificate) -> str:
    spki_der = cert.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(spki_der).hexdigest()


@router.post("/create", response_model=EnrollmentSession)
def create_enrollment_session(
    session: SessionDep,
    current_user: CurrentUser,
    create_in: EnrollmentSessionCreate,
) -> EnrollmentSession:
    session_id = uuid.uuid4()
    auth_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TTL_SECONDS)

    enrollment_token = EnrollmentToken(
        session_id=session_id,
        expires_at=expires_at,
        claimed=False,
        token_tag=generate_token(auth_token),
        key_id=HMAC_KEY_ID,
        owner_id=current_user.id,
        latitude=create_in.latitude,
        longitude=create_in.longitude,
    )

    session.add(enrollment_token)
    session.commit()

    return EnrollmentSession(
        session_id=session_id, auth_token=auth_token, expires_at=expires_at
    )


@router.post("/confirm/{session_id}", response_model=EnrollmentResponse)
async def enroll_station(
    session: SessionDep, session_id: uuid.UUID, enrollment_req: EnrollmentRequest
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
        x509.load_pem_x509_csr(enrollment_req.csr_pem.encode("utf-8"))
    except ValueError:
        session.add(enrollment_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid CSR"
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

    leaf = x509.load_pem_x509_certificate(signed.certificate_pem.encode("utf-8"))
    spki_pin = _csr_spki_sha256_hex(leaf)

    if enrollment_session.latitude is None or enrollment_session.longitude is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="enrollment session is missing coordinates",
        )

    station = Station(
        latitude=enrollment_session.latitude,
        longitude=enrollment_session.longitude,
        owner_id=enrollment_session.owner_id,
        spki_sha256=spki_pin,
    )
    session.add(station)
    session.flush()

    enrollment_session.claimed = True
    enrollment_session.station_id = station.id
    session.add(enrollment_session)
    session.commit()
    session.refresh(station)

    return EnrollmentResponse(
        success=True,
        certificate_pem=signed.certificate_pem,
        ca_chain_pem=signed.ca_chain_pem,
        station_id=station.id,
    )
