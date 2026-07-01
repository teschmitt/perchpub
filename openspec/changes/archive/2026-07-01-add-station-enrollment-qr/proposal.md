## Why

Enrolling a station today ends with the wizard showing a `session_id` + one-time `auth_token` as copyable text, which the operator must then carry onto the Raspberry Pi by hand (SSH, paste, curl) — a step no doc even describes. That does not scale to a **public service with hundreds of non-technical users**: "copy this token and shell into your Pi" is not an onboarding funnel.

The station is a **camera**. We can close the loop optically: render the enrollment credential as a **QR code** the operator holds up to the feeder camera; `perchstation` scans it, generates its keypair/CSR, and confirms — no keyboard, no SSH. `perchstation` already ships a decoder and a frozen wire contract ([docs/perchstation-enrollment-qr-contract.md](../../../docs/perchstation-enrollment-qr-contract.md)); the operator is rewriting the station side, so this change also **re-cuts that contract** to the simpler, more secure shape below.

## What Changes

- **Backend returns a CA pin.** `POST /api/v1/enrollment/create` grows one field, `ca_pin` — the hex `SHA-256(SubjectPublicKeyInfo)` of the **device-CA root** (`settings.STEP_CA_ROOT_CERT_PATH`), reusing the exact SPKI-SHA256 primitive already used for `Station.spki_sha256`. Computed once, cached. No signing, no step-ca round trip at create time.
- **Confirm returns the full device-CA chain.** So the station can build `leaf→intermediate→root` and verify the pinned root, `POST /api/v1/enrollment/confirm/{session_id}` returns `ca_chain_pem` = issuing **intermediate + root** (step-ca returns the intermediate; the backend appends the root from `settings.STEP_CA_ROOT_CERT_PATH`). The station presents leaf+intermediate for mTLS and uses the root only for the pin check.
- **Enrollment TTL becomes configurable and shorter.** `TTL_SECONDS = 300` becomes `settings.ENROLLMENT_TTL_SECONDS`, **default 60 s** (the QR makes enrollment near-instant; a shorter window shrinks the replay surface of a photographed QR). The demo can raise it via env.
- **Wizard renders a QR (primary), keeps the text (fallback).** The wizard encodes compact UTF-8 JSON `{"session_id","auth_token","ca_pin"}` as a **single byte-mode QR**, rendered **in-memory** (SVG/canvas, no network, `Cache-Control: no-store`), with the existing copyable `session_id`/`auth_token` text kept as a collapsible fallback for headless/glare cases. The live countdown now derives purely from `expires_at`.
- **The perchstation contract is re-cut.** [docs/perchstation-enrollment-qr-contract.md](../../../docs/perchstation-enrollment-qr-contract.md) is rewritten from "full `ca_chain_pem` in the QR" to "**`ca_pin` (root SPKI) in the QR; intermediate+root delivered by `/confirm`, verified against the pin**" (design.md carries the full wire spec + station verification algorithm). This deletes the QR-capacity ceiling, the `confirm ⊆ QR` superset rule, and shrinks the station's X.509 work to a single chain build + one hash compare.
- **Out of scope (its own change, [harden-enrollment-for-multitenancy](../harden-enrollment-for-multitenancy/proposal.md)):** rate limiting / quotas on `create` + `confirm`, the enrollment audit trail, station revocation + cert lifecycle, and the SPKI-only-identity guard. Those are prerequisites for going public but are independent of the QR encoding.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `station-enrollment`: the enrollment-session create response now carries a `ca_pin` (device-CA root SPKI); `POST /enrollment/confirm` now returns the full intermediate+root chain; the wizard presents the credential primarily as a scannable QR (perchstation contract) with copyable text as a fallback; the one-time-token TTL is configurable (default 60 s).

## Impact

- **Backend:** `backend/app/core/config.py` (add `ENROLLMENT_TTL_SECONDS: int = 60`; `STEP_CA_ROOT_CERT_PATH` already exists), `backend/app/models/enrollment.py` (`ca_pin: str` on `EnrollmentSession`), `backend/app/api/routes/enrollment.py` (compute + cache the **root** SPKI pin; use the configurable TTL; return `ca_pin`; append the root to the confirm response's `ca_chain_pem` — the append may live in `backend/app/ca/step_ca_client.py`). Tests: `backend/tests/api/routes/test_enrollment.py`.
- **Frontend:** `frontend/src/routes/(app)/enroll/+page.server.ts` (thread `ca_pin` through `EnrollResult.session`), `frontend/src/lib/components/enroll-token.svelte` (render the QR + keep the text fallback), one new QR-render dependency + one QR-decode dev dependency, and a regenerated OpenAPI client (`EnrollmentSession` gains `ca_pin`). Tests: a Vitest round-trip (build payload → decode → assert fields) + the wizard render test.
- **Docs / contract:** `docs/perchstation-enrollment-qr-contract.md` rewritten to the `ca_pin` (root) shape — the shared artifact both repos pin to.
- **Dependencies:** one browser QR generator (e.g. `qrcode`), one dev-only QR decoder for the conformance test. No backend deps (the SPKI hash uses `cryptography`, already installed).
- **This is a breaking contract change — lockstep required.** The *current* perchstation decoder makes `ca_chain_pem` a required QR field and will **not decode** the new `{session_id, auth_token, ca_pin}` payload (it ignores `ca_pin` as unknown), and `/confirm` returning intermediate+root breaks its `confirm ⊆ QR` superset rule. A perchstation built against the **new decoder** enrolls even *without* implementing `ca_pin` **verification** (it uses `session_id`+`auth_token` and treats `/confirm`'s chain as-is) — so the demo needs the minimal decoder update but not the full pin-verification logic. It does **not** work against today's station unmodified.
