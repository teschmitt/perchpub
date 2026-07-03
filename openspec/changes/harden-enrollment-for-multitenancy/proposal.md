## Why

PerchPub is moving from a self-hosted single-operator tool to a **public service with many users and stations sharing one device CA**. That inverts the enrollment threat model: a leaked one-time `auth_token` is no longer self-inflicted — it lets one user enroll a device into **another user's account** (a cross-tenant integrity / near-account-takeover primitive), and the currently **unauthenticated** `POST /enrollment/confirm/{session_id}` endpoint mints a real, step-ca-signed certificate on every success. The single-tenant code has **no rate limits, no quotas, no audit trail, and no revocation** — all prerequisites for operating enrollment safely at scale.

The core trust chain (authenticated owner-bound session → 256-bit single-use token → backend-minted OTT → SPKI-pinned identity) is sound; investigation confirmed it is sounder than the skeleton assumed. This change hardens the operational envelope around it — it does not rebuild it.

Two findings from the investigation shape the scope:

- **The backend is already the sole cert→account authority.** `get_current_station` ([deps.py:103](../../../backend/app/api/deps.py#L103)) is the *only* consumer of station identity (its sole caller is `uploads.py`), it resolves purely by `SHA-256(SPKI)`, and it already rejects out-of-window leaves. So revocation enforced at that resolver is complete for integrity, and the SPKI-only-identity guard is already true in code — this change locks it with a test rather than building it.
- **The mTLS edge cannot do per-certificate revocation.** The Traefik file-provider `clientAuth` ([dynamic.yml](../../../deploy/traefik/dynamic/dynamic.yml)) verifies leaves against static `caFiles` with no CRL/OCSP mechanism. "Reject a revoked leaf at the TLS handshake" is not achievable on the current edge without a proxy swap or reliance on cert expiry — so edge-cryptographic revocation is explicitly **out of scope** here and deferred to a named follow-up.

## What Changes

- **Rate limits.** `POST /enrollment/create` is rate-limited per authenticated user; `POST /enrollment/confirm/{session_id}` is rate-limited per source (in addition to the existing ≤3-attempts-per-session cap). Excess requests get `429` + `Retry-After` **before** any side effect (no CSR signing, no `Station`/`EnrollmentToken` write). Redis-backed (already in-stack for Huey); fail-open (a throttle, not the authorization boundary).
- **Per-user quotas.** A ceiling on concurrently-active (unclaimed, unexpired) enrollment sessions and on total owned, non-revoked stations, enforced in `POST /enrollment/create` (`403` at the ceiling). DB-backed and always enforced. Superusers exempt.
- **Enrollment audit trail.** A dedicated `EnrollmentAudit` table records who created each session (actor, source, timestamp), and on confirm the source, timestamp, originating session + owner, and resulting `Station.spki_sha256` / `station_id`, plus revocation events — so a leaked-token incident is reconstructable and a rogue enrollment is attributable. Configurable retention with a periodic purge.
- **Application-layer station revocation.** `Station.revoked_at`, exposed via `POST /station/{id}/revoke` (owner + superuser; non-owner gets the same `403`/`404` leak-avoidance as station update), enforced in `get_current_station` (a revoked leaf → generic mTLS `401`, no upload, nothing attributed) and filtered from the owner's active station list. Non-destructive (observations/uploads retained). Re-enrolling the revoked key does not reactivate it — recovery is a fresh device key.
- **SPKI-only identity guard.** Assert and regression-test that station identity is resolved **only** by the enrollment-time `SPKI → Station → owner_id` binding, and that no code path authorizes on the leaf's CN or SAN (the OTT copies CSR-requested SANs verbatim, so a SAN must never be trusted for authorization in multi-tenant).

## Capabilities

### New Capabilities

- `enrollment-hardening`: rate limits, per-user quotas, an audit trail, application-layer station revocation, and the SPKI-only-identity guard for multi-tenant enrollment. Kept as a single capability (see design [D5](./design.md)) — the deferred edge-cryptographic revocation will be its own capability when/if triggered.

## Impact

- **Backend:** `backend/app/api/routes/enrollment.py` (rate-limit + quota deps, audit writes, refuse re-enroll of a revoked pin), `backend/app/api/routes/stations.py` (revoke route, filter revoked from active list), `backend/app/api/deps.py` (enforce `revoked_at` in `get_current_station`), a new `EnrollmentAudit` model + `Station.revoked_at` in `backend/app/models/` (register in `models/__init__.py`), a new `backend/app/core/ratelimit.py` (Redis fixed-window limiter dependency), new settings in `backend/app/core/config.py`, a periodic purge task in `backend/app/tasks.py`, and two Alembic migrations.
- **Infra:** none. No step-ca, Traefik, or station-repo change — the point of choosing application-layer revocation.
- **Docs:** operator-facing revocation runbook; documented limits/quotas for station authors.
- **Explicitly deferred (separate future change, e.g. `add-edge-certificate-revocation`):** cryptographic revocation at the TLS edge (CRL/OCSP or a proxy that supports it) plus the step-ca renewal-lifecycle work it depends on. Trigger: device leaves proving long-lived **and** stations gaining a direct step-ca renewal path. See [design.md](./design.md).
