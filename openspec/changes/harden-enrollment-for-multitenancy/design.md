## Context

See [proposal.md](./proposal.md). This design is **intentionally incomplete** — it records the open questions that must be answered before the requirements below are implementation-ready. The trust chain being hardened: authenticated user → `POST /enrollment/create` (owner-bound `EnrollmentToken`, 256-bit `auth_token`, HMAC tag stored) → operator conveys the token to the device (QR, per the sibling change) → device `POST /enrollment/confirm/{session_id}` (unauthenticated; bearer = `auth_token`; ≤3 attempts; single-use `claimed`) → backend mints an OTT and step-ca signs → `Station` pinned by `SHA-256(SPKI)` of the leaf, owned by the session's `owner_id`.

## Goals / Non-Goals

**Goals:** make enrollment safe to expose to hundreds of mutually-distrusting tenants — bound abuse, attribute actions, and be able to revoke.

**Non-Goals (this change):** the QR encoding (sibling change); rebuilding the sound core trust chain; user-facing billing/plans.

## Open Questions (must be resolved before implementation)

### Q1 — Revocation + cert lifecycle *(load-bearing)*
- **Short-lived leaf certs + renewal** (station periodically re-enrolls/renews; revocation = stop renewing + expire) vs **CRL/OCSP** (long-lived certs, explicit revocation list Traefik must consult). Trade-offs: short-lived shifts load to renewal + needs a renewal path the station repo must implement; CRL/OCSP needs a responder and Traefik mTLS wiring, and revocation-checking at the edge.
- What does "revoke" mean operationally — de-link `spki_sha256` (uploads stop being *attributed*, but the cert still handshakes) vs the cert stops *authenticating* at the mTLS edge? For a public service it must be the latter.
- Where does revocation state live, and who can trigger it (owner, superuser, automated abuse response)?

### Q2 — Rate-limit + quota mechanism
- Middleware vs per-route dependency; storage (Redis is already in-stack for Huey). Limits: per-user create rate, per-IP + per-session confirm rate, max active sessions/user, max stations/user. Values TBD.
- Behavior on limit: `429` with `Retry-After`? Interaction with the existing ≤3-attempts-per-session cap.

### Q3 — Audit model + retention
- New SQLModel table vs structured logs vs both. Fields: actor user, source IP/UA, timestamps for create/confirm, outcome, resulting `spki_sha256`, session_id. Retention + PII posture (source IPs).

### Q4 — SPKI-only identity guard
- Confirm no code path authorizes on leaf CN/SAN. `_build_provisioner_jwt` copies CSR-requested SANs into the OTT (`step_ca_client.py`), so a station can obtain a leaf with arbitrary SANs — identity MUST stay the enrollment-time `SPKI → Station → owner_id` binding only. Likely a regression test + a `deps.py` assertion; possibly a clarifying requirement in `station-enrollment` rather than the new capability.

### Q5 — Capability decomposition
- Keep the single `enrollment-hardening` capability or split into `enrollment-abuse-controls` (Q2/Q3) + `station-revocation` (Q1) + a `station-enrollment` clarification (Q4)?

## Decisions

None yet — this is a skeleton. Each open question above becomes a decision here once resolved.

## Risks / Trade-offs

- **Revocation is the risk.** Getting the cert lifecycle wrong is expensive to change later (it touches step-ca, Traefik, and the station repo in lockstep). Prototype Q1 before committing spec language.
- **Priority.** For a *public launch* this hardening is arguably higher priority than the QR UX; sequence accordingly even though the QR is the immediate ask.
