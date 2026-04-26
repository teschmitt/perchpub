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
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID


@dataclass
class TestCA:
    cert: x509.Certificate
    key: EllipticCurvePrivateKey

    @property
    def cert_pem(self) -> str:
        return self.cert.public_bytes(Encoding.PEM).decode("utf-8")


@dataclass
class TestLeaf:
    cert: x509.Certificate
    key: EllipticCurvePrivateKey

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


def make_leaf(ca: TestCA, common_name: str = "device-001.local") -> TestLeaf:
    key = ec.generate_private_key(ec.SECP256R1())
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


def make_csr(common_name: str = "device-001.local") -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")
