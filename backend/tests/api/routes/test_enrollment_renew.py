"""Behavioral tests for unattended station certificate renewal.

``POST /api/v1/enrollment/renew`` is the mTLS-authenticated sibling of
``/enrollment/confirm``: the station proves its identity with its current
enrollment-issued client certificate (forwarded by the Traefik mTLS
entrypoint), POSTs a CSR built over its EXISTING keypair, and receives a fresh
leaf plus the ``[intermediate, root]`` device-CA chain. The wire contract is
pinned in the perchstation repo (specs/001-clip-delivery/contracts/
perchpub-api.md §4); the ``RenewalRequest``/``RenewalResponse`` schema names
and fields are load-bearing — the station mirrors ``openapi.json`` with a
drift test.

step-ca is mocked at the route module boundary
(app.api.routes.enrollment.sign_device_csr), like test_enrollment.py.
"""

from __future__ import annotations

import contextlib
import hashlib
import urllib.parse
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.deps import _load_device_ca
from app.ca.step_ca_client import SignedCertificate
from app.core import ratelimit
from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Station, User
from app.models.enrollment import EnrollmentAudit, EnrollmentAuditEvent
from tests.utils.fake_redis import FakeRedis
from tests.utils.mtls import (
    DeviceKey,
    TestCA,
    TestLeaf,
    make_ca,
    make_intermediate,
    make_leaf,
)
from tests.utils.utils import random_email, random_lower_string

RENEW_URL = f"{settings.API_V1_STR}/enrollment/renew"


@dataclass
class _RenewalPKI:
    """One coherent root → intermediate hierarchy both trust stores point at."""

    root: TestCA
    intermediate: TestCA


@pytest.fixture
def renewal_pki(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[_RenewalPKI, None, None]:
    """Wire the two CA files a renewal touches to one test hierarchy.

    - ``DEVICE_CLIENT_CA_CERT_PATH`` (deps.get_current_station verifies the
      presented leaf against this DIRECT issuer) ← the intermediate.
    - ``STEP_CA_ROOT_CERT_PATH`` (the enrollment route appends this root to
      the response chain) ← the root.

    Module-level lru_caches on both readers are cleared around each test so
    the patched paths take effect.
    """
    from app.api.routes import enrollment as enr

    root = make_ca("PerchPub Test Root CA")
    intermediate = make_intermediate(root)
    root_file = tmp_path / "root_ca.crt"
    root_file.write_text(root.cert_pem, encoding="utf-8")
    intermediate_file = tmp_path / "intermediate_ca.crt"
    intermediate_file.write_text(intermediate.cert_pem, encoding="utf-8")
    monkeypatch.setattr(settings, "STEP_CA_ROOT_CERT_PATH", str(root_file))
    monkeypatch.setattr(settings, "DEVICE_CLIENT_CA_CERT_PATH", str(intermediate_file))
    enr._device_ca_pin.cache_clear()
    enr._device_ca_root_pem.cache_clear()
    _load_device_ca.cache_clear()
    yield _RenewalPKI(root=root, intermediate=intermediate)
    enr._device_ca_pin.cache_clear()
    enr._device_ca_root_pem.cache_clear()
    _load_device_ca.cache_clear()


def _cert_header(leaf: TestLeaf) -> dict[str, str]:
    return {settings.MTLS_CLIENT_CERT_HEADER: urllib.parse.quote(leaf.cert_pem)}


def _csr_for_key(key: DeviceKey, common_name: str = "station-abc123.local") -> str:
    """A station renewal CSR: existing key, stable identity as CN + first SAN."""
    algorithm = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False
        )
        .sign(key, algorithm)
    )
    return csr.public_bytes(Encoding.PEM).decode("utf-8")


def _enrolled_station(db: Session, leaf: TestLeaf) -> Station:
    user = User(
        email=random_email(),
        hashed_password=get_password_hash(random_lower_string()),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    station = Station(
        latitude=47.5,
        longitude=8.7,
        owner_id=user.id,
        spki_sha256=leaf.spki_sha256_hex,
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


def _signed_cert_for(csr_pem: str, signing_ca: TestCA) -> SignedCertificate:
    """Fake step-ca response whose leaf carries the CSR's public key.

    Mirrors step-ca: the leaf is signed by the issuing intermediate and
    ``ca_chain_pem`` carries that intermediate; the backend appends the root.
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
        .not_valid_after(now + timedelta(hours=24))
        .sign(signing_ca.key, hashes.SHA256())
    )
    return SignedCertificate(
        certificate_pem=leaf.public_bytes(Encoding.PEM).decode("utf-8"),
        ca_chain_pem=signing_ca.cert_pem,
        not_before=now,
        not_after=now + timedelta(hours=24),
    )


@contextlib.contextmanager
def _fake_ratelimit_backend() -> Iterator[FakeRedis]:
    """Counting limiter backend with a pinned clock and a closed circuit.

    Same shape as test_enrollment.py's helper: the autouse conftest fixture
    fails the limiter open by default, so rate-limit tests opt back in here.
    """
    fake = FakeRedis()
    with (
        patch.object(ratelimit, "redis_client", fake),
        patch.object(ratelimit.time, "time", return_value=1_000_000.0),
    ):
        ratelimit._reset_circuit()
        yield fake


@pytest.mark.parametrize("key_type", ["ed25519", "ec"])
def test_renew_happy_path_issues_fresh_leaf_and_chain(
    client: TestClient, db: Session, renewal_pki: _RenewalPKI, key_type: str
) -> None:
    """Enrolled cert + matching-SPKI CSR → 200 with a verifiable leaf + chain."""
    leaf = make_leaf(
        renewal_pki.intermediate, "station-abc123.local", key_type=key_type
    )
    station = _enrolled_station(db, leaf)
    csr_pem = _csr_for_key(leaf.key)

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, renewal_pki.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r = client.post(
            RENEW_URL, json={"csr_pem": csr_pem}, headers=_cert_header(leaf)
        )

    assert r.status_code == 200, r.text
    body = r.json()
    # Exactly the two contract fields. The station's parser tolerates additive
    # optional fields, but adding one must be a deliberate cross-repo decision.
    assert set(body) == {"certificate_pem", "ca_chain_pem"}

    new_leaf = x509.load_pem_x509_certificate(body["certificate_pem"].encode("utf-8"))
    chain = x509.load_pem_x509_certificates(body["ca_chain_pem"].encode("utf-8"))
    assert len(chain) == 2
    intermediate_cert, root_cert = chain

    # leaf -> intermediate -> root builds.
    new_leaf.verify_directly_issued_by(intermediate_cert)
    intermediate_cert.verify_directly_issued_by(root_cert)

    # The root is the enrollment root, byte-for-byte — renewal never migrates
    # the trust anchor the station pinned at enrollment.
    assert root_cert.public_bytes(Encoding.DER) == renewal_pki.root.cert.public_bytes(
        Encoding.DER
    )

    # The renewed leaf carries the SAME key: SPKI(leaf) == SPKI(CSR) == pin.
    new_spki = hashlib.sha256(
        new_leaf.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
    ).hexdigest()
    assert new_spki == station.spki_sha256

    now = datetime.now(timezone.utc)
    assert new_leaf.not_valid_before_utc <= now <= new_leaf.not_valid_after_utc


def test_renew_spki_mismatch_returns_403_and_signs_nothing(
    client: TestClient, db: Session, renewal_pki: _RenewalPKI
) -> None:
    """A CSR over a DIFFERENT key than the presented cert is not renewal — it
    is re-enrollment, which stays operator-gated. 403, nothing issued, and the
    recorded pin is never rotated.
    """
    leaf = make_leaf(renewal_pki.intermediate, "station-abc123.local")
    station = _enrolled_station(db, leaf)
    other_key = ed25519.Ed25519PrivateKey.generate()
    sign_calls: list[str] = []

    async def _tracking_sign(csr: str) -> SignedCertificate:
        sign_calls.append(csr)
        return _signed_cert_for(csr, renewal_pki.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign):
        r = client.post(
            RENEW_URL,
            json={"csr_pem": _csr_for_key(other_key)},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 403, r.text
    assert sign_calls == []  # step-ca never called; nothing issued
    db.expire_all()
    refetched = db.get(Station, station.id)
    assert refetched is not None
    assert refetched.spki_sha256 == leaf.spki_sha256_hex  # no re-pin


def test_renew_unknown_station_cert_returns_generic_401(
    client: TestClient, renewal_pki: _RenewalPKI
) -> None:
    """A device-CA-signed leaf with no enrolled Station gets the same generic
    401 as every other mTLS failure (no station-existence leak)."""
    leaf = make_leaf(renewal_pki.intermediate, "ghost.local")
    r = client.post(
        RENEW_URL,
        json={"csr_pem": _csr_for_key(leaf.key)},
        headers=_cert_header(leaf),
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "client certificate required"


def test_renew_revoked_station_returns_401_and_signs_nothing(
    client: TestClient, db: Session, renewal_pki: _RenewalPKI
) -> None:
    """A revoked station's leaf no longer authenticates: generic 401, no cert."""
    leaf = make_leaf(renewal_pki.intermediate, "station-revoked.local")
    station = _enrolled_station(db, leaf)
    station.revoked_at = datetime.now(timezone.utc)
    db.add(station)
    db.commit()
    sign_calls: list[str] = []

    async def _tracking_sign(csr: str) -> SignedCertificate:
        sign_calls.append(csr)
        return _signed_cert_for(csr, renewal_pki.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign):
        r = client.post(
            RENEW_URL,
            json={"csr_pem": _csr_for_key(leaf.key)},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 401
    assert r.json()["detail"] == "client certificate required"
    assert sign_calls == []


def test_renew_without_cert_header_returns_401(client: TestClient) -> None:
    """No client cert: in prod the mTLS edge refuses the handshake; the
    backend-level guard is the same generic 401 as the upload path."""
    r = client.post(
        RENEW_URL,
        json={"csr_pem": _csr_for_key(ed25519.Ed25519PrivateKey.generate())},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "client certificate required"


def test_renew_garbage_csr_returns_422_and_signs_nothing(
    client: TestClient, db: Session, renewal_pki: _RenewalPKI
) -> None:
    leaf = make_leaf(renewal_pki.intermediate, "station-garbage.local")
    _enrolled_station(db, leaf)
    sign_calls: list[str] = []

    async def _tracking_sign(csr: str) -> SignedCertificate:
        sign_calls.append(csr)
        return _signed_cert_for(csr, renewal_pki.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign):
        r = client.post(
            RENEW_URL,
            json={"csr_pem": "not a certificate signing request"},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "invalid CSR"
    assert sign_calls == []


def test_renew_csr_with_invalid_self_signature_returns_422(
    client: TestClient, db: Session, renewal_pki: _RenewalPKI
) -> None:
    """Proof of possession: a CSR whose self-signature does not verify is
    refused even though its SPKI matches the presented cert."""
    leaf = make_leaf(renewal_pki.intermediate, "station-pop.local")
    _enrolled_station(db, leaf)

    csr = x509.load_pem_x509_csr(_csr_for_key(leaf.key).encode("utf-8"))
    der = bytearray(csr.public_bytes(Encoding.DER))
    der[-1] ^= 0x01  # corrupt the trailing signature byte; DER still parses
    tampered = x509.load_der_x509_csr(bytes(der))
    assert not tampered.is_signature_valid  # the tamper really broke PoP
    tampered_pem = tampered.public_bytes(Encoding.PEM).decode("utf-8")
    sign_calls: list[str] = []

    async def _tracking_sign(csr_pem: str) -> SignedCertificate:
        sign_calls.append(csr_pem)
        return _signed_cert_for(csr_pem, renewal_pki.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign):
        r = client.post(
            RENEW_URL,
            json={"csr_pem": tampered_pem},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "invalid CSR"
    assert sign_calls == []


def test_renew_step_ca_failure_returns_502(
    client: TestClient, db: Session, renewal_pki: _RenewalPKI
) -> None:
    """A step-ca failure surfaces exactly as on the confirm path: generic 502
    (transient for the station, which retries with backoff)."""
    leaf = make_leaf(renewal_pki.intermediate, "station-502.local")
    _enrolled_station(db, leaf)

    async def _raise(_csr: str) -> SignedCertificate:
        raise httpx.HTTPError("step-ca exploded")

    with patch("app.api.routes.enrollment.sign_device_csr", new=_raise):
        r = client.post(
            RENEW_URL,
            json={"csr_pem": _csr_for_key(leaf.key)},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 502
    assert r.json()["detail"] == "certificate issuance failed"


def test_renew_writes_renewal_succeeded_audit(
    client: TestClient, db: Session, renewal_pki: _RenewalPKI
) -> None:
    """Each issuance writes one renewal_succeeded row: station, pin, source,
    user-agent — no session and no human actor (unattended)."""
    leaf = make_leaf(renewal_pki.intermediate, "station-audit.local")
    station = _enrolled_station(db, leaf)

    async def _fake_sign(csr: str) -> SignedCertificate:
        return _signed_cert_for(csr, renewal_pki.intermediate)

    with patch("app.api.routes.enrollment.sign_device_csr", new=_fake_sign):
        r = client.post(
            RENEW_URL,
            json={"csr_pem": _csr_for_key(leaf.key)},
            headers={**_cert_header(leaf), "User-Agent": "perchpub-station/1.2"},
        )
    assert r.status_code == 200, r.text

    rows = db.exec(
        select(EnrollmentAudit).where(
            EnrollmentAudit.station_id == station.id,
            EnrollmentAudit.event == EnrollmentAuditEvent.renewal_succeeded,
        )
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.spki_sha256 == station.spki_sha256
    assert row.session_id is None  # unattended: no enrollment session involved
    assert row.actor_user_id is None  # the station itself acts, no user
    assert row.source
    assert row.user_agent == "perchpub-station/1.2"


def test_renew_beyond_station_rate_returns_429_without_signing(
    client: TestClient,
    db: Session,
    renewal_pki: _RenewalPKI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Renewals beyond the per-station rate are 429'd before signing. The
    station treats 429 as terminal-for-this-attempt and backs off (≤1 h)."""
    monkeypatch.setattr(settings, "ENROLLMENT_RENEW_RATE_PER_MIN", 1)
    leaf = make_leaf(renewal_pki.intermediate, "station-rl.local")
    _enrolled_station(db, leaf)
    sign_calls: list[str] = []

    async def _tracking_sign(csr: str) -> SignedCertificate:
        sign_calls.append(csr)
        return _signed_cert_for(csr, renewal_pki.intermediate)

    with (
        _fake_ratelimit_backend(),
        patch("app.api.routes.enrollment.sign_device_csr", new=_tracking_sign),
    ):
        ok = client.post(
            RENEW_URL,
            json={"csr_pem": _csr_for_key(leaf.key)},
            headers=_cert_header(leaf),
        )
        assert ok.status_code == 200, ok.text
        r = client.post(
            RENEW_URL,
            json={"csr_pem": _csr_for_key(leaf.key)},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 429
    assert r.headers.get("retry-after") is not None
    assert len(sign_calls) == 1  # only the first renewal signed


def test_openapi_pins_renewal_contract_schemas() -> None:
    """The perchstation repo mirrors openapi.json field-for-field: schema names
    RenewalRequest/RenewalResponse and their required fields are load-bearing."""
    from app.main import app

    spec = app.openapi()
    schemas = spec["components"]["schemas"]

    req = schemas["RenewalRequest"]
    assert set(req["properties"]) == {"csr_pem"}
    assert req.get("required") == ["csr_pem"]
    assert req["properties"]["csr_pem"]["type"] == "string"

    resp = schemas["RenewalResponse"]
    assert set(resp["properties"]) == {"certificate_pem", "ca_chain_pem"}
    assert set(resp.get("required", [])) == {"certificate_pem", "ca_chain_pem"}
    assert resp["properties"]["certificate_pem"]["type"] == "string"
    assert resp["properties"]["ca_chain_pem"]["type"] == "string"

    post = spec["paths"]["/api/v1/enrollment/renew"]["post"]
    req_ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert req_ref.endswith("/RenewalRequest")
    ok_ref = post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ok_ref.endswith("/RenewalResponse")
