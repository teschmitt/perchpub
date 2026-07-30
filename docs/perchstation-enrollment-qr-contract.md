# PerchStation enrollment-QR contract

**Audience:** an agent implementing the enrollment **QR generation / display**
in the **perchpub** repo (server side) — the web UI that renders the QR an
operator points the station's camera at — and the agent implementing the
**perchstation** decoder/verifier that scans it.

**Authority:** this document is the **wire contract both repos pin to**. It is
the **re-cut** contract (the `ca_pin` shape): the QR carries a **pin of the
device-CA root**, not the CA chain, and `POST /enrollment/confirm` delivers the
chain in-band. perchpub and perchstation move to this shape **together** — see
"Two-repo lockstep" in §8. The full rationale and the station verification
algorithm live in
[openspec `add-station-enrollment-qr` design.md](../openspec/changes/add-station-enrollment-qr/design.md);
where this prose disagrees with that design or with the shipped perchstation
decoder, those win — flag the drift.

> **Migration note.** The *previous* contract embedded the entire device-CA
> `ca_chain_pem` in the QR and enforced a `confirm ⊆ QR` DER superset rule. That
> is gone. The current perchstation decoder (pre-rewrite) makes `ca_chain_pem` a
> required QR field and will **not** decode a `{session_id, auth_token, ca_pin}`
> payload; a decoder built to **this** contract is required for the new flow.

Keywords **MUST / MUST NOT / SHOULD / SHOULD NOT / MAY** are used per RFC 2119.

This is the QR-side companion to the
[device-certificate contract](./perchstation-csr-contract.md); read §3 and §7
there for how the delivered CA chain is used after enrollment.

---

## 1. Payload — exact shape

The QR symbol **MUST** encode, as its data segment, the **raw UTF-8 bytes of a
single JSON object**. Not a URL, not base64-of-JSON, not CBOR — the JSON text
itself.

```json
{"session_id":"550e8400-e29b-41d4-a716-446655440000","auth_token":"<opaque secret string>","ca_pin":"<64 lowercase hex — sha256 of the device-CA ROOT SPKI>","perchpub_url":"https://api.perchpub.net"}
```

| Field (wire name) | Type | Required | Meaning / rule |
|---|---|---|---|
| `session_id` | string (canonical UUID) | **MUST** | Path param for `POST /api/v1/enrollment/confirm/{session_id}`. Parse as a canonical UUID; a bad value → decode fails. |
| `auth_token` | string, non-empty | **MUST** | One-time bearer for `/confirm`; HMAC-verified server-side. MUST be present and non-empty. |
| `ca_pin` | string, 64 lowercase hex | **MUST** | `SHA-256( SubjectPublicKeyInfo(DER) )` of the device-CA **root** certificate. The station's out-of-band commitment to the trust root (see §3). |
| `perchpub_url` | string, absolute `https://` **origin** (scheme + host [+ port]), **no path, no trailing slash** | **SHOULD** (perchpub emits it) | The public **`:443` enrollment origin** the station enrolls against, e.g. `https://api.perchpub.net`. The station derives its `:8443` upload endpoint from it (switch the port) and validates the edge's TLS against **public / system trust** (wholly separate from `ca_pin`, which pins the *device* CA). It MUST be the canonical public origin whose edge certificate SAN matches. A station **MAY** use it to enroll with **zero pre-configuration**, but **MUST** tolerate its absence (an older perchpub) and MUST NOT hard-fail without it. |
| *(any other field)* | — | MAY | **Silently ignored** — the station SHOULD NOT reject unknown fields (forward-compat). In particular `expires_at` MAY appear and MUST be ignored: perchpub enforces the TTL, not the station. |

- Field **order is irrelevant** (JSON object) and whitespace is tolerated, but
  the generator **SHOULD** emit **compact** JSON (no spaces) — the payload is
  tiny (~160 B), and compactness leaves maximum error-correction headroom.
- The payload is naturally **ASCII** (UUID + URL-safe token + lowercase hex). It
  MAY be UTF-8; the decoder treats the QR bytes as UTF-8.

---

## 2. What is **not** in the QR

- **No `ca_chain_pem`.** The device-CA chain is **not** in the QR anymore. It is
  delivered in-band by `POST /confirm` (§3). The QR carries only the `ca_pin`
  commitment used to verify that chain.
- **No keypair, no CSR.** The station generates those locally after decoding.

> **`perchpub_url` is now carried in the QR (§1).** Earlier revisions of this
> contract omitted it — the station read its enrollment base URL from its own
> `config.toml`. perchpub now emits `perchpub_url` (sourced from its
> `STATION_EDGE_URL` setting) so a station can enroll with **zero
> pre-configuration**. This is **additive and backward-compatible**: a station
> that does not read it silently ignores it, and a station that does read it
> **MUST** still tolerate its absence (an older perchpub) rather than hard-fail.

---

## 3. `ca_pin` semantics — the interop constraint

`ca_pin` is the hex `SHA-256` of the **SubjectPublicKeyInfo (DER)** of the
**device-CA root** certificate (step-ca's root). It is **not** the issuing
intermediate, and it is **not** the public / Let's Encrypt `:443` edge CA — the
`:443` enrollment edge is validated against system / public trust, wholly
separate from this device-CA pin.

**`POST /confirm` returns the full device-CA chain.** step-ca's sign response
carries the issuing **intermediate**; perchpub **appends the root** (read from
`STEP_CA_ROOT_CERT_PATH`), so the `ca_chain_pem` in the confirm response is:

```
<issuing intermediate PEM>
<device-CA root PEM>
```

intermediate first, root last.

**Station obligations** (implemented in perchstation; specified here):

1. Decode the QR → generate keypair + CSR → `POST /confirm/{session_id}` with
   `auth_token` + CSR.
2. From the response `ca_chain_pem` (intermediate + root), build the path
   `leaf → intermediate → root`:
   - Verify a **usable CA** intermediate (`cA=TRUE` **and**
     `keyUsage.keyCertSign`) issued the leaf. step-ca signs leaves with the
     intermediate, so the chain **MUST** contain that intermediate.
   - **Abort** enrollment unless `SHA-256( SubjectPublicKeyInfo(DER) )` of the
     **root** equals `ca_pin`. A mismatch means the confirm channel delivered a
     chain the operator's authenticated browser did not vouch for — reject the
     leaf.
3. Present **leaf + intermediate** for mTLS (`:8443`). The **root** is used only
   for the pin check; it is not sent in the mTLS handshake.

**Why root, not intermediate?** The pin is anchored to the long-lived trust
root, so the operator can rotate the device **intermediate** with zero
coordination with the QR/pin logic. Because `ca_pin` and the appended root are
read from the **same file** (`STEP_CA_ROOT_CERT_PATH`), they are DER-equal by
construction — no "same step-ca instance" reasoning needed.

---

## 4. QR symbol parameters

- **One symbol only.** Render exactly **one** QR (the station reads one camera
  still, not a multi-frame / animated sequence) and keep other QRs out of the
  camera's view.
- **Byte mode.** Encode the raw UTF-8 payload bytes in **byte mode**.
- **Error correction:** because the QR is scanned off a **screen by the Pi
  camera** (not a clean file), use a **high** EC level — **M**, ideally **Q** —
  for glare / blur robustness. The payload is tiny (~160 B), so there is ample
  capacity for it; **favor error correction over density**.
- **No capacity ceiling.** With the chain gone, the payload is a fixed ~160 B —
  far under any single-symbol limit at any version. The old ~2953-byte ceiling
  and its "CA chain too large" guard no longer apply.
- **Quiet zone:** include the standard **≥4-module** quiet zone.
- **Contrast & size:** black-on-white, high contrast, generous module size on
  screen. If you also expose a downloadable image (for `enroll --qr-source
  file`), emit **PNG or JPEG** and keep dimensions well under **8192×8192** (the
  station rejects larger frames as a decompression-bomb guard).

---

## 5. Security

The QR embeds a **live single-use credential** (`auth_token`). Treat the whole
rendered symbol as a **secret**:

- **Never** place `auth_token` or the QR in a **URL / query string** (no
  `GET /qr?token=…`), in a **persisted client store**, or in **logs**.
- Render the QR **in-memory** from the transient session values (SVG / canvas) —
  never fetch it from a token-bearing endpoint.
- Serve any response that carries the token with **`Cache-Control: no-store`**;
  keep it out of shared / CDN caches.
- The credential is protected by three parametric defenses, all server-side:
  **single-use** (`claimed`), **≤3 attempts**, and a **bounded TTL**
  (`settings.ENROLLMENT_TTL_SECONDS`, **default 600 s / 10 min**; lower via env
  to shrink the window). A photograph of the on-screen QR taken within the TTL
  is a valid credential — the bounded window plus single-use (the live device typically
  redeems first, locking out a relayed photo with `Already enrolled`) are the
  mitigations; a static QR cannot itself distinguish a live scan from a photo.

---

## 6. Reference generator (language-agnostic)

```
payload_bytes = utf8( compact_json({
    "session_id":   session_id,   // canonical UUID string
    "auth_token":   auth_token,   // one-time opaque secret
    "ca_pin":       ca_pin,       // 64 lowercase hex = sha256(SPKI(DER)) of the device-CA ROOT
    "perchpub_url": perchpub_url, // public :443 enrollment origin, e.g. https://api.perchpub.net
}) )
qr = QR_encode(payload_bytes, mode=BYTE, ec_level=M_or_Q, quiet_zone>=4, one_symbol)
render(qr)   // in-memory SVG/canvas on the page; PNG/JPEG only for a file export
```

`ca_pin` is produced by perchpub as `hex( sha256( SPKI_DER( root_cert ) ) )` for
the cert at `STEP_CA_ROOT_CERT_PATH` — the same SPKI-SHA256 construction used
for the per-station leaf pin. `perchpub_url` is perchpub's `STATION_EDGE_URL`
setting (per-deployment; the public `:443` station edge origin). Both are
returned in the `POST /enrollment/create` response alongside `session_id`,
`auth_token`, and `expires_at`.

---

## 7. Conformance tests

- **Round-trip (generator side).** Build the QR, decode it with any standard QR
  reader, parse the JSON, and assert `session_id` / `auth_token` / `ca_pin` /
  `perchpub_url` survive **byte-for-byte** (`perchpub_url` an absolute `https://`
  origin — scheme + host, no path, no trailing slash). The decoded object MUST
  contain **exactly** those four fields and MUST NOT contain a CA chain, keypair,
  or CSR.
- **Interop (end-to-end).** Run `POST /enrollment/create` (capture `ca_pin`),
  then a real `POST /enrollment/confirm`, parse the returned `ca_chain_pem`
  (intermediate + root), verify the `leaf → intermediate → root` path builds
  (usable-CA intermediate issued the leaf), and assert
  `SHA-256( SPKI(DER) )` of the **root** equals `ca_pin`. This proves the
  station's root-pin verification will succeed against the deployed step-ca.

---

## 8. Two-repo lockstep

`/confirm` now returns intermediate + root, which violates the *old* decoder's
`confirm ⊆ QR` superset rule, and the QR no longer carries `ca_chain_pem` at all
— so the perchstation rewrite (this `ca_pin` contract) and the perchpub change
that emits it **MUST** deploy together. A perchstation built against the **new
decoder** can enroll even before it implements `ca_pin` **verification** (it uses
`session_id` + `auth_token` and takes `/confirm`'s chain as-is) — so the minimal
demo needs the new **decoder** but MAY defer the **pin check** (carried-but-
unverified). It does **not** work against the pre-rewrite station unmodified.
