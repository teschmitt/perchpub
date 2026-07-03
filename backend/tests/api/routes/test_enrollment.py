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

import contextlib
import hashlib
import uuid
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.ca.step_ca_client import SignedCertificate
from app.core import ratelimit
from app.core.config import settings
from app.models import EnrollmentToken, Station, User
from app.models.enrollment import (
    EnrollmentAudit,
    EnrollmentAuditEvent,
    EnrollmentSession,
)
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


def _csr_with_key(
    key: ec.EllipticCurvePrivateKey, common_name: str = "device-001.local"
) -> str:
    """Build a CSR from a caller-supplied key.

    Unlike ``make_csr`` (which mints a fresh key each call), this lets two CSRs
    share one key — and therefore one leaf SPKI — modelling a station that
    re-enrolls with its persisted keypair to refresh its certificate.
    """
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(Encoding.PEM).decode("utf-8")


def _operator(db: Session, client: TestClient) -> tuple[User, dict[str, str]]:
    email = random_email()
    headers = authentication_token_from_email(client=client, email=email, db=db)
    user = db.exec(select(User).where(User.email == email)).one()
    return user, headers


def _create_session(
    client: TestClient, headers: dict[str, str], *, is_private: bool | None = None
) -> EnrollmentSession:
    body: dict[str, object] = {"latitude": 47.5, "longitude": 8.7}
    if is_private is not None:
        body["is_private"] = is_private
    r = client.post(
        f"{settings.API_V1_STR}/enrollment/create",
        headers=headers,
        json=body,
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


def test_reenroll_same_key_refreshes_cert_and_reuses_station(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """Re-enrolling with the persisted keypair refreshes the certificate on the
    SAME station instead of tripping the unique SPKI index with a 500.

    A station keeps its device keypair across enrollments, so its second CSR
    carries the same public key -> the signed leaf has the same SPKI -> the
    same ``Station.spki_sha256`` pin. The server must treat this as a refresh of
    the existing station, not a duplicate insert.
    """
    operator, headers = _operator(db, client)
    device_key = ec.generate_private_key(ec.SECP256R1())

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    # First enrollment creates the station.
    first = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r1 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{first.session_id}",
            json={"auth_token": first.auth_token, "csr_pem": _csr_with_key(device_key)},
        )
    assert r1.status_code == 200, r1.text
    station_id = uuid.UUID(r1.json()["station_id"])

    # Second enrollment reuses the SAME device key (persisted keypair).
    second = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r2 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{second.session_id}",
            json={
                "auth_token": second.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )

    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["success"] is True
    # Same station identity — no duplicate row was created.
    assert uuid.UUID(body["station_id"]) == station_id
    # A freshly signed leaf + chain are still returned.
    assert body["certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")
    assert body["ca_chain_pem"].startswith("-----BEGIN CERTIFICATE-----")

    # Exactly one station carries this SPKI (identity resolution is SPKI-unique).
    leaf = x509.load_pem_x509_certificate(body["certificate_pem"].encode("utf-8"))
    spki = hashlib.sha256(
        leaf.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    ).hexdigest()
    stations = db.exec(select(Station).where(Station.spki_sha256 == spki)).all()
    assert len(stations) == 1
    assert stations[0].id == station_id
    assert stations[0].owner_id == operator.id

    # The second session is claimed and points at the same, existing station.
    token = db.get(EnrollmentToken, second.session_id)
    assert token is not None
    assert token.claimed is True
    assert token.station_id == station_id


def test_reenroll_same_key_different_owner_is_rejected(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """A device key already bound to one account cannot be re-enrolled into
    another — the SPKI -> owner binding is not silently transferable.
    """
    owner_a, headers_a = _operator(db, client)
    _owner_b, headers_b = _operator(db, client)
    device_key = ec.generate_private_key(ec.SECP256R1())

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    first = _create_session(client, headers_a)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r1 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{first.session_id}",
            json={"auth_token": first.auth_token, "csr_pem": _csr_with_key(device_key)},
        )
    assert r1.status_code == 200, r1.text
    station_id = uuid.UUID(r1.json()["station_id"])

    # A different operator tries to enroll a device carrying the same key.
    second = _create_session(client, headers_b)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r2 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{second.session_id}",
            json={
                "auth_token": second.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )

    assert r2.status_code == 409, r2.text
    # Ownership is unchanged; the second session is left unclaimed.
    station = db.get(Station, station_id)
    assert station is not None
    assert station.owner_id == owner_a.id
    token = db.get(EnrollmentToken, second.session_id)
    assert token is not None
    assert token.claimed is False


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


def test_confirm_private_session_yields_private_station(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """A session created with is_private=True yields a new *private* station.

    Privacy is chosen at setup (create), stored on the enrollment session, and
    applied to the Station born at confirm time.
    """
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers, is_private=True)

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": make_csr()},
        )

    assert r.status_code == 200, r.text
    station = db.get(Station, uuid.UUID(r.json()["station_id"]))
    assert station is not None
    assert station.is_private is True


def test_confirm_omitted_privacy_defaults_public(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """Omitting is_private at create yields a new *public* station (default False)."""
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)  # is_private omitted

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": make_csr()},
        )

    assert r.status_code == 200, r.text
    station = db.get(Station, uuid.UUID(r.json()["station_id"]))
    assert station is not None
    assert station.is_private is False


def test_reenroll_does_not_alter_existing_privacy(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """Re-enrolling an existing device (same SPKI) through a session whose
    is_private differs leaves the existing station's privacy unchanged.

    Privacy is a station-management operation on an existing station, not a side
    effect of refreshing a certificate — mirroring how coordinates are create-only.
    """
    _, headers = _operator(db, client)
    device_key = ec.generate_private_key(ec.SECP256R1())

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    # First enrollment creates a PRIVATE station.
    first = _create_session(client, headers, is_private=True)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r1 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{first.session_id}",
            json={"auth_token": first.auth_token, "csr_pem": _csr_with_key(device_key)},
        )
    assert r1.status_code == 200, r1.text
    station_id = uuid.UUID(r1.json()["station_id"])

    # Re-enroll the SAME device through a session that says is_private=False.
    second = _create_session(client, headers, is_private=False)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r2 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{second.session_id}",
            json={
                "auth_token": second.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )
    assert r2.status_code == 200, r2.text
    assert uuid.UUID(r2.json()["station_id"]) == station_id

    # Privacy is unchanged — still private, despite the second session's False.
    db.expire_all()
    station = db.get(Station, station_id)
    assert station is not None
    assert station.is_private is True


class _FakeRedis:
    """In-memory fixed-window counter standing in for Redis in rate tests."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, ttl: int) -> bool:
        return True


@contextlib.contextmanager
def _fake_ratelimit_backend() -> Iterator[_FakeRedis]:
    """Swap the limiter's Redis for a deterministic in-memory counter and pin
    the clock so every hit lands in one fixed window.
    """
    fake = _FakeRedis()
    with (
        patch.object(ratelimit, "redis_client", fake),
        patch.object(ratelimit.time, "time", return_value=1_000_000.0),
    ):
        yield fake


def test_confirm_beyond_source_rate_returns_429_without_signing(
    client: TestClient,
    db: Session,
    device_ca: _DeviceCA,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirms beyond the per-source rate are 429'd before any side effect:
    no CSR is signed and no Station is created (design D2).
    """
    monkeypatch.setattr(settings, "ENROLLMENT_CONFIRM_RATE_PER_MIN", 2)
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)  # created before the fake backend

    sign_calls: list[str] = []

    async def _tracking_sign(csr: str) -> SignedCertificate:
        sign_calls.append(csr)
        return _signed_cert_for(csr, device_ca.intermediate)

    with (
        _fake_ratelimit_backend(),
        patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign),
    ):
        # Exhaust the 2/min budget with confirms to unknown sessions (still
        # counted — the limiter runs before the handler's 404).
        for _ in range(2):
            r = client.post(
                f"{settings.API_V1_STR}/enrollment/confirm/{uuid.uuid4()}",
                json={"auth_token": "x", "csr_pem": make_csr()},
            )
            assert r.status_code == 404
        # The 3rd confirm — a valid session that would otherwise sign+create —
        # is rejected by the rate limit.
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": make_csr()},
        )

    assert r.status_code == 429
    assert r.headers.get("retry-after") is not None
    assert sign_calls == []  # step-ca was never called
    token = db.get(EnrollmentToken, enrollment.session_id)
    assert token is not None
    assert token.claimed is False
    assert token.station_id is None


def test_create_beyond_user_rate_returns_429_without_token(
    client: TestClient,
    db: Session,
    device_ca: _DeviceCA,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/create beyond the per-user rate is 429'd with no EnrollmentToken."""
    monkeypatch.setattr(settings, "ENROLLMENT_CREATE_RATE_PER_MIN", 2)
    operator, headers = _operator(db, client)

    with _fake_ratelimit_backend():
        for _ in range(2):
            ok = client.post(
                f"{settings.API_V1_STR}/enrollment/create",
                headers=headers,
                json={"latitude": 47.5, "longitude": 8.7},
            )
            assert ok.status_code == 200, ok.text
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/create",
            headers=headers,
            json={"latitude": 47.5, "longitude": 8.7},
        )

    assert r.status_code == 429
    assert r.headers.get("retry-after") is not None
    tokens = db.exec(
        select(EnrollmentToken).where(EnrollmentToken.owner_id == operator.id)
    ).all()
    assert len(tokens) == 2  # the rejected create persisted nothing


def test_create_rate_exempts_superuser(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Superusers are exempt from the create rate limit."""
    monkeypatch.setattr(settings, "ENROLLMENT_CREATE_RATE_PER_MIN", 1)
    with _fake_ratelimit_backend():
        for _ in range(3):
            r = client.post(
                f"{settings.API_V1_STR}/enrollment/create",
                headers=superuser_token_headers,
                json={"latitude": 47.5, "longitude": 8.7},
            )
            assert r.status_code == 200, r.text


def test_confirm_new_station_at_ceiling_returns_403_without_signing(
    client: TestClient,
    db: Session,
    device_ca: _DeviceCA,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-superuser at the owned-station ceiling is refused when confirming a
    NEW device — before any CSR is signed and with no station created (D2). The
    ceiling is enforced at station creation, not at /create.
    """
    monkeypatch.setattr(settings, "MAX_STATIONS_PER_USER", 2)
    operator, headers = _operator(db, client)
    for _ in range(2):
        db.add(Station(latitude=0.0, longitude=0.0, owner_id=operator.id))
    db.commit()

    enrollment = _create_session(client, headers)  # /create still succeeds at cap
    sign_calls: list[str] = []

    async def _tracking_sign(csr: str) -> SignedCertificate:
        sign_calls.append(csr)
        return _signed_cert_for(csr, device_ca.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": make_csr()},
        )
    assert r.status_code == 403, r.text
    assert sign_calls == []  # rejected before signing
    stations = db.exec(
        select(Station).where(Station.owner_id == operator.id)
    ).all()
    assert len(stations) == 2  # no third station created


def test_at_station_ceiling_can_still_refresh_existing_station(
    client: TestClient,
    db: Session,
    device_ca: _DeviceCA,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user AT the owned-station ceiling can still re-enroll (refresh the cert
    of) an EXISTING station — the ceiling gates new stations only, and refresh
    has no other path (D2/D1). A new device at the ceiling is still refused.
    """
    monkeypatch.setattr(settings, "MAX_STATIONS_PER_USER", 1)
    _, headers = _operator(db, client)
    device_key = ec.generate_private_key(ec.SECP256R1())

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    first = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r1 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{first.session_id}",
            json={
                "auth_token": first.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )
    assert r1.status_code == 200, r1.text  # user is now AT the ceiling (1 station)
    station_id = uuid.UUID(r1.json()["station_id"])

    # Refresh the SAME station (same key) while at the ceiling -> allowed.
    second = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r2 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{second.session_id}",
            json={
                "auth_token": second.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )
    assert r2.status_code == 200, r2.text
    assert uuid.UUID(r2.json()["station_id"]) == station_id  # refreshed, not new

    # A NEW device at the ceiling is refused.
    third = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r3 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{third.session_id}",
            json={
                "auth_token": third.auth_token,
                "csr_pem": _csr_with_key(ec.generate_private_key(ec.SECP256R1())),
            },
        )
    assert r3.status_code == 403, r3.text


def test_create_at_active_session_ceiling_returns_403(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user holding the max active (unclaimed, unexpired) sessions gets 403."""
    monkeypatch.setattr(settings, "MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER", 2)
    operator, headers = _operator(db, client)
    for _ in range(2):
        _create_session(client, headers)

    r = client.post(
        f"{settings.API_V1_STR}/enrollment/create",
        headers=headers,
        json={"latitude": 47.5, "longitude": 8.7},
    )
    assert r.status_code == 403
    tokens = db.exec(
        select(EnrollmentToken).where(EnrollmentToken.owner_id == operator.id)
    ).all()
    assert len(tokens) == 2  # only the two under-ceiling sessions persisted


def test_create_quota_exempts_superuser(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Superusers are exempt from both quotas (station + active session)."""
    monkeypatch.setattr(settings, "MAX_STATIONS_PER_USER", 0)
    monkeypatch.setattr(settings, "MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER", 0)
    r = client.post(
        f"{settings.API_V1_STR}/enrollment/create",
        headers=superuser_token_headers,
        json={"latitude": 47.5, "longitude": 8.7},
    )
    assert r.status_code == 200, r.text


def test_confirm_rate_fails_open_when_backend_unavailable(
    client: TestClient,
    db: Session,
    device_ca: _DeviceCA,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Redis outage disables the rate limit (fail-open): a valid confirm still
    succeeds even with the rate configured to reject everything.
    """
    monkeypatch.setattr(settings, "ENROLLMENT_CONFIRM_RATE_PER_MIN", 0)
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)

    broken = MagicMock()
    broken.incr.side_effect = RedisConnectionError("backend down")

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    with (
        patch.object(ratelimit, "redis_client", broken),
        patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign),
    ):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": make_csr()},
        )
    assert r.status_code == 200, r.text


def test_confirm_limiter_neutralized_by_default(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """More confirm calls than the per-source limit do NOT 429 by default.

    Guards the in-stack (live-Redis) suite: the confirm limiter keys on the
    shared "testclient" source, so without the autouse fail-open fixture these
    would 429 once past ENROLLMENT_CONFIRM_RATE_PER_MIN and break unrelated
    confirm tests.
    """
    over = settings.ENROLLMENT_CONFIRM_RATE_PER_MIN + 3
    for _ in range(over):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{uuid.uuid4()}",
            json={"auth_token": "x", "csr_pem": make_csr()},
        )
        assert r.status_code == 404, r.text  # unknown session, never 429


def test_reenroll_revoked_pin_refused_without_signing(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """A revoked-pin re-confirm is refused BEFORE step-ca signs (no throwaway
    cert), and the failed attempt is charged so the <=3 cap bounds retries (D1).
    """
    _, headers = _operator(db, client)
    device_key = ec.generate_private_key(ec.SECP256R1())
    sign_calls: list[str] = []

    async def _tracking_sign(csr: str) -> SignedCertificate:
        sign_calls.append(csr)
        return _signed_cert_for(csr, device_ca.intermediate)

    first = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign):
        r1 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{first.session_id}",
            json={
                "auth_token": first.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )
    assert r1.status_code == 200, r1.text
    assert len(sign_calls) == 1  # the successful enrollment signed once
    station_id = uuid.UUID(r1.json()["station_id"])

    station = db.get(Station, station_id)
    assert station is not None
    station.revoked_at = datetime.now(timezone.utc)
    db.add(station)
    db.commit()

    second = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign):
        r2 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{second.session_id}",
            json={
                "auth_token": second.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )
    assert r2.status_code == 409, r2.text
    assert len(sign_calls) == 1  # revoked re-confirm did NOT sign (no throwaway cert)
    token = db.get(EnrollmentToken, second.session_id)
    assert token is not None
    assert token.attempts == 1  # the failed attempt was charged
    assert token.claimed is False


def _audit_rows(
    db: Session, session_id: uuid.UUID, event: EnrollmentAuditEvent
) -> list[EnrollmentAudit]:
    return db.exec(
        select(EnrollmentAudit).where(
            EnrollmentAudit.session_id == session_id,
            EnrollmentAudit.event == event,
        )
    ).all()


def test_create_writes_session_created_audit(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """/create records a session_created audit row with actor + source."""
    operator, headers = _operator(db, client)
    before = datetime.now(timezone.utc)
    enrollment = _create_session(client, headers)

    rows = _audit_rows(
        db, enrollment.session_id, EnrollmentAuditEvent.session_created
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == operator.id
    assert row.source  # the request source (TestClient host) is recorded
    assert row.station_id is None
    assert row.spki_sha256 is None
    assert row.created_at >= before.replace(tzinfo=None) - timedelta(seconds=5)


def test_confirm_writes_confirm_succeeded_audit(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """A completed confirm writes exactly one confirm_succeeded row linking the
    resulting station (spki + id) to the session, its owner, source, and time.
    """
    operator, headers = _operator(db, client)
    enrollment = _create_session(client, headers)

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": make_csr()},
        )
    assert r.status_code == 200, r.text
    station_id = uuid.UUID(r.json()["station_id"])
    station = db.get(Station, station_id)
    assert station is not None

    rows = _audit_rows(
        db, enrollment.session_id, EnrollmentAuditEvent.confirm_succeeded
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.station_id == station_id
    assert row.spki_sha256 == station.spki_sha256
    assert row.actor_user_id == operator.id
    assert row.session_id == enrollment.session_id
    assert row.source


def test_confirm_audit_source_prefers_forwarded_for_and_records_user_agent(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """The confirm audit's source is the leftmost X-Forwarded-For hop (the
    original client), falling back to request.client.host, and the station's
    user-agent is captured.
    """
    _, headers = _operator(db, client)
    enrollment = _create_session(client, headers)

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{enrollment.session_id}",
            json={"auth_token": enrollment.auth_token, "csr_pem": make_csr()},
            headers={
                "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
                "User-Agent": "perchpub-station/1.2",
            },
        )
    assert r.status_code == 200, r.text

    rows = _audit_rows(
        db, enrollment.session_id, EnrollmentAuditEvent.confirm_succeeded
    )
    assert len(rows) == 1
    assert rows[0].source == "203.0.113.7"
    assert rows[0].user_agent == "perchpub-station/1.2"


def test_reenroll_revoked_pin_does_not_reactivate(
    client: TestClient, db: Session, device_ca: _DeviceCA
) -> None:
    """Re-confirming with a revoked station's key (same SPKI) is refused and the
    station stays revoked — recovery requires a fresh device key (D1).
    """
    operator, headers = _operator(db, client)
    device_key = ec.generate_private_key(ec.SECP256R1())

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, device_ca.intermediate)

    first = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r1 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{first.session_id}",
            json={
                "auth_token": first.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )
    assert r1.status_code == 200, r1.text
    station_id = uuid.UUID(r1.json()["station_id"])

    station = db.get(Station, station_id)
    assert station is not None
    station.revoked_at = datetime.now(timezone.utc)
    db.add(station)
    db.commit()

    # Re-enroll the SAME device key through a fresh session.
    second = _create_session(client, headers)
    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r2 = client.post(
            f"{settings.API_V1_STR}/enrollment/confirm/{second.session_id}",
            json={
                "auth_token": second.auth_token,
                "csr_pem": _csr_with_key(device_key),
            },
        )

    assert r2.status_code == 409, r2.text
    db.expire_all()
    station = db.get(Station, station_id)
    assert station is not None
    assert station.revoked_at is not None  # still revoked, not reactivated
    token = db.get(EnrollmentToken, second.session_id)
    assert token is not None
    assert token.claimed is False


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
