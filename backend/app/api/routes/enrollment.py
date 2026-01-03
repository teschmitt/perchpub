import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.core.config import settings
from app.models.enrollment import (
    EnrollmentRequest,
    EnrollmentResponse,
    EnrollmentSession,
    EnrollmentToken,
)

TTL_SECONDS = 300
MAX_ENROLLMENT_ATTEMPTS = 3

# TODO: use a real secrets manager instead of env files like an amateur
HMAC_KEY_ID = "2025-12-rot1"
HMAC_KEY = bytes.fromhex(settings.ENROLLMENT_HMAC_KEY_HEX)

router = APIRouter(prefix="/enrollment", tags=["enrollment"])


def generate_token(auth_token: str) -> bytes:
    return hmac.new(HMAC_KEY, auth_token.encode("utf-8"), hashlib.sha256).digest()


@router.post("/create", response_model=EnrollmentSession)
def create_enrollment_session(
    session: SessionDep,
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
    )

    session.add(enrollment_token)
    session.commit()

    return EnrollmentSession(
        session_id=session_id, auth_token=auth_token, expires_at=expires_at
    )


@router.post("/confirm/{session_id}", response_model=EnrollmentResponse)
def enroll_station(
    session: SessionDep, session_id: uuid.UUID, enrollment_req: EnrollmentRequest
) -> EnrollmentResponse:
    enrollment_session = session.get(EnrollmentToken, session_id)

    # Session is expired
    if enrollment_session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session expired."
        )

    # Maximum number of retries has been reached
    if enrollment_session.attempts >= MAX_ENROLLMENT_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Too many retries."
        )

    # Session has already been claimed
    if enrollment_session.claimed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Already enrolled."
        )

    enrollment_session.attempts += 1

    # Verify auth token
    recv_token_tag = generate_token(enrollment_req.auth_token)
    verified = hmac.compare_digest(recv_token_tag, enrollment_session.token_tag)
    if not verified:
        session.add(enrollment_session)
        session.commit()
        session.refresh(enrollment_session)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid auth token."
        )

    enrollment_session.claimed = verified

    session.add(enrollment_session)
    session.commit()
    session.refresh(enrollment_session)

    return EnrollmentResponse(success=verified)
