"""step-ca integration utilities for device certificate enrollment.

Talks to step-ca's JWK provisioner via the HTTP /1.0/sign endpoint. The
OTT JWT structure follows what the `step` CLI generates:

    header:  { kid, alg, typ }
    payload: { iss, sub, aud, sha, iat, nbf, exp }

`sha` is the hex sha256 of the CSR's SubjectPublicKeyInfo (DER); step-ca
checks it to bind one OTT to one specific CSR. See:
https://github.com/smallstep/certificates/tree/master/authority/provisioner#jwk
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID

from app.core.config import settings


@dataclass
class SignedCertificate:
    certificate_pem: str
    ca_chain_pem: str
    not_before: datetime
    not_after: datetime


def _load_provisioner_jwk() -> jwt.PyJWK:
    """Load the JWK for the device-enrollment provisioner from disk.

    step-ca emits the JWK as JSON when the provisioner is created (see
    `step ca provisioner add --create`). The path is configured via
    settings.STEP_CA_JWK_PATH.
    """
    return jwt.PyJWK.from_json(
        Path(settings.STEP_CA_JWK_PATH).read_text(encoding="utf-8")
    )


def _csr_spki_sha256_hex(csr_pem: str) -> str:
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    spki_der = csr.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(spki_der).hexdigest()


def _csr_subject_common_name(csr_pem: str) -> str | None:
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cn_attrs:
        return None
    return str(cn_attrs[0].value)


def _build_provisioner_jwt(csr_pem: str, *, lifetime: int = 300) -> str:
    """Create a short-lived OTT JWT bound to this CSR for the JWK provisioner.

    The signing algorithm is read from the JWK itself (alg/kty), so the same
    code path works for EC P-256 (step-ca's default) and RSA alike.
    """
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=lifetime)

    jwk = _load_provisioner_jwk()
    sub = _csr_subject_common_name(csr_pem) or settings.STEP_CA_PROVISIONER_NAME

    payload: dict[str, Any] = {
        "iss": settings.STEP_CA_PROVISIONER_NAME,
        "sub": sub,
        "aud": f"{settings.STEP_CA_URL}/1.0/sign",
        "sha": _csr_spki_sha256_hex(csr_pem),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    headers: dict[str, Any] = {}
    if jwk.key_id:
        headers["kid"] = jwk.key_id

    return jwt.encode(payload, jwk.key, algorithm=jwk.algorithm_name, headers=headers)


async def sign_device_csr(csr_pem: str) -> SignedCertificate:
    """Send CSR to step-ca; return the signed leaf and CA chain."""
    request_body: dict[str, Any] = {
        "csr": csr_pem,
        "ott": _build_provisioner_jwt(csr_pem),
    }

    async with httpx.AsyncClient(base_url=settings.STEP_CA_URL, timeout=10.0) as client:
        response = await client.post("/1.0/sign", json=request_body)
        response.raise_for_status()
        data = response.json()

    cert_pem = data.get("crt") or data.get("certificate")
    ca_chain_pem = data.get("ca") or data.get("chain", "")

    def _parse_ts(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    return SignedCertificate(
        certificate_pem=cert_pem,
        ca_chain_pem=ca_chain_pem,
        not_before=_parse_ts(data.get("notBefore")),
        not_after=_parse_ts(data.get("notAfter")),
    )
