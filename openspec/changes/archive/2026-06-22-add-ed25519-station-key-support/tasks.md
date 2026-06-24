## 1. Parametrize the CSR test helper

- [x] 1.1 In `backend/tests/utils/mtls.py`, add `from cryptography.hazmat.primitives.asymmetric import ed25519` and turn `make_csr` (currently L86-93) into `make_csr(common_name="device-001.local", *, key_type="ed25519")` accepting `"ed25519"` or `"ec"`, selecting `(key, algorithm)` together: Ed25519 → `ed25519.Ed25519PrivateKey.generate()` + `.sign(key, None)`; EC → `ec.generate_private_key(ec.SECP256R1())` + `.sign(key, hashes.SHA256())`. **Default `key_type="ed25519"`** so the helper default reflects the new recommended default; give `make_leaf` the same param/default for its subject key. `make_ca` (the issuer) stays EC P-256.
- [x] 1.2 Widen the key type annotations so `mypy` (via `bash scripts/lint.sh`) stays green: `TestCA.key` (L26) and `TestLeaf.key` (L36), currently `EllipticCurvePrivateKey`, become a union (`EllipticCurvePrivateKey | ed25519.Ed25519PrivateKey`) or the `CertificateIssuerPrivateKeyTypes` alias.
- [x] 1.3 Confirm the existing un-parametrized callers in `test_enrollment.py` (`make_csr()` in the 404/401/403 tests, L83/L172) still pass now that they generate Ed25519 CSRs — they assert no key type, only a valid CSR.
- [x] 1.4 Run `cd backend && bash scripts/lint.sh` and confirm mypy + ruff pass with the widened annotations and the new helper.

## 2. Parametrize the enrollment route tests

- [x] 2.1 In `backend/tests/api/routes/test_enrollment.py`, parametrize the happy-path enrollment test (`test_full_enrollment_creates_station_with_spki_pin`, L97) with `@pytest.mark.parametrize("key_type", ["ec", "ed25519"])`, passing `key_type` through to `make_csr`. `_signed_cert_for` (L42-60) already copies `csr.public_key()` into the fake leaf, so an Ed25519 CSR yields an Ed25519-SPKI leaf with no further change.
- [x] 2.2 Assert, for the Ed25519 case, that the leaf parsed from `certificate_pem` carries an Ed25519 public key (`isinstance(leaf.public_key(), Ed25519PublicKey)`) and that `Station.spki_sha256` equals `SHA-256` of the leaf SPKI (DER).
- [x] 2.3 Run the enrollment tests and confirm both `key_type` cases pass.

## 3. Parametrize the step-ca client tests

- [x] 3.1 In `backend/tests/ca/test_step_ca_client.py`, give the device-CSR helper (`_make_csr`, L67-74) an Ed25519 variant via the same `key_type` switch. Leave the `provisioner_jwk` fixture (L33) as ES256 — the provisioner key type is independent of the device key type.
- [x] 3.2 Parametrize the test(s) asserting the OTT `sha` claim equals `SHA-256` of the CSR SPKI over both `"ec"` and `"ed25519"`; confirm the claim computation is unchanged for Ed25519.

## 4. Prove the real step-ca path in the integration smoke test

- [x] 4.1 In `backend/tests/integration/test_compose_smoke.py`, add `from cryptography.hazmat.primitives.asymmetric import ed25519` and give `_make_csr` (L35-44) an Ed25519 branch (`ed25519.Ed25519PrivateKey.generate()` + `.sign(private_key, None)`).
- [x] 4.2 Parametrize `test_compose_smoke_full_ingest_flow` (or add an Ed25519 sibling) over `key_type` so the enroll → real-step-ca-sign → SPKI-pin → hand-stuffed mTLS upload flow runs with an Ed25519 station key. Assert the returned `certificate_pem` parses to an Ed25519 leaf and the upload returns `200`. This is the case that proves the **deployed** step-ca default template issues an Ed25519 leaf.
- [x] 4.3 Run the integration smoke suite (`scripts/integration-test.sh`) and confirm both key types pass end-to-end.

## 5. Document Ed25519 station key generation (recommended default)

- [x] 5.1 Add a device-key generation section to the operator-facing station-enrollment runbook (`deployment.md` "Setting up the CA for mTLS" and/or `deploy/terraform/README.md` post-apply smoke step, which already references `device.crt`/`device.key`), **leading with Ed25519 as the recommended default**: `openssl genpkey -algorithm ed25519 -out device.key` then `openssl req -new -key device.key -subj '/CN=station-01' -out device.csr` (no `-sha256` for Ed25519). Document EC P-256 as the supported alternative below it.
- [x] 5.2 Add the Python `cryptography` recipe for both types, Ed25519 first, calling out that Ed25519 CSRs sign with `.sign(key, None)` (no hash) while EC/RSA pass `hashes.SHA256()`. State that Ed25519 is the recommended default and EC P-256 remains supported.
- [x] 5.3 (Optional, accuracy) Fix the misleading EC-only comment at `backend/app/ca/step_ca_client.py:71` (mentions only EC P-256/RSA) and the EC-only lines in `PLAN.md` (L322 deploy-smoke keygen, L419-421 verify note) to include Ed25519. Behavior is unchanged; this only prevents readers inferring EC is required.

## 6. Verify and gate

- [x] 6.1 Run `cd backend && bash scripts/lint.sh` and `bash scripts/test.sh`; confirm all unit tests (including the new Ed25519 parametrizations) and lint pass.
- [x] 6.2 Confirm the working-tree diff touches **only** tests and docs (plus the optional comment fixes) — no change under `backend/app/**`, `docker-compose*.yml`, or `deploy/traefik/**`. If any production change turns out to be required, stop and surface it (the proposal asserts none is).
- [x] 6.3 Run `openspec validate add-ed25519-station-key-support --strict` and confirm the change validates.
