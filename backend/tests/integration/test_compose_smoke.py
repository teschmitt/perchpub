"""WI-INT-5: full-stack ingest path against the compose stack.

The deploy-day rehearsal. Brings the test compose stack up via
`scripts/integration-test.sh` (db + redis + minio + step-ca + backend +
worker), then walks the operator-login → enrollment → cert → upload →
classify-task flow end-to-end via HTTP against the host-mapped backend
on :8001. The mTLS handshake is hand-stuffed via
`X-Forwarded-Tls-Client-Cert` (prod-mTLS Traefik wiring is the deferred
follow-up to mTLS-05; see PLAN.md).

Catches what the per-route TestClient suite can't: the docker-compose
wiring itself (FU-15 env_file injection, prestart sequencing, init
container ordering, step-ca's narrowed subpath mounts from FU-13), plus
backend↔worker handoff over the real Redis.
"""

import hashlib
import time
import urllib.parse
import uuid

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.x509.oid import NameOID
from sqlmodel import Session

from app.core.config import settings
from app.models.species import Species

_BASE_URL = "http://localhost:8001"
_POLL_TIMEOUT_S = 60.0


def _make_csr(common_name: str, *, key_type: str = "ed25519") -> str:
    # Ed25519 is the recommended default device key; EC P-256 stays supported.
    # Ed25519 signs the CSR with no hash algorithm; EC/RSA require one.
    private_key: ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey
    if key_type == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
        algorithm = None
    elif key_type == "ec":
        private_key = ec.generate_private_key(ec.SECP256R1())
        algorithm = hashes.SHA256()
    else:
        raise ValueError(f"unsupported key_type: {key_type!r}")
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(private_key, algorithm)
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")


@pytest.mark.parametrize("key_type", ["ec", "ed25519"])
def test_compose_smoke_full_ingest_flow(
    db: Session,
    video_bytes: bytes,
    key_type: str,
) -> None:
    # Seed both labels so the random-weight classifier resolves either way.
    # Idempotent w.r.t. test_worker_consumer adding the same rows: Species
    # has no unique constraint on classification_id; _lookup_species_id
    # returns the first match.
    db.add(Species(scientific_name="Smoke Negative", classification_id=0))
    db.add(Species(scientific_name="Smoke Positive", classification_id=1))
    db.commit()

    with httpx.Client(base_url=_BASE_URL, timeout=30.0) as client:
        health = client.get("/api/v1/utils/health-check/")
        assert health.status_code == 200

        # Operator login (the prestart-seeded sentinel superuser).
        login = client.post(
            "/api/v1/login/access-token",
            data={
                "username": settings.FIRST_SUPERUSER,
                "password": settings.FIRST_SUPERUSER_PASSWORD,
            },
        )
        assert login.status_code == 200, login.text
        bearer = login.json()["access_token"]
        operator_headers = {"Authorization": f"Bearer {bearer}"}

        # Operator opens an enrollment session for a new station.
        create = client.post(
            "/api/v1/enrollment/create",
            json={"latitude": 12.34, "longitude": 56.78},
            headers=operator_headers,
        )
        assert create.status_code == 200, create.text
        enrollment_session = create.json()

        # Station-side: generate keypair + CSR, claim the session.
        csr_pem = _make_csr(
            common_name=f"smoke-{uuid.uuid4().hex[:8]}", key_type=key_type
        )
        confirm = client.post(
            f"/api/v1/enrollment/confirm/{enrollment_session['session_id']}",
            json={
                "auth_token": enrollment_session["auth_token"],
                "csr_pem": csr_pem,
            },
        )
        assert confirm.status_code == 200, confirm.text
        enrollment = confirm.json()
        assert enrollment["success"] is True
        assert enrollment["certificate_pem"]
        assert enrollment["station_id"]

        # The real step-ca must preserve the CSR's key type in the issued
        # leaf — this is the case that proves the deployed JWK provisioner's
        # default template issues an Ed25519 leaf (not just EC P-256).
        leaf = x509.load_pem_x509_certificate(
            enrollment["certificate_pem"].encode("utf-8")
        )
        expected_pub = (
            Ed25519PublicKey if key_type == "ed25519" else EllipticCurvePublicKey
        )
        assert isinstance(leaf.public_key(), expected_pub)

        # Interop invariant (design D3 / Risks): the QR carries only the root
        # pin; /confirm returns the full chain (intermediate + root). This is
        # the assertion that proves a station's root-pin verification will
        # succeed against the deployed step-ca — build leaf -> intermediate ->
        # root and assert the root's SPKI-SHA256 equals the create-time ca_pin.
        ca_pin = enrollment_session["ca_pin"]
        assert len(ca_pin) == 64 and ca_pin == ca_pin.lower()

        chain = x509.load_pem_x509_certificates(
            enrollment["ca_chain_pem"].encode("utf-8")
        )
        assert len(chain) == 2, "expected issuing intermediate + root"
        intermediate_cert, root_cert = chain

        # leaf -> intermediate -> root builds (each cert issued by the next).
        leaf.verify_directly_issued_by(intermediate_cert)
        intermediate_cert.verify_directly_issued_by(root_cert)

        # The issuing intermediate is a usable CA (cA=TRUE + keyCertSign).
        basic = intermediate_cert.extensions.get_extension_for_class(
            x509.BasicConstraints
        )
        assert basic.value.ca is True
        key_usage = intermediate_cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert key_usage.value.key_cert_sign is True

        # The pinned root equals the chain's root by SPKI-SHA256.
        root_spki = root_cert.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        assert hashlib.sha256(root_spki).hexdigest() == ca_pin

        # Hand-stuffed mTLS handshake: the cert PEM URL-encoded into the
        # `X-Forwarded-Tls-Client-Cert` header, mirroring what Traefik's
        # `passTLSClientCert.pem` middleware would emit on the prod mtls
        # entrypoint.
        cert_header = urllib.parse.quote(enrollment["certificate_pem"])
        upload = client.post(
            "/api/v1/upload/",
            files={"file": ("smoke.mp4", video_bytes, "video/mp4")},
            headers={settings.MTLS_CLIENT_CERT_HEADER: cert_header},
        )
        assert upload.status_code == 200, upload.text
        task_id = upload.json()["id"]

        # Poll until the worker container picks the task off Redis,
        # downloads the upload from Minio, runs inference against the
        # seeded TF Lite fixture, and persists an Observation.
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        latest: dict[str, object] = {}
        while time.monotonic() < deadline:
            poll = client.get(f"/api/v1/classify-task/{task_id}")
            assert poll.status_code == 200, poll.text
            latest = poll.json()
            if latest["status"] in ("Success", "Failed"):
                break
            time.sleep(0.5)
        assert latest.get("status") == "Success", latest

        observation = latest.get("observation")
        assert observation is not None
        # ObservationPublic nests the StationPublic object, no flat station_id.
        assert observation["station"]["id"] == enrollment["station_id"]
