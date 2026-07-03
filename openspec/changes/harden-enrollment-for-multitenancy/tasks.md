# Tasks

Implementation is TDD off the `#### Scenario`s in [specs/enrollment-hardening/spec.md](./specs/enrollment-hardening/spec.md): write the failing test first, then the code that makes it pass. Phases are independent and land top-to-bottom; phases 1–4 each map to one requirement. No infra (step-ca / Traefik / station-repo) change — see [design.md](./design.md) D1. All backend commands run from `backend/` (or `docker compose exec backend`).

## 1. SPKI-only identity guard (D4 — smallest, already true; lock it)

- [x] 1.1 Failing regression test in `backend/tests/api/routes/test_uploads.py` (reuse `tests/utils/mtls.py`): a valid device-CA leaf whose CN/SAN name another tenant's station resolves **only** by its `SHA-256(SPKI)` — it authenticates as the SPKI-matched station (or `401` if none), and the spoofed CN/SAN has no effect on which station/account the upload touches.
- [x] 1.2 Add a short affirming comment in `get_current_station` ([deps.py:103](../../../backend/app/api/deps.py#L103)) that identity is SPKI-only and CN/SAN are never read for authorization. No behavioural change.

## 2. Enrollment audit trail (D3)

- [x] 2.1 Add `EnrollmentAudit` table to `backend/app/models/enrollment.py` (fields per D3: `id`, `event`, `session_id`, `actor_user_id`, `source`, `user_agent`, `spki_sha256`, `station_id`, indexed `created_at`); register it in `backend/app/models/__init__.py`.
- [x] 2.2 Alembic migration: `alembic revision --autogenerate -m "enrollment audit table"` then `alembic upgrade head`.
- [x] 2.3 Failing test in `backend/tests/api/routes/test_enrollment.py`: a completed `confirm` writes exactly one `confirm_succeeded` row linking `spki_sha256` + `station_id` ↔ `session_id` ↔ owner ↔ source ↔ timestamp; `create` writes a `session_created` row with actor + source.
- [x] 2.4 Write audit rows in `create_enrollment_session` and `enroll_station` ([enrollment.py](../../../backend/app/api/routes/enrollment.py)); thread the source (`X-Forwarded-For` leftmost, fallback `request.client.host`) and user-agent into `confirm` (add `request: Request`).
- [x] 2.5 Add `ENROLLMENT_AUDIT_RETENTION_DAYS` (default `180`) to `config.py`; add a `@huey_client.periodic_task` nightly purge in `backend/app/tasks.py`; test that rows past the window are deleted and rows within it are retained.

## 3. Rate limits + quotas (D2)

- [x] 3.1 New `backend/app/core/ratelimit.py`: a Redis-backed fixed-window limiter (construct `redis.Redis` from `HUEY_REDIS_HOST`/`HUEY_REDIS_PORT` — no new dependency) exposed as a per-route FastAPI dependency factory; **fail-open** with a logged warning if Redis is unreachable. Add limit/quota settings to `config.py` (`ENROLLMENT_CREATE_RATE_PER_MIN=5`, `ENROLLMENT_CONFIRM_RATE_PER_MIN=10`, `MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER=5`, `MAX_STATIONS_PER_USER=25`).
- [x] 3.2 Failing tests: `confirm` beyond the per-source rate → `429` + `Retry-After`, and **no** CSR signed / **no** `Station` row (assert `sign_device_csr` not called); `create` beyond the per-user rate → `429`, no `EnrollmentToken`. (Fake the Redis clock/window; superuser exempt from create-rate.)
- [x] 3.3 Failing tests: a non-superuser at the owned-station ceiling → `create` returns `403`, no `EnrollmentToken`; a user at the active-session ceiling (unclaimed, unexpired) → `create` returns `403`. Superuser is exempt.
- [x] 3.4 Wire the limiter dependency onto `/create` (per user) and `/confirm` (per source) and add the two DB-backed quota checks at the top of `create_enrollment_session`, before any write.

## 4. Application-layer station revocation (D1)

- [x] 4.1 Add `Station.revoked_at: datetime | None = None` to `backend/app/models/station.py`; expose it on `StationPublic`. Alembic migration (`-m "station revoked_at"`) + `upgrade head`.
- [x] 4.2 Failing test in `test_uploads.py`: a revoked station's leaf → `get_current_station` yields the generic `401` (no upload stored); and in `test_stations.py`: a revoked station is absent from `GET /station/` for its owner.
- [x] 4.3 Enforce revocation in `get_current_station` ([deps.py](../../../backend/app/api/deps.py)) — after the SPKI match, `revoked_at is not None` → the generic mTLS `401`; filter `revoked_at IS NOT NULL` out of `read_stations`'s active list ([stations.py:38](../../../backend/app/api/routes/stations.py#L38)).
- [x] 4.4 Add `POST /station/{id}/revoke` in `stations.py`: owner-or-superuser (non-owner → `403` public / `404` private, mirroring `update_station`); set `revoked_at`, write a `station_revoked` audit row. In `enroll_station`, refuse to reuse a station whose `revoked_at is not None` (recovery = fresh key → new SPKI).
- [x] 4.5 Failing tests in `test_stations.py`: owner and superuser can revoke; non-owner gets `403`/`404`; and in `test_enrollment.py`: re-`confirm` with the revoked pin's key does not reactivate (station stays revoked, leaf still `401`s).

## 5. Verify and gate

- [ ] 5.1 `cd backend && bash scripts/lint.sh && bash scripts/test.sh` green.
- [ ] 5.2 `openspec validate harden-enrollment-for-multitenancy --strict` passes.
- [ ] 5.3 Docs: operator-facing revocation runbook (how to `POST /station/{id}/revoke`, what "revoked" means and the leaf-expiry residual window) and the documented limits/quotas for station authors.
- [ ] 5.4 `requesting-code-review` before merge; then archive (`openspec archive harden-enrollment-for-multitenancy`), folding the delta into `openspec/specs/enrollment-hardening/`.
