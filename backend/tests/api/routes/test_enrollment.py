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

import hashlib
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.ca.step_ca_client import SignedCertificate
from app.core.config import settings
from app.models import EnrollmentToken, Station, User
from app.models.enrollment import EnrollmentSession
from tests.utils.mtls import TestCA, make_ca, make_csr, make_intermediate
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email, random_lower_string


@dataclass
class _DeviceCA:
    """The device-CA material a test's enrollment route is pointed at."""

    root: TestCA
    intermediate: TestCA
    root_pem: str
    pin: str


@pytest.fixture(autouse=True)
def device_ca(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[_DeviceCA, None, None]:
    """Point the enrollment route at a known device-CA root on disk.

    Every ``/create`` computes ``ca_pin`` from ``STEP_CA_ROOT_CERT_PATH`` and
    every ``/confirm`` appends that root to the returned chain, so both paths
    need a real root file. The route's module-level pin/root caches are cleared
    around each test so the patched path takes effect.
    """
    from app.api.routes import enrollment as enr

    root = make_ca("PerchPub Test Root CA")
    intermediate = make_intermediate(root)
    root_file = tmp_path / "root_ca.crt"
    root_file.write_text(root.cert_pem, encoding="utf-8")
    monkeypatch.setattr(settings, "STEP_CA_ROOT_CERT_PATH", str(root_file))
    enr._device_ca_pin.cache_clear()
    enr._device_ca_root_pem.cache_clear()
    yield _DeviceCA(
        root=root,
        intermediate=intermediate,
        root_pem=root.cert_pem,
        pin=root.spki_sha256_hex,
    )
    enr._device_ca_pin.cache_clear()
    enr._device_ca_root_pem.cache_clear()


def _signed_cert_for(csr_pem: str, signing_ca: TestCA) -> SignedCertificate:
    """Build a fake step-ca response whose leaf SPKI matches csr_pem.

    The route hashes the LEAF cert's SPKI to derive the station pin, so the
    fake leaf must carry the CSR's public key. The leaf is signed by
    ``signing_ca`` (the issuing intermediate) and ``ca_chain_pem`` carries that
    intermediate — mirroring step-ca, which returns the intermediate and lets
    the backend append the root.
    """
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    now = datetime.now(timezone.utc)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "device")]))
        .issuer_name(signing_ca.cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(signing_ca.key, hashes.SHA256())
    )
    return SignedCertificate(
        certificate_pem=leaf.public_bytes(Encoding.PEM).decode("utf-8"),
        ca_chain_pem=signing_ca.cert_pem,
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


@pytest.mark.parametrize("key_type", ["ec", "ed25519"])
def test_full_enrollment_creates_station_with_spki_pin(
    client: TestClient, db: Session, key_type: str, device_ca: _DeviceCA
) -> None:
    operator, headers = _operator(db, client)
    enrollment = _create_session(client, headers)
    csr_pem = make_csr("device-001.local", key_type=key_type)

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

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

    # The issued leaf preserves the CSR's key type, and the station pin is
    # SHA-256 of that leaf's SPKI (DER) regardless of key algorithm.
    leaf = x509.load_pem_x509_certificate(body["certificate_pem"].encode("utf-8"))
    expected_pub = Ed25519PublicKey if key_type == "ed25519" else EllipticCurvePublicKey
    assert isinstance(leaf.public_key(), expected_pub)
    leaf_spki_der = leaf.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )

    station = db.get(Station, station_id)
    assert station is not None
    assert station.owner_id == operator.id
    assert station.latitude == 47.5
    assert station.longitude == 8.7
    assert station.spki_sha256 == hashlib.sha256(leaf_spki_der).hexdigest()
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


def test_create_returns_root_ca_pin(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """/create returns ca_pin = lowercase-hex SHA-256(SPKI) of the device-CA root."""
    _, headers = _operator(db, client)
    r = client.post(
        f"{settings.API_V1_STR}/enrollment/create",
        headers=headers,
        json={"latitude": 47.5, "longitude": 8.7},
    )
    assert r.status_code == 200, r.text
    ca_pin = r.json()["ca_pin"]

    assert ca_pin == device_ca.pin
    assert ca_pin == device_ca.root.spki_sha256_hex
    assert len(ca_pin) == 64
    assert ca_pin == ca_pin.lower()
    int(ca_pin, 16)  # is valid hex


def test_create_expires_at_uses_default_60s_ttl(
    client: TestClient, db: Session
) -> None:
    """The default enrollment window is 60 s, not the old hardcoded 300 s."""
    assert settings.ENROLLMENT_TTL_SECONDS == 60
    _, headers = _operator(db, client)
    before = datetime.now(timezone.utc)
    enrollment = _create_session(client, headers)
    ttl = (enrollment.expires_at - before).total_seconds()
    assert 55 <= ttl <= 65, ttl


def test_create_expires_at_honors_configured_ttl(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """expires_at derives from settings.ENROLLMENT_TTL_SECONDS, not a constant."""
    monkeypatch.setattr(settings, "ENROLLMENT_TTL_SECONDS", 123)
    _, headers = _operator(db, client)
    before = datetime.now(timezone.utc)
    enrollment = _create_session(client, headers)
    ttl = (enrollment.expires_at - before).total_seconds()
    assert 118 <= ttl <= 128, ttl


def test_confirm_returns_intermediate_and_root_chain(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """/confirm returns intermediate+root; the root's SPKI-SHA256 equals ca_pin."""
    _, headers = _operator(db, client)
    create = client.post(
        f"{settings.API_V1_STR}/enrollment/create",
        headers=headers,
        json={"latitude": 47.5, "longitude": 8.7},
    )
    assert create.status_code == 200, create.text
    session = create.json()
    ca_pin = session["ca_pin"]

    csr_pem = make_csr("device-chain.local")

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        confirm = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{session['session_id']}",
            json={"auth_token": session["auth_token"], "csr_pem": csr_pem},
        )

    assert confirm.status_code == 200, confirm.text
    body = confirm.json()

    # The chain carries exactly the issuing intermediate followed by the root.
    chain = x509.load_pem_x509_certificates(body["ca_chain_pem"].encode("utf-8"))
    assert len(chain) == 2
    intermediate_cert, root_cert = chain

    # leaf -> intermediate -> root builds (each cert is issued by the next).
    leaf = x509.load_pem_x509_certificate(body["certificate_pem"].encode("utf-8"))
    leaf.verify_directly_issued_by(intermediate_cert)
    intermediate_cert.verify_directly_issued_by(root_cert)

    # The root is self-issued and is a usable CA.
    assert root_cert.subject == root_cert.issuer
    basic = root_cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert basic.value.ca is True

    # The returned root's SPKI-SHA256 equals the create-time ca_pin (D3 interop).
    root_spki = root_cert.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    assert hashlib.sha256(root_spki).hexdigest() == ca_pin


def test_create_missing_root_commits_no_orphan_token(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing root fails loudly at create without persisting an orphan token."""
    from app.api.routes import enrollment as enr

    operator, headers = _operator(db, client)
    monkeypatch.setattr(settings, "STEP_CA_ROOT_CERT_PATH", "/nonexistent/root_ca.crt")
    enr._device_ca_pin.cache_clear()
    enr._device_ca_root_pem.cache_clear()

    with pytest.raises(FileNotFoundError):
        client.post(
            f"{settings.API_V1_STR}/enrollment/create",
            headers=headers,
            json={"latitude": 47.5, "longitude": 8.7},
        )

    orphans = db.exec(
        select(EnrollmentToken).where(EnrollmentToken.owner_id == operator.id)
    ).all()
    assert orphans == []


def test_confirm_empty_intermediate_chain_returns_502(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """An empty step-ca chain must fail loudly (502), never degrade to root-only."""
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)
    csr_pem = make_csr()

    async def _fake_sign_no_chain(csr: str) -> SignedCertificate:
        signed = _signed_cert_for(csr, device_ca.intermediate)
        return SignedCertificate(
            certificate_pem=signed.certificate_pem,
            ca_chain_pem="",  # step-ca returned no intermediate
            not_before=signed.not_before,
            not_after=signed.not_after,
        )

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign_no_chain):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": csr_pem},
        )

    assert r.status_code == 502
    assert r.json()["detail"] == "certificate issuance failed"

    # The session stays unclaimed and retryable; no Station was persisted.
    token = db.get(EnrollmentToken, enrollment.session_id)
    assert token is not None
    assert token.claimed is False
    assert token.station_id is None


def test_confirm_missing_root_leaves_session_unclaimed(
    client: TestClient,
    db: Session,
    device_ca: _DeviceCA,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the root read fails at confirm, the session is left unclaimed/retryable."""
    from app.api.routes import enrollment as enr

    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)  # caches the pin from a good root
    csr_pem = make_csr()

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    # Break the root and drop the cache so /confirm's chain build re-reads it.
    monkeypatch.setattr(settings, "STEP_CA_ROOT_CERT_PATH", "/nonexistent/root_ca.crt")
    enr._device_ca_root_pem.cache_clear()
    enr._device_ca_pin.cache_clear()

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        with pytest.raises(FileNotFoundError):
            client.post(
                f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
                json={"auth_token": enrollment.auth_token, "csr_pem": csr_pem},
            )

    token = db.get(EnrollmentToken, enrollment.session_id)
    assert token is not None
    assert token.claimed is False
    assert token.station_id is None
