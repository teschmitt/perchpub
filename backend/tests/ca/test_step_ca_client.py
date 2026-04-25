"""Tests for the step-ca JWK provisioner OTT JWT structure.

The OTT JWT is what step-ca actually verifies on the wire, so the test
asserts the header `kid`, the algorithm matches the JWK, and the body
carries the CSR-bound `sha` claim plus iss/sub/aud.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID
from jwt.algorithms import ECAlgorithm

from app.ca.step_ca_client import sign_device_csr
from app.core.config import settings


@pytest.fixture
def provisioner_jwk(tmp_path: Path) -> dict[str, Any]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwk_dict: dict[str, Any] = json.loads(ECAlgorithm.to_jwk(private_key))
    jwk_dict["alg"] = "ES256"
    jwk_dict["kid"] = "test-kid-abc"
    jwk_path = tmp_path / "provisioner.jwk"
    jwk_path.write_text(json.dumps(jwk_dict), encoding="utf-8")
    return {"path": jwk_path, "private_key": private_key, "dict": jwk_dict}


def _make_csr(common_name: str = "device-001.local") -> str:
    private_key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        )
        .sign(private_key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def test_sign_device_csr_builds_correct_ott(
    provisioner_jwk: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "STEP_CA_JWK_PATH", str(provisioner_jwk["path"]))
    monkeypatch.setattr(settings, "STEP_CA_PROVISIONER_NAME", "device-enrollment")
    monkeypatch.setattr(settings, "STEP_CA_URL", "http://step-ca.test:9000")

    csr_pem = _make_csr("device-001.local")
    captured: dict[str, Any] = {}

    async def fake_post(self: Any, url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        captured["body"] = kwargs.get("json")

        class _Resp:
            def json(self) -> dict[str, Any]:
                return {
                    "crt": "-----BEGIN CERTIFICATE-----\nfake-leaf\n-----END CERTIFICATE-----\n",
                    "ca": "-----BEGIN CERTIFICATE-----\nfake-ca\n-----END CERTIFICATE-----\n",
                    "notBefore": "2026-04-25T12:00:00Z",
                    "notAfter": "2026-04-26T12:00:00Z",
                }

            def raise_for_status(self) -> None:
                return None

        return _Resp()

    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(sign_device_csr(csr_pem))

    assert captured["url"] == "/1.0/sign"
    assert captured["body"]["csr"] == csr_pem
    token = captured["body"]["ott"]

    headers = jwt.get_unverified_header(token)
    assert headers["kid"] == "test-kid-abc"
    assert headers["alg"] == "ES256"

    payload = jwt.decode(
        token,
        key=provisioner_jwk["private_key"].public_key(),
        algorithms=["ES256"],
        audience="http://step-ca.test:9000/1.0/sign",
    )
    assert payload["iss"] == "device-enrollment"
    assert payload["sub"] == "device-001.local"
    assert payload["aud"] == "http://step-ca.test:9000/1.0/sign"

    spki_der = (
        x509.load_pem_x509_csr(csr_pem.encode())
        .public_key()
        .public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    )
    assert payload["sha"] == hashlib.sha256(spki_der).hexdigest()

    assert result.certificate_pem.startswith("-----BEGIN CERTIFICATE-----")
    assert result.ca_chain_pem.startswith("-----BEGIN CERTIFICATE-----")


def test_sign_device_csr_falls_back_to_provisioner_name_when_csr_has_no_cn(
    provisioner_jwk: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "STEP_CA_JWK_PATH", str(provisioner_jwk["path"]))
    monkeypatch.setattr(settings, "STEP_CA_PROVISIONER_NAME", "device-enrollment")
    monkeypatch.setattr(settings, "STEP_CA_URL", "http://step-ca.test:9000")

    private_key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([]))
        .sign(private_key, hashes.SHA256())
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    captured: dict[str, Any] = {}

    async def fake_post(self: Any, url: str, **kwargs: Any) -> Any:
        captured["body"] = kwargs.get("json")

        class _Resp:
            def json(self) -> dict[str, Any]:
                return {
                    "crt": "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n",
                    "ca": "-----BEGIN CERTIFICATE-----\nfake-ca\n-----END CERTIFICATE-----\n",
                }

            def raise_for_status(self) -> None:
                return None

        return _Resp()

    with patch("httpx.AsyncClient.post", new=fake_post):
        asyncio.run(sign_device_csr(csr_pem))

    payload = jwt.decode(
        captured["body"]["ott"],
        key=provisioner_jwk["private_key"].public_key(),
        algorithms=["ES256"],
        audience="http://step-ca.test:9000/1.0/sign",
    )
    assert payload["sub"] == "device-enrollment"
