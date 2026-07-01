## Context

A logged-in operator starts enrollment in the `(app)` zone: the wizard's `create` form action POSTs `latitude`/`longitude` to `POST /api/v1/enrollment/create`, which mints an `EnrollmentToken` and returns `{session_id, auth_token, expires_at}`. Today the wizard shows `session_id`+`auth_token` as copyable text; the operator moves them to the Pi out-of-band, the Pi generates a keypair/CSR and POSTs `POST /api/v1/enrollment/confirm/{session_id}` (bearer = `auth_token`), the backend signs via step-ca and pins `SHA-256(SPKI)` of the leaf as `Station.spki_sha256`. The confirm endpoint is public on the `:443` (`api.${DOMAIN}`) WebPKI edge — it is the certless bootstrap; mTLS (`:8443`) covers only `/upload/` + `/classify-task/`.

`perchstation` already decodes an enrollment QR ([docs/perchstation-enrollment-qr-contract.md](../../../docs/perchstation-enrollment-qr-contract.md)). Its current contract puts the **entire device-CA `ca_chain_pem`** in the QR, which forces: sourcing the chain at create-time, a `confirm ⊆ QR` DER superset rule, a ~2953-byte capacity ceiling, and X.509 chain-walking on the station. The operator is **rewriting the station side**, so we re-cut the contract to a simpler, stricter shape.

This is being built for a **public, multi-tenant service** (hundreds of users/stations, one shared device CA). A leaked `auth_token` is therefore a **cross-tenant** integrity risk (enroll a device into another user's account), which drives the TTL and no-leak decisions below.

## Goals / Non-Goals

**Goals:**
- Present the enrollment credential as a **single scannable QR** the operator holds up to the feeder camera, so non-technical users onboard with no SSH/keyboard.
- Keep the QR **small and robust** off-screen-into-a-camera by carrying a **pin**, not a chain.
- Preserve (and extend to the QR) the existing "the token never leaks beyond the one-time display" property.
- Re-cut the two-repo wire contract so perchpub and perchstation stay pinned to one format.

**Non-Goals:**
- Rate limiting / quotas, audit trail, station revocation + cert lifecycle, SPKI-only-identity guard — all in [harden-enrollment-for-multitenancy](../harden-enrollment-for-multitenancy/proposal.md).
- Any change to the signing path or the mTLS edge (the confirm handler only *appends* the already-on-disk root to its response chain — see D3).
- Animated / multi-frame QR (perchstation reads one still; a rolling QR to beat photographs is a large complexity regression for marginal gain — see Risks).
- Building the station-side scanner/verifier (separate `perchstation` repo). This change *specifies* the station's obligations in the rewritten contract doc but implements only perchpub's half.

## Decisions

### D1. Pin the device-CA root SPKI

`ca_pin = hex( SHA-256( SubjectPublicKeyInfo(DER) of the device-CA root ) )`, read from `settings.STEP_CA_ROOT_CERT_PATH` (`/home/step-ca/certs/root_ca.crt`, already mounted + already used as the httpx trust root in `step_ca_client.py`).

Pinning the **root** (not the issuing intermediate) is a deliberate choice:

1. **Stable anchor.** The pin is anchored to the long-lived trust root, so the operator can rotate the device **intermediate** — a routine operation at scale — with zero coordination with the QR/pin logic. An intermediate-pin would change value on every rotation and would spuriously abort any enrollment whose QR was minted just before one.
2. **Consistency by construction.** `ca_pin` and the root the station checks against are read from the **same file** (`STEP_CA_ROOT_CERT_PATH`; see D3), so they are DER-equal by construction — no "same step-ca instance" reasoning needed.

**Cost (accepted):** the root is **not** in step-ca's `/1.0/sign` response (which returns the intermediate), so `/confirm` must **append the root** to `ca_chain_pem` (D3). Root-pin is also slightly *looser* than intermediate-pin — it accepts any intermediate the root signs — which is moot for a single-intermediate step-ca and is the price of the rotation-robustness in (1).

### D2. Hash-pin, not full chain

The QR carries `ca_pin` (a 64-char hex string), not `ca_chain_pem`. The chain the station needs to *present* in mTLS is delivered in-band by `/confirm` (now intermediate+root, D3); the QR delivers only the **out-of-band integrity commitment** to verify it. This is strictly cheaper (tiny QR, EC-level headroom for camera robustness) and at least as secure (a hash of the trust root commits to the same anchor as shipping the cert, with far less station-side ASN.1 code to get wrong). The out-of-band commitment matters more, not less, for a public shared-CA service: it lets the station reject a leaf issued under any CA the operator's authenticated browser did not vouch for, even if the `:443` confirm channel were subverted.

### D3. The re-cut wire contract (authoritative for the doc rewrite)

**QR symbol:** one QR, **byte mode**, quiet zone ≥4 modules, black-on-white, generous module size; EC level **M** (ideally **Q**) — the tiny payload leaves ample capacity, so favor error correction for the screen→camera path. Data segment = **raw UTF-8 bytes of one compact JSON object**:

```json
{"session_id":"<uuid>","auth_token":"<opaque secret>","ca_pin":"<64-hex sha256 of ROOT SPKI>"}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `session_id` | string (canonical UUID) | yes | path param for `POST /confirm/{session_id}` |
| `auth_token` | string, non-empty | yes | one-time bearer, HMAC-verified server-side |
| `ca_pin` | string, 64 lowercase hex | yes | `SHA-256(SPKI(DER))` of the device-CA **root** |

- No `perchpub_url` (station reads it from its own `config.toml`, unchanged). No chain, no keypair, no CSR.
- Unknown fields MAY be ignored by the station (forward-compat).
- The whole symbol is **secret** (contains `auth_token`): no logs, no CDN/shared cache, `Cache-Control: no-store`, in-memory render, never a token-bearing URL (no `GET /qr?token=…`).

**`/confirm` returns the full chain.** step-ca's sign response carries the issuing **intermediate**; the backend appends the **root** from `STEP_CA_ROOT_CERT_PATH`, so `ca_chain_pem` = intermediate + root (previously intermediate-only). This is the only server behavior change on the confirm path — no change to signing or the mTLS edge.

**Station obligations (specified here, implemented in perchstation):** after decode → generate keypair/CSR → `POST /confirm` → from the response `ca_chain_pem` (intermediate + root), build the path `leaf → intermediate → root`: verify a usable intermediate (`cA=TRUE` + `keyUsage.keyCertSign`) issued the leaf, and **abort unless `SHA-256(SPKI(DER))` of the root equals `ca_pin`**. Then present **leaf + intermediate** for mTLS (the root is used only for the pin check). Equality holds because perchpub computes `ca_pin` from — and appends to `/confirm` — the *same* `STEP_CA_ROOT_CERT_PATH` file.

### D4. TTL configurable, default 60 s

`settings.ENROLLMENT_TTL_SECONDS` (default `60`) replaces the `TTL_SECONDS = 300` constant in `enrollment.py`; `create` sets `expires_at = now + ENROLLMENT_TTL_SECONDS`. The frontend countdown already keys off `expires_at`, so it follows automatically. Rationale: camera enrollment is near-instant, and a smaller window shrinks the replay surface of a photographed QR (a cross-tenant risk on a public service). The demo can set `ENROLLMENT_TTL_SECONDS=300` if fumbling the camera.

### D5. QR primary, text fallback, in-memory render

The wizard shows the QR as the primary artifact and keeps the existing copyable `session_id`/`auth_token` text as a collapsible fallback (headless Pi / glare / fixed-focus camera). Render client-side from the in-memory session values (SVG or canvas). This satisfies the existing "SHALL NOT be placed in a URL, query string, or persisted client store" requirement for the QR too — nothing hits the network to build it.

## Risks / Trade-offs

- **Irreducible: a photograph of the on-screen QR within the TTL is a valid credential.** A static QR cannot distinguish a live scan from a photo. Defenses are all parametric and already in place or added here: single-use (`claimed`), ≤3 attempts, and the **60 s TTL** — plus the QR *favors the legitimate device*, which scans live and typically redeems before a human relaying a photo, locking the attacker out with `Already enrolled`. A rolling/animated QR would defeat photos but perchstation reads one still and it's a large regression — rejected.
- **`ca_pin` vs the confirm root.** Verification works because `ca_pin` and the root appended to `/confirm` are read from the *same file* (`STEP_CA_ROOT_CERT_PATH`) — DER-equal by construction. Root-pinning also removes the intermediate-rotation-within-the-window abort that an intermediate-pin would suffer. The residual risk is a **misconfigured mount** — the on-disk `root_ca.crt` not actually being the trust root of the signing hierarchy; the conformance test closes this by building the full `leaf→intermediate→root` path from a live `/confirm` and asserting the root's SPKI equals `ca_pin`.
- **Two-repo lockstep.** `/confirm` now returns intermediate+root, which would violate the *old* perchstation decoder's `confirm ⊆ QR` superset rule — so the perchstation rewrite (new `ca_pin` contract) and this change must deploy together. The rewritten contract doc is the single source both repos pin to. The *current* decoder also requires `ca_chain_pem` and cannot decode the new `{session_id, auth_token, ca_pin}` payload at all — so the rewrite's **decoder** is required for the demo, even though its **pin-verification** step can be deferred (until it lands, the pin is carried-but-unverified, which is the only part that is demo-optional).
- **Demo tension with 60 s.** Mitigated by making the TTL a setting (D4).
- **Capacity is a non-issue** (payload ~160 B ≪ ceiling) *because* we pin instead of embedding the chain — the whole point of D2.
