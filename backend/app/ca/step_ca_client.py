"""step-ca integration utilities for device certificate enrollment.

This module encapsulates talking to step-ca for signing device CSRs
using the JWK-based provisioner configured in settings.

The implementation follows step-ca's HTTP API as documented at:
https://github.com/smallstep/certificates/tree/master/authority/provisioner#jwk
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.core.config import settings


@dataclass
class SignedCertificate:
    certificate_pem: str
    ca_chain_pem: str
    not_before: datetime
    not_after: datetime


def _load_jwk() -> dict[str, Any]:
    """Load the JWK for the device-enrollment provisioner from disk.

    The path is provided via settings.STEP_CA_JWK_PATH and should be mounted
    as a secret in production.
    """

    jwk_path = Path(settings.STEP_CA_JWK_PATH)
    jwk_data = jwk_path.read_text(encoding="utf-8")
    # PyJWT accepts a JWK JSON string or dict; we pass the string directly.
    # Consumers may choose to parse it into dict if desired.
    return jwt.api_jwk.PyJWK.from_json(jwk_data).to_dict()


def _build_provisioner_jwt(*, lifetime: int = 300) -> str:
    """Create a short-lived JWT for the JWK provisioner.

    This follows the pattern used by the `step` CLI when talking to step-ca.
    """

    now = datetime.now(UTC)
    exp = now + timedelta(seconds=lifetime)

    jwk_dict = _load_jwk()
    key = jwt.supported_key_types()["RSA"].from_dict(jwk_dict)

    payload: dict[str, Any] = {
        "iss": settings.STEP_CA_PROVISIONER_NAME,
        "sub": settings.STEP_CA_PROVISIONER_NAME,
        "aud": f"{settings.STEP_CA_URL}/1.0/sign",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    headers: dict[str, Any] = {}
    if settings.STEP_CA_PROVISIONER_KID:
        headers["kid"] = settings.STEP_CA_PROVISIONER_KID

    token = jwt.encode(
        payload, key, algorithm=jwk_dict.get("alg", "RS256"), headers=headers
    )
    return token


async def sign_device_csr(csr_pem: str) -> SignedCertificate:
    """Send CSR to step-ca and return the signed certificate and chain.

    This uses the step-ca `1.0/sign` endpoint with a JWK provisioner JWT for
    authentication.
    """

    provisioner_token = _build_provisioner_jwt()

    request_body: dict[str, Any] = {
        "csr": csr_pem,
        "ott": provisioner_token,
    }

    async with httpx.AsyncClient(base_url=settings.STEP_CA_URL, timeout=10.0) as client:
        response = await client.post("/1.0/sign", json=request_body)
        response.raise_for_status()
        data = response.json()

    cert_pem = data.get("crt") or data.get("certificate")
    ca_chain_pem = data.get("ca") or data.get("chain", "")
    not_before_str = data.get("notBefore")
    not_after_str = data.get("notAfter")

    # step-ca uses RFC3339 timestamps; datetime.fromisoformat handles the
    # common subset, but we fall back defensively if parsing fails.
    def _parse_ts(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(UTC)

    not_before = _parse_ts(not_before_str)
    not_after = _parse_ts(not_after_str)

    return SignedCertificate(
        certificate_pem=cert_pem,
        ca_chain_pem=ca_chain_pem,
        not_before=not_before,
        not_after=not_after,
    )
