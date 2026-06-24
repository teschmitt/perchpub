## Context

A station enrolls by generating a keypair + CSR and POSTing the CSR to `POST /api/v1/enrollment/confirm/{session_id}`. The backend signs the CSR via step-ca's `backend-device-enrollment` JWK provisioner, pins `SHA256(SubjectPublicKeyInfo)` of the **signed leaf** as `Station.spki_sha256`, and the station later presents that leaf for mutual-TLS uploads on the Traefik `:8443` (`mtls`) entrypoint serving `/api/v1/upload/`. Every test and the (unbuilt) reference-client plan use EC P-256 today, so Ed25519 is neither exercised nor documented.

This design records the investigation that establishes Ed25519 is already supported, so the change can be scoped to tests + docs with confidence.

## Goals / Non-Goals

**Goals:**
- Prove the full enroll → sign → SPKI-pin → mTLS-upload path with an Ed25519 station key in CI, alongside an EC P-256 regression case.
- Promote Ed25519 to the recommended default key type for new stations — via docs and the test helper — without server-side enforcement.
- Document Ed25519 device-key generation so an operator can enroll an Ed25519 station without trial and error.
- Leave no EC-P256-only-or-default assumption in the operator-facing enrollment docs.

**Non-Goals:**
- Reinitializing step-ca or changing the CA's own key type (destructive; invalidates issued certs and Traefik `caFiles`).
- Modifying Traefik TLS options or backend signing/verification code.
- **Server-side enforcement** of a single key type — a provisioner x509-template allowlist / the CA rejecting non-Ed25519 CSRs. The CA continues to accept any key type; EC P-256 stations keep working. (That enforcement is a possible **future** change, tracked separately.)

## Decisions

**Verified: no production code or config must change to *support* Ed25519** (high confidence; whole-`backend/app/**` + deploy sweep, plus an empirical venv reproduction).

- **Backend is key-type-agnostic.** CSR validation is `x509.load_pem_x509_csr(...)` only ([enrollment.py:113-114](../../../backend/app/api/routes/enrollment.py)); the SPKI pin is `sha256(public_key().public_bytes(DER, SubjectPublicKeyInfo))` in both `_csr_spki_sha256_hex` implementations ([enrollment.py:38-42](../../../backend/app/api/routes/enrollment.py), [step_ca_client.py:51-56](../../../backend/app/ca/step_ca_client.py)); mTLS identity uses `leaf.verify_directly_issued_by(ca)` + validity window + SPKI pin ([deps.py:140-149](../../../backend/app/api/deps.py)). None branch on curve, key size, or algorithm. `Station`/`Enrollment` models store only a hex pin, no key-type field.
- **The OTT signing algorithm is the CA-side provisioner key, not the device key.** `_build_provisioner_jwt` reads `jwk.algorithm_name` ([step_ca_client.py:93](../../../backend/app/ca/step_ca_client.py)) — that constrains the provisioner JWK (ES256), independent of the device leaf key type. The CSR is forwarded verbatim to `/1.0/sign`.
- **step-ca needs no change.** The provisioner is created with the stock `step ca provisioner add backend-device-enrollment --type JWK --create` ([docker-compose.yml:298](../../../docker-compose.yml)) — no `--x509-template` / `--x509-template-data` / policy flag, and no template file anywhere in the repo. step-ca 0.29.0's default JWK x509 leaf template copies the CSR public key verbatim and accepts Ed25519. An EC P-256 intermediate signing an Ed25519 leaf is valid X.509: the issuer signing-key algorithm is independent of the subject public-key algorithm.
- **Traefik needs no change.** `tls.options.mtls` pins only `clientAuthType: RequireAndVerifyClientCert` and `minVersion: VersionTLS12`, with **no** `cipherSuites`/`curvePreferences` ([dynamic.yml:18-30](../../../deploy/traefik/dynamic/dynamic.yml)). `cipherSuites`/`curvePreferences` govern the TLS key-exchange, which is orthogonal to the client *certificate's* signature scheme. `traefik:v3.7.5` is built on Go 1.24; Go's `crypto/tls` has verified Ed25519 client certs since Go 1.13, at TLS 1.2 and 1.3.
- **Empirical reproduction** (cryptography 45.0.7, the installed pin): an Ed25519 CSR → Ed25519 leaf gives `CSR-SPKI == LEAF-SPKI == mTLS-recomputed pin`, and `verify_directly_issued_by` succeeds for an Ed25519 leaf under **both** an Ed25519 CA and an EC P-256 CA.

**"Default" is a docs/tooling concept, not server behavior.** The backend is key-type-agnostic and never selects a key type — the station generates whatever keypair it likes and the server signs/pins it. So "Ed25519 is the default" is realized in exactly two places: (a) the operator docs lead with Ed25519 as the recommended path, and (b) the test CSR helper (`make_csr`/`make_leaf`) defaults its device key type to Ed25519, so un-parametrized callers exercise the Ed25519 path. EC P-256 stays a fully supported, explicitly parametrized regression case. Making the *server* prefer or require Ed25519 would mean a provisioner x509-template allowlist (enforcement) — explicitly out of scope here.

**Test approach.**
- Add a parametrized key/CSR factory to `backend/tests/utils/mtls.py` — `make_csr(common_name, *, key_type="ed25519")` (and the same `key_type` on `make_leaf`), **defaulting to Ed25519** so the helper default reflects the new recommended default. Select `(key, algorithm)` together: `ed25519.Ed25519PrivateKey.generate()` with `.sign(key, None)` for Ed25519, `ec.generate_private_key(SECP256R1())` with `.sign(key, hashes.SHA256())` for `key_type="ec"`. Ed25519 forbids passing a hash algorithm; `cryptography` raises `ValueError` if one is supplied. `make_ca` (the issuer) can stay EC P-256 — only the device/subject key default changes.
- **mypy/lint will fail unless the type annotations widen.** `TestCA.key` and `TestLeaf.key` are typed `EllipticCurvePrivateKey`; broaden to a union (`EllipticCurvePrivateKey | Ed25519PrivateKey`) or the `CertificateIssuerPrivateKeyTypes` alias so `bash scripts/lint.sh` (mypy) stays green.
- The fake step-ca leaf in `test_enrollment.py::_signed_cert_for` already copies `csr.public_key()` into the leaf, so feeding it an Ed25519 CSR yields an Ed25519-SPKI leaf with no change beyond the CSR fixture.
- The provisioner-JWK fixture in `test_step_ca_client.py` stays ES256 — the provisioner key type is unrelated to the device key type.
- The integration-smoke case (`test_compose_smoke.py`) is the **only** test that hits the real step-ca, so it is the one that proves the deployed default template actually issues an Ed25519 leaf and that the hand-stuffed mTLS upload authenticates.

**Docs approach.** No operator-facing doc currently shows a device-key recipe (`deployment.md`, `deploy/terraform/README.md` reference `device.crt`/`device.key` abstractly), so the work is purely additive: add EC and Ed25519 keygen, e.g. `openssl genpkey -algorithm ed25519 -out device.key` and `ed25519.Ed25519PrivateKey.generate()` + CSR `.sign(key, None)`.

## Risks / Trade-offs

- **Residual unverified link:** real step-ca runtime issuance of an Ed25519 leaf is proven only in the local venv and from Smallstep docs, not yet against the deployed step-ca 0.29.0. This is precisely what the integration-smoke Ed25519 case closes — it is the highest-value test in this change and the acceptance gate for "Ed25519 is really supported."
- **`dynamic.yml:24-26` first-apply `caFiles` caveat** (which CA file device leaves chain to) is signature-scheme-independent — identical for EC and Ed25519 — so it is not an Ed25519 concern, but it remains an open first-apply assumption flagged in the config itself.
- **Type-annotation widening** in the test helper is the one non-obvious edit; missing it surfaces as a `mypy` failure in CI, not a runtime bug.
