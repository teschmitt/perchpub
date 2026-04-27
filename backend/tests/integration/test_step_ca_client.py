"""WI-INT-4: real CSR signing against the step-ca container.

Exercises `app.ca.step_ca_client.sign_device_csr` against a step-ca that
was bootstrapped by the test compose stack (FU-19's
`DOCKER_STEPCA_INIT_PASSWORD` + the existing `step-ca-provisioner-init`
script). `scripts/integration-test.sh` extracts the resulting JWK +
root cert out of the container and exports `STEP_CA_JWK_PATH` /
`STEP_CA_ROOT_CERT_PATH` before pytest runs.

Catches: PyJWT 2.x API drift, JWK encoding mismatches, step-ca API
version drift, `sha`-claim binding regressions — none of which the
mocked unit tests in `tests/ca/test_step_ca_client.py` can see.
"""

import asyncio
import hashlib
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID

from app.ca.step_ca_client import sign_device_csr
from tests.utils.mtls import make_csr


def _spki_sha256_hex(public_key: object) -> str:
    spki_der = public_key.public_bytes(  # type: ignore[attr-defined]
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(spki_der).hexdigest()


def test_sign_device_csr_returns_leaf_bound_to_csr() -> None:
    csr_pem = make_csr(common_name="device-int-0001.local")
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    csr_spki_hex = _spki_sha256_hex(csr.public_key())

    result = asyncio.run(sign_device_csr(csr_pem))

    leaf = x509.load_pem_x509_certificate(result.certificate_pem.encode("utf-8"))
    # sha-claim binding: step-ca only issues a leaf whose SPKI hashes
    # to the OTT's `sha` claim. Reaching this assertion means the OTT
    # PyJWT-encoded fine, the JWK loaded fine, and step-ca accepted
    # the binding.
    assert _spki_sha256_hex(leaf.public_key()) == csr_spki_hex

    # CSR subject CN propagates to the leaf.
    leaf_cn_attrs = leaf.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    assert leaf_cn_attrs
    assert leaf_cn_attrs[0].value == "device-int-0001.local"

    # Issuer is step-ca's intermediate (`DOCKER_STEPCA_INIT_NAME=PerchPub CA`
    # → "PerchPub CA Intermediate CA").
    issuer_cn_attrs = leaf.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
    assert issuer_cn_attrs
    assert "Intermediate" in str(issuer_cn_attrs[0].value)

    # step-ca's default leaf lifetime is 24h. Allow a generous window for
    # clock skew and step-ca's NotBefore backdating.
    lifetime = leaf.not_valid_after_utc - leaf.not_valid_before_utc
    assert timedelta(hours=23) < lifetime < timedelta(hours=25)

    # CA chain parses and is the intermediate that signed the leaf.
    assert result.ca_chain_pem
    intermediate = x509.load_pem_x509_certificate(
        result.ca_chain_pem.encode("utf-8")
    )
    assert leaf.issuer == intermediate.subject

    # not_before / not_after came back populated (sign_device_csr's
    # _parse_ts fallback would mask broken parsing otherwise).
    assert result.not_before < result.not_after
