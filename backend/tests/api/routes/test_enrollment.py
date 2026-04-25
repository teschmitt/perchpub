"""Behavioral tests for the device enrollment flow.

The /create endpoint is operator-authenticated and stages station coordinates
plus an HMAC handshake token. The /confirm endpoint receives a CSR from the
station, exchanges it for a step-ca-signed leaf, and persists a Station with
the leaf's SPKI pin.

step-ca is mocked at the route module boundary
(app.api.routes.enrollment.sign_device_csr) — its wire structure is exercised
in tests/ca/test_step_ca_client.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.ca.step_ca_client import SignedCertificate
from app.core.config import settings
from app.models import EnrollmentToken, Station, User
from app.models.enrollment import EnrollmentSession
from tests.utils.mtls import make_ca, make_csr
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email, random_lower_string


def _signed_cert_for(csr_pem: str) -> SignedCertificate:
    """Build a fake step-ca response whose leaf SPKI matches csr_pem.

    The route hashes the LEAF cert's SPKI to derive the station pin, so the
    fake leaf must carry the CSR's public key.
    """
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    ca = make_ca()
    now = datetime.now(timezone.utc)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "device")]))
        .issuer_name(ca.cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(ca.key, hashes.SHA256())
    )
    return SignedCertificate(
        certificate_pem=leaf.public_bytes(Encoding.PEM).decode("utf-8"),
        ca_chain_pem=ca.cert_pem,
        not_before=now,
        not_after=now + timedelta(days=30),
    )


def _operator(db: Session, client: TestClient) -> tuple[User, dict[str, str]]:
    email = random_email()
    headers = authentication_token_from_email(client=client, email=email, db=db)
    user = db.exec(select(User).where(User.email == email)).one()
    return user, headers


def _create_session(client: TestClient, headers: dict[str, str]) -> EnrollmentSession:
    r = client.post(
        f"{settings.API_V1_STR}/enrollment/create",
        headers=headers,
        json={"latitude": 47.5, "longitude": 8.7},
    )
    assert r.status_code == 200, r.text
    return EnrollmentSession(**r.json())


def test_confirm_unknown_session_returns_404(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/enrollment/confirm/{uuid.uuid4()}",
        json={"auth_token": "irrelevant", "csr_pem": make_csr()},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Unknown enrollment session"


def test_create_session_requires_auth(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/enrollment/create",
        json={"latitude": 47.5, "longitude": 8.7},
    )
    assert r.status_code == 401


def test_full_enrollment_creates_station_with_spki_pin(
    client: TestClient, db: Session
) -> None:
    operator, headers = _operator(db, client)
    enrollment = _create_session(client, headers)
    csr_pem = make_csr("device-001.local")

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": csr_pem},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")
    assert body["ca_chain_pem"].startswith("-----BEGIN CERTIFICATE-----")
    station_id = uuid.UUID(body["station_id"])

    station = db.get(Station, station_id)
    assert station is not None
    assert station.owner_id == operator.id
    assert station.latitude == 47.5
    assert station.longitude == 8.7
    assert station.spki_sha256 is not None
    assert len(station.spki_sha256) == 64

    token = db.get(EnrollmentToken, enrollment.session_id)
    assert token is not None
    assert token.claimed is True
    assert token.station_id == station.id


def test_confirm_invalid_csr_returns_400(client: TestClient, db: Session) -> None:
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)

    r = client.post(
        f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
        json={"auth_token": enrollment.auth_token, "csr_pem": "not a real csr"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid CSR"


def test_confirm_step_ca_failure_returns_502(client: TestClient, db: Session) -> None:
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)
    csr_pem = make_csr()

    async def _raise(_csr: str) -> SignedCertificate:
        raise httpx.HTTPError("step-ca exploded")

    with patch("app.api.routes.enrollment.sign_device_csr", new=_raise):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": csr_pem},
        )

    assert r.status_code == 502
    assert r.json()["detail"] == "certificate issuance failed"


def test_confirm_invalid_auth_token_returns_403(
    client: TestClient, db: Session
) -> None:
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)

    r = client.post(
        f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
        json={"auth_token": "wrong" + random_lower_string(), "csr_pem": make_csr()},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Invalid auth token."
