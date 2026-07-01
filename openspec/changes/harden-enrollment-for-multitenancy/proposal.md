> **STATUS: SKELETON.** This change captures the multi-tenant enrollment-hardening work so it is not lost. The proposal below is firm on *what* and *why*; the *how* — especially revocation + cert lifecycle — is unresolved. Do **not** implement before the open questions in [design.md](./design.md) are closed and the spec deltas are fleshed out. Sibling change [add-station-enrollment-qr](../add-station-enrollment-qr/proposal.md) is independent and can ship first.

## Why

PerchPub is moving from a self-hosted single-operator tool to a **public service with hundreds of users and stations sharing one device CA**. That inverts the enrollment threat model: a leaked one-time `auth_token` is no longer self-inflicted — it lets one user enroll a device into **another user's account** (a cross-tenant integrity / near-account-takeover primitive), and the currently **unauthenticated** `POST /enrollment/confirm` endpoint mints a real, step-ca-signed certificate on every success. The single-tenant code has **no rate limits, no quotas, no audit trail, and no revocation** — all of which are prerequisites for operating enrollment safely at scale. The core trust chain (authenticated owner-bound session → 256-bit single-use token → backend-minted OTT → SPKI-pinned identity) is sound; this change hardens the operational envelope around it, it does not rebuild it.

## What Changes

- **Rate limits + quotas.** Throttle `POST /enrollment/create` (per authenticated user) and the unauthenticated `POST /enrollment/confirm/{session_id}` (per source IP and per session) to bound abuse, probing, and CA-log growth. Enforce a per-user cap on active enrollment sessions and on total owned stations. *(Mechanism TBD — see design.)*
- **Enrollment audit trail.** Record who created each session (user, source, timestamp), and on confirm the source, timestamp, and resulting `Station.spki_sha256`, so a leaked-token incident is reconstructable and a rogue enrollment is attributable. *(Storage + retention TBD.)*
- **Station revocation + certificate lifecycle.** Give an owner (and a superuser) a way to revoke a station such that its certificate **no longer authenticates mTLS uploads**, and decide the cert lifecycle that makes revocation effective at scale — **short-lived leaf certs + renewal** vs **CRL/OCSP**. This is the **load-bearing, least-designed** piece. *(Mechanism TBD — the pivotal open question.)*
- **SPKI-only identity guard.** Assert and regression-test that station identity is resolved **only** by the enrollment-time `SPKI → Station → owner_id` binding, and that no code path authorizes on the leaf's CN or SAN (the OTT copies CSR-requested SANs verbatim, so a SAN must never be trusted for authorization in multi-tenant).

## Capabilities

### New Capabilities
- `enrollment-hardening`: rate limiting, quotas, audit, revocation + cert lifecycle, and the SPKI-only-identity guard for multi-tenant enrollment. **NOTE:** this is a deliberately broad placeholder capability for the skeleton; a design task is to decide whether to split it (e.g. `enrollment-abuse-controls` + `station-revocation`) before implementation.

### Modified Capabilities
- `station-enrollment` (anticipated): the SPKI-only-identity guard may land as a clarifying requirement here rather than in the new capability — decide during design.

## Impact

- **Backend (anticipated):** `backend/app/api/routes/enrollment.py` (rate-limit + quota checks, audit writes), a new audit model under `backend/app/models/`, a revocation path touching `backend/app/api/routes/stations.py` and the step-ca integration (`backend/app/ca/step_ca_client.py`), and identity resolution in `backend/app/api/deps.py` (SPKI-only guard). A rate-limiter dependency and/or Redis (already in the stack for Huey) is likely.
- **Infra (anticipated):** revocation may require step-ca configuration (short-lived certs / renewal provisioner, or CRL/OCSP responder) and Traefik mTLS changes — potentially the largest surface.
- **Docs:** operator-facing revocation runbook; abuse/limits documented for station authors.
- **Dependencies / open questions:** all deferred to [design.md](./design.md). This is a skeleton.
