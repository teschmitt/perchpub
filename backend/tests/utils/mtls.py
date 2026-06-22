"""Test helpers for building in-memory CA / leaf certs and CSRs.

mTLS-03 uses these to fake a step-ca response (sign_device_csr returns a
SignedCertificate built around `make_leaf`). mTLS-04 and mTLS-06 reuse
the same builders to populate `X-Forwarded-Tls-Client-Cert` and the
device CA file referenced by `DEVICE_CLIENT_CA_CERT_PATH`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID

# Device/subject keys may be Ed25519 (the recommended default for new
# stations) or EC P-256 (the supported alternative). The CA issuer key
# stays EC P-256, but the dataclass fields are widened to the union so
# mypy accepts an Ed25519 leaf key.
DeviceKey = EllipticCurvePrivateKey | ed25519.Ed25519PrivateKey


@dataclass
class TestCA:
    cert: x509.Certificate
    key: DeviceKey

    @property
    def cert_pem(self) -> str:
        return self.cert.public_bytes(Encoding.PEM).decode("utf-8")


@dataclass
class TestLeaf:
    cert: x509.Certificate
    key: DeviceKey

    @property
    def cert_pem(self) -> str:
        return self.cert.public_bytes(Encoding.PEM).decode("utf-8")

    @property
    def spki_sha256_hex(self) -> str:
        spki_der = self.cert.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        return hashlib.sha256(spki_der).hexdigest()


def make_ca(common_name: str = "PerchPub Test Device CA") -> TestCA:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return TestCA(cert=cert, key=key)


def _generate_device_key(key_type: str) -> DeviceKey:
    """Generate a device/subject keypair of the requested type.

    Ed25519 is the recommended default for new stations; EC P-256 stays
    fully supported. The CA issuer key (``make_ca``) is independent and
    always EC P-256.
    """
    if key_type == "ed25519":
        return ed25519.Ed25519PrivateKey.generate()
    if key_type == "ec":
        return ec.generate_private_key(ec.SECP256R1())
    raise ValueError(f"unsupported key_type: {key_type!r}")


def make_leaf(
    ca: TestCA, common_name: str = "device-001.local", *, key_type: str = "ed25519"
) -> TestLeaf:
    key = _generate_device_key(key_type)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca.cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca.key, hashes.SHA256())
    )
    return TestLeaf(cert=cert, key=key)


def make_csr(
    common_name: str = "device-001.local", *, key_type: str = "ed25519"
) -> str:
    key = _generate_device_key(key_type)
    # Ed25519 forbids a hash algorithm; EC/RSA require one. cryptography
    # raises ValueError if a hash is passed for Ed25519, so select the
    # (key, algorithm) pair together.
    algorithm = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, algorithm)
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")
