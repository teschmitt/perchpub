## Why

PerchPub stations are Raspberry Pi-class devices that generate a keypair + CSR at enrollment. Ed25519 keys are smaller and faster to generate, store, and use than the EC P-256 keys the test suite (and the still-unbuilt reference-client plan) assume today — the better choice for constrained stations. Investigation shows the stack **already** accepts Ed25519 end-to-end with no server reconfiguration, but that support is incidental and unverified. This change makes it explicit, CI-proven, and documented, and promotes Ed25519 to the **recommended default** for new stations — without restricting key types or reconfiguring the server.

## What Changes

- **No production code or config changes.** Adversarial review of the whole backend, the step-ca JWK provisioner config, and the Traefik mTLS edge confirmed the enroll → sign → SPKI-pin → mTLS path is already key-type-agnostic (evidence in `design.md`). EC P-256 stays fully supported and tested; the change adds no removals and touches no production surface.
- **Recommended default.** Ed25519 becomes the recommended/default device key type: the docs lead with it and the test CSR helper defaults to Ed25519. The server still accepts **any** key type — "default" is a docs/tooling choice here, not server enforcement (the backend never selects the key type; the station does).
- **Test coverage.** Parametrize the CSR test helper and the enrollment, step-ca-client, and integration-smoke tests over **Ed25519 and EC P-256**. Assert that an Ed25519 CSR yields an Ed25519 leaf, the SPKI pin matches, and an mTLS upload presenting the Ed25519 leaf authenticates; keep an EC P-256 case as a regression. The integration-smoke case is the one that proves the **deployed** step-ca actually issues an Ed25519 leaf (the unit enrollment test mocks signing).
- **Docs.** Add Ed25519 device-key generation (OpenSSL and Python `cryptography`) to the station-enrollment runbook as the recommended path, noting that Ed25519 CSRs are signed with **no** hash algorithm (`.sign(key, None)`), and document EC P-256 as the supported alternative.
- **Out of scope (non-goals):** any key-type allowlist or **server-side enforcement** (the CA keeps accepting any key type), and any step-ca / Traefik / backend reconfiguration. Making Ed25519 the only *enforced* key type via a provisioner x509-template allowlist is a future change, tracked separately, not here.

## Capabilities

### New Capabilities
- `station-enrollment`: how a station enrolls a device keypair/CSR, which device key types are supported, how the issued leaf's SubjectPublicKeyInfo SHA-256 is pinned as the station identity, and how that identity authenticates mTLS uploads.

### Modified Capabilities
- None. There are no existing `openspec/specs/` capabilities, and no requirement-level behavior of any other capability changes.

## Impact

- **Production code / config:** none — verified at high confidence across `backend/app/**`, the `step-ca` provisioner in `docker-compose.yml`, and `deploy/traefik/dynamic/dynamic.yml`.
- **Tests:** `backend/tests/utils/mtls.py` (parametrize `make_csr`/`make_leaf`, **defaulting the device key type to Ed25519**; **widen** the `EllipticCurvePrivateKey` type annotations or `mypy`/`scripts/lint.sh` fails), `backend/tests/api/routes/test_enrollment.py`, `backend/tests/ca/test_step_ca_client.py`, `backend/tests/integration/test_compose_smoke.py`.
- **Docs:** `deployment.md` and/or `deploy/terraform/README.md` — neither shows a device-key recipe today, so this only adds keygen, leading with Ed25519 as the recommended default and EC P-256 as the supported alternative; optional clarifying notes in `README.md` / `CLAUDE.md` and the misleading EC-only comment at `backend/app/ca/step_ca_client.py:71`.
- **Dependencies:** none. `cryptography>=42,<46` (installed 45.0.7) already supports Ed25519 CSR parsing/signing; Traefik `v3.7.5` (Go 1.24) verifies Ed25519 client certs.
