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
    arrives via the Traefik `mtls` entrypoint (port 8443, configured in
    `docker-compose.override.yml` and `traefik/dynamic.yml`), which
    terminates TLS with `RequireAndVerifyClientCert` against the
    step-ca intermediate CA and then sets `MTLS_CLIENT_CERT_HEADER`
    from the leaf via the `passTLSClientCert` middleware. Reaching this
    dependency over any other ingress (the regular `https` entrypoint,
    direct hits to backend:8000 in dev, etc.) leaves the header
    attacker-controlled — entrypoint isolation is what backs the trust
    boundary. mTLS-06 routes will use this dep on the upload path only.

    Header format: Traefik's `passTLSClientCert.pem` middleware emits the
    leaf URL-encoded — newlines as `%0A`, `+` left as literal `+` because
    it's a valid base64 char and Traefik's escape doesn't treat headers
    as form-data. Use `urllib.parse.unquote` (NOT `unquote_plus`):
    `unquote_plus` would decode `+` → space and corrupt the base64 body.
    Traefik 3.x's `pem: true` strips the `-----BEGIN/END CERTIFICATE-----`
    armor and forwards just the base64 body, so we re-attach the armor
    when missing before parsing.

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
        decoded = urllib.parse.unquote(encoded).strip().encode("utf-8")
        if b"-----BEGIN CERTIFICATE-----" not in decoded:
            decoded = (
                b"-----BEGIN CERTIFICATE-----\n"
                + decoded
                + b"\n-----END CERTIFICATE-----\n"
            )
        leaf = x509.load_pem_x509_certificate(decoded)
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
