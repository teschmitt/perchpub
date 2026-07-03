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
    # Every "this session is no longer usable" case returns 401 with the same
    # generic detail, so a backend-for-frontend can treat any 401 as
    # "clear the cookie" without leaking which case occurred. Authorization
    # decisions on a *valid* principal (role/ownership) stay 403 elsewhere.
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise credentials_exception
    user = session.get(User, token_data.sub)
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise credentials_exception
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


def client_source(request: Request) -> str | None:
    """Best-effort origin identifier for audit trails and per-source throttling.

    Prefer the leftmost ``X-Forwarded-For`` hop (the original client), falling
    back to the socket peer. This is sound ONLY while Traefik is the direct edge
    with no trusted upstream: with no ``forwardedHeaders.trustedIPs`` configured,
    Traefik discards an attacker-supplied inbound XFF and rewrites it from the
    real peer, so the leftmost hop is the true client. If a CDN/LB is ever
    fronted (or ``trustedIPs`` is set), the leftmost hop becomes client-spoofable
    — the per-source rate limit could then be bypassed by rotating it and the
    audit ``source`` poisoned; revisit this choice at that point. The enrollment
    endpoints ride the ordinary HTTPS edge, not the mTLS entrypoint, so this is a
    weaker boundary than the mTLS cert header — it gates a throttle + audit, not
    authorization.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


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
    arrives via a Traefik mTLS entrypoint that terminates TLS with
    `RequireAndVerifyClientCert` against the device CA and sets
    `MTLS_CLIENT_CERT_HEADER` from the verified leaf via the
    `passTLSClientCert` middleware. Reaching this dep over any other
    ingress (plain HTTPS without client-cert verification, direct hits
    to backend:8000) leaves the header attacker-controlled —
    entrypoint isolation is the trust boundary. The dev stack runs no
    proxy (FU-11) so this dep is only exercised via tests that
    hand-stuff the header; prod-side mTLS wiring is the deferred
    follow-up to mTLS-05.

    Header format: Traefik's `passTLSClientCert.pem` middleware forwards the
    whole verified client chain as a **comma-separated** list of certificates,
    leaf first (observed in prod: `<leaf_b64>,<intermediate_b64>`). Each entry
    is the base64 DER body with the `-----BEGIN/END CERTIFICATE-----` armor
    stripped (Traefik 3.x). We take the first entry (the leaf), re-attach the
    armor, and parse it — splitting on the comma is load-bearing: wrapping the
    whole blob in one PEM block puts the leaf's `=` padding mid-stream and
    fails with `InvalidByte`. `unquote` (NOT `unquote_plus`) decodes any %0A
    newlines while leaving `+` — a valid base64 char — intact.

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
        # Take the leaf (first entry) from Traefik's comma-separated chain and
        # re-attach the PEM armor it strips. Splitting before re-armoring is
        # load-bearing — see the docstring's "Header format" note.
        leaf_b64 = urllib.parse.unquote(encoded).split(",", 1)[0].strip()
        decoded = leaf_b64.encode("utf-8")
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

    # Identity is the SPKI pin ALONE. The leaf's CommonName and SubjectAltNames
    # are never read for authorization: a station controls those via its CSR and
    # the step-ca OTT copies CSR-requested SANs verbatim, so trusting them would
    # let any station spoof another tenant's identity. Resolution is strictly
    # SHA-256(SPKI) -> Station -> owner_id. (enrollment-hardening, D4.)
    station = session.exec(
        select(Station).where(Station.spki_sha256 == spki_pin)
    ).first()
    if station is None:
        raise _GENERIC_MTLS_401
    if station.revoked_at is not None:
        # A revoked station's leaf no longer authenticates (D1): the same generic
        # 401 as an unknown pin, so no upload is stored and nothing is attributed
        # to it. The revoked leaf may still complete a TLS handshake until it
        # expires (a rate-limiting/DoS concern, not an integrity one).
        raise _GENERIC_MTLS_401
    return station


CurrentStation = Annotated[Station, Depends(get_current_station)]
