import functools
import hashlib
import urllib.parse
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import jwt
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import Station, TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)
optional_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token",
    auto_error=False,
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
OptionalTokenDep = Annotated[str | None, Depends(optional_oauth2)]


def _resolve_user(session: Session, token: str) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    return _resolve_user(session, token)


def get_optional_current_user(
    session: SessionDep, token: OptionalTokenDep
) -> User | None:
    if token is None:
        return None
    return _resolve_user(session, token)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


@functools.lru_cache(maxsize=1)
def _load_device_ca() -> x509.Certificate:
    pem_bytes = Path(settings.DEVICE_CLIENT_CA_CERT_PATH).read_bytes()
    return x509.load_pem_x509_certificate(pem_bytes)


_GENERIC_MTLS_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="client certificate required",
)


def get_current_station(session: SessionDep, request: Request) -> Station:
    """Resolve the calling station from the forwarded mTLS client cert.

    Threat model: this dependency only authenticates when the request
    arrives via the Traefik mtls entrypoint, which terminates TLS with
    `RequireAndVerifyClientCert` and then sets `MTLS_CLIENT_CERT_HEADER`
    from a leaf it has already validated against the device CA. Reaching
    this dependency over any other ingress (the regular https
    entrypoint, direct hits to backend:8000 in dev, etc.) leaves the
    header attacker-controlled — entrypoint isolation in mTLS-05 is
    what backs the trust boundary in production. Until that lands, this
    dep stays unwired.

    Header format: Traefik's `passTLSClientCert.pem` middleware emits a
    URL-encoded PEM (Go `url.QueryEscape`). `urllib.parse.unquote`
    inverses it without touching `+`, which appears literally inside
    base64 PEM bodies.

    Failure handling: every failure path collapses to 401 with the same
    generic detail. We do not distinguish between "header missing",
    "header malformed", "leaf signed by a different CA", and "no Station
    has the matching SPKI pin" — same intent as the WI-08 unified-signup
    response (no station-existence leak via timing or wording).
    """
    encoded = request.headers.get(settings.MTLS_CLIENT_CERT_HEADER)
    if not encoded:
        raise _GENERIC_MTLS_401

    try:
        pem_bytes = urllib.parse.unquote(encoded).encode("utf-8")
        leaf = x509.load_pem_x509_certificate(pem_bytes)
        ca = _load_device_ca()
        leaf.verify_directly_issued_by(ca)
        now = datetime.now(timezone.utc)
        if leaf.not_valid_before_utc > now or leaf.not_valid_after_utc < now:
            raise ValueError("leaf outside validity window")
        spki_der = leaf.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        spki_pin = hashlib.sha256(spki_der).hexdigest()
    except (InvalidSignature, ValueError, TypeError, FileNotFoundError):
        raise _GENERIC_MTLS_401

    station = session.exec(
        select(Station).where(Station.spki_sha256 == spki_pin)
    ).first()
    if station is None:
        raise _GENERIC_MTLS_401
    return station


CurrentStation = Annotated[Station, Depends(get_current_station)]
