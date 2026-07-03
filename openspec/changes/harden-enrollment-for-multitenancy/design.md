## Context

See [proposal.md](./proposal.md). The trust chain being hardened: authenticated user → `POST /enrollment/create` (owner-bound `EnrollmentToken`, 256-bit `auth_token`, HMAC tag stored) → operator conveys the token to the device (QR, per the shipped `add-station-enrollment-qr` change) → device `POST /enrollment/confirm/{session_id}` (unauthenticated; bearer = `auth_token`; ≤3 attempts; single-use `claimed`) → backend mints an OTT and step-ca signs → `Station` pinned by `SHA-256(SPKI)` of the leaf, owned by the session's `owner_id`.

The skeleton deferred five open questions. Investigation of the actual code and edge config closed all five; they are recorded below as decisions. The load-bearing one (Q1, revocation) resolved differently from the skeleton's stated prior — the evidence is in D1.

## Goals / Non-Goals

**Goals:** make enrollment safe to expose to many mutually-distrusting tenants — bound abuse, attribute actions, and be able to revoke a station — with **no infra (step-ca / Traefik / station-repo) changes**, so it ships as a self-contained backend change.

**Non-Goals (this change):** the QR encoding (shipped separately); rebuilding the sound core trust chain; user-facing billing/plans; **cryptographic revocation at the TLS edge (CRL/OCSP)** — deferred, see D1 and the "Deferred follow-up" section.

## Decisions

### D1 — Revocation is enforced at the application identity layer *(resolves Q1)*

**Decision.** Add `Station.revoked_at: datetime | None`. Enforce it in `get_current_station`: after resolving a station by SPKI, if `revoked_at is not None`, raise the existing generic mTLS `401`. Expose revocation as `POST /station/{id}/revoke` (owner + superuser), non-destructively. Filter revoked stations from the owner's active list. Refuse to reuse a revoked pin on re-enrollment. **Do not** attempt cryptographic revocation at the TLS edge in this change.

**Why this, not edge-level revocation (against the skeleton's "must be at the edge" prior):**

1. **Traefik can't do it.** The mTLS edge ([dynamic.yml](../../../deploy/traefik/dynamic/dynamic.yml)) uses the file-provider `clientAuth` with `RequireAndVerifyClientCert` against static `caFiles`. The Traefik file provider has **no CRL/OCSP mechanism** for client certs. Edge-level per-cert revocation would require swapping the proxy or standing up an OCSP responder step-ca doesn't ship — a large, cross-repo, infra-heavy effort.
2. **The app is already the sole cert→account authority.** `get_current_station` ([deps.py:103-168](../../../backend/app/api/deps.py#L103)) is the *only* place a certificate is mapped to a `Station`/`owner_id`, its only caller is the upload path, and it already rejects out-of-window leaves ([deps.py:154](../../../backend/app/api/deps.py#L154)). A `revoked_at` check there makes a revoked cert **fail to authenticate as any station → `401`, no upload, nothing attributed.** That is the complete *integrity* guarantee — the one that matters for multi-tenancy.
3. **The residual gap is not an integrity gap.** After revocation a revoked leaf can still complete a *TLS handshake* before being refused with `401`. That is a resource-exhaustion/DoS concern — covered by D2's rate limits — and it self-heals as the short-lived leaf expires. It never lets the revoked station touch data or another account.
4. **Stations can't self-renew around it.** step-ca (`http://step-ca:9000`) is an internal service, not exposed at the edge; the only path to a new cert is the backend's operator-initiated enrollment flow (needs a fresh `auth_token`). So "stop issuing" is automatic: a revoked station cannot obtain a new cert without operator action, and re-enrolling the *same* key stays revoked (D1 refuses reuse of a revoked pin). Recovery is a fresh device key → new SPKI → new `Station`.

**Operational meaning of "revoke":** the certificate no longer *authenticates as a station* (immediate, at the resolver), and the station disappears from the active list. It is not de-attribution-only — a revoked leaf performs no action.

**Related open item (does NOT block this change):** the real device-leaf lifetime and whether stations ever gain a direct step-ca renewal path. The step-ca JWK provisioner is created with defaults ([docker-compose.yml:331](../../../docker-compose.yml#L331)), i.e. step-ca's default TLS cert duration, and no station-side renewal path is exposed today. That lifetime bounds the residual handshake window only; app-layer revocation is immediate regardless. If leaves later prove long-lived **and** stations gain a direct step-ca renewal path, edge-cryptographic revocation becomes necessary — that is the trigger for the deferred follow-up.

### D2 — Rate limits: Redis-backed fixed-window dependency; quotas: DB-backed *(resolves Q2)*

**Decision.** A small fixed-window limiter in a new `backend/app/core/ratelimit.py`, backed by the in-stack Redis (constructed from `HUEY_REDIS_HOST`/`HUEY_REDIS_PORT` — no new dependency; `redis` is already present via Huey), applied as a **per-route FastAPI dependency** so it runs before the handler body (no CSR signing / no writes on a rejected request). Quotas are counted against Postgres in the `create` handler.

- **Limits (env-configurable, sensible defaults in `config.py`):**
  - `ENROLLMENT_CREATE_RATE_PER_MIN` per authenticated user — default `5`.
  - `ENROLLMENT_CONFIRM_RATE_PER_MIN` per source — default `10` (per-session is already capped at ≤3 attempts total).
  - `MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER` — default `5` (active = unclaimed, unexpired).
  - `MAX_STATIONS_PER_USER` — default `25` (owned, non-revoked).
- **Behaviour on limit:** rate exceeded → `429` + `Retry-After` (transient). Quota exceeded → `403` (persistent "at your ceiling"), with no `EnrollmentToken` persisted.
- **Source IP for `confirm`:** derived from the Traefik-populated `X-Forwarded-For` (leftmost hop), falling back to `request.client.host`. Trustworthy only because the mTLS entrypoint sets it — the same entrypoint-isolation trust boundary as the cert header (see the `deps.py` docstring).
- **Fail-open:** if Redis is unavailable the limiter logs and allows the request. Rate limits are a throttle; the security boundary is the HMAC token + attempts cap + quotas (DB-backed, always enforced), not the limiter. Superusers are exempt from the create-rate and quotas.

### D3 — Audit: a dedicated queryable table with configurable retention *(resolves Q3)*

**Decision.** A new `EnrollmentAudit` SQLModel table (a table, not logs — it must be *queryable* to attribute a rogue enrollment, and no log aggregation is deployed). Written from `enrollment.py` (create + confirm) and the revoke route.

- **Fields:** `id` (uuid pk), `event` (`session_created` | `confirm_succeeded` | `station_revoked`), `session_id` (uuid, nullable), `actor_user_id` (uuid, nullable — the session owner for confirm, the revoker for revoke), `source` (str — IP), `user_agent` (str, nullable), `spki_sha256` (str, nullable — set on confirm), `station_id` (uuid, nullable), `created_at` (datetime, indexed).
- **PII posture:** the source IP is retained in full (a security audit trail has a legitimate-interest basis and incident reconstruction often needs the real address), bounded by **retention**: `ENROLLMENT_AUDIT_RETENTION_DAYS` (default `180`) with a `@huey_client.periodic_task` nightly purge of rows past the window.
- Failed confirms are intentionally *not* audited to a row per attempt (the ≤3 cap + rate limits bound them and they would dominate the table); the successful/lifecycle events carry attribution.

### D4 — SPKI-only identity guard: already true; lock it with a test *(resolves Q4)*

**Decision.** No behavioural change is needed — `get_current_station` already resolves identity *only* by `SHA-256(SPKI)` and the CN/SAN handling in `step_ca_client.py` ([step_ca_client.py:59-114](../../../backend/app/ca/step_ca_client.py#L59)) only shapes the step-ca OTT, never an authz decision. This change **adds a regression test** (a valid device-CA leaf whose CN/SAN names another tenant resolves only by its SPKI, or `401`, with the CN/SAN having no effect) and a short affirming comment at the resolver. The guarantee is captured as an ADDED requirement in `enrollment-hardening` (D5), not as a modification to `station-enrollment`, because the new content is a multi-tenant hardening contract distinct from that spec's key-type-agnostic identity requirement.

### D5 — One capability *(resolves Q5)*

**Decision.** Keep a single `enrollment-hardening` capability. Rate limits, quotas, audit, application-layer revocation, and the SPKI guard are one cohesive "make enrollment multi-tenant-safe" story; splitting adds ceremony for no clarity. The deferred edge-cryptographic revocation is a genuinely separate concern (different layer, infra-heavy, cross-repo) and will be its own capability/change when triggered — not a premature split now.

## Deferred follow-up: edge-cryptographic revocation

Out of scope here; captured so it is not lost. A future change (working name `add-edge-certificate-revocation`) would make a revoked leaf fail the **TLS handshake** at the edge, not merely the app resolver. It requires resolving, in lockstep: (a) a proxy that consults a CRL/OCSP for client certs (Traefik's file provider does not) or a short-lived-cert + station-side renewal model; (b) step-ca's revocation/renewal configuration; and (c) the station repo's renewal loop. **Trigger:** device leaves proving long-lived AND stations gaining a direct step-ca renewal path — until then, D1's app-layer revocation plus leaf expiry is sufficient and this work would be speculative.

## Risks / Trade-offs

- **Residual handshake window.** Between revocation and leaf expiry a revoked cert can complete a handshake and be refused with `401`. Accepted: it performs no action (integrity intact) and the cost of the handshake+`401` is bounded by D2's per-source rate limit. Documented in the spec's revocation requirement.
- **Fail-open limiter.** A Redis outage disables rate limiting. Accepted: quotas and the HMAC/attempts cap remain enforced, and availability of enrollment is preferred over hard-failing every request on a limiter hiccup. The degradation is logged.
- **Quota defaults.** The default ceilings are guesses for an early public service; all are env-configurable, so they can be tuned without a code change.
