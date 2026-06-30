## Why

The SvelteKit frontend rewrite (P0 `add-sveltekit-frontend-foundation` → P3 `add-superuser-frontend-tools`) was authored as frontend-only ("Backend: none"). A code-grounded review of those four changes against the actual backend confirmed ~30 concrete API claims as accurate, but surfaced **three backend realities the frontend specs depend on that do not currently hold** — each of which silently breaks a P0/P1/P3 acceptance scenario. This change (the backend prerequisite for the rewrite) closes exactly those three gaps, and **nothing else**, so P0–P3 can be built as written:

1. **Auth returns `403`, not `401`, for a bad/expired token.** P0's BFF keys cookie-clearing and the forced `/login` redirect on a backend `401` (`add-sveltekit-frontend-foundation/specs/web-frontend/spec.md` "an expired session is cleared"; design.md auth-flow step 2). But `backend/app/api/deps.py:49-53` (`_resolve_user`) raises `403` for an invalid/expired JWT (`404` for a deleted user, `400` for an inactive one). The only `401` in the codebase is the mTLS station path the browser never hits — so the BFF's expiry handling, as P0 specifies it, never fires and an expired session shows a broken authed page instead of bouncing to login.
2. **Collection list endpoints have no `ORDER BY`.** P1's landing "most recent observations" and the paginated feed assume a stable, time-descending order, but `backend/app/api/routes/observations.py:28` issues `select(Observation).offset(skip).limit(limit)` with no ordering — Postgres returns arbitrary heap order. "Most recent" is therefore unachievable and successive identical page requests can return rows in different, overlapping order. The same omission affects `GET /species/`, `GET /station/`, and `GET /classify-task/`.
3. **`ClassifyTaskPublic` omits the `created_at`/`updated_at` it needs.** P3's admin classify-task table renders "created/updated timestamps" and its status badge picks "the observation's most-recent classify task". But `backend/app/models/classify_task.py:66-69` exposes only `id`/`object_name`/`status`/`upload`/`observation` — the timestamps live on the table model only, so they are absent from `openapi.json`, absent from the generated typed client (referencing them fails type-check), and there is no field to sort "most-recent" by.

Fixing these in the backend — rather than reworking P0/P1/P3 — lets the frontend specs stand unchanged: the backend will return the `401` P0 already expects, serve the most-recent-first order P1 already assumes, and expose the timestamps P3 already renders.

## What Changes

- **Bearer auth failures return `401`.** `_resolve_user` (`backend/app/api/deps.py`) raises `401 Unauthorized` (keeping the generic `"Could not validate credentials"` detail) when a JWT cannot be validated (expired/malformed/invalid claims), when it resolves to a non-existent user, and when it resolves to an inactive user — i.e. every "this session is no longer usable" case. **Authorization** failures for a successfully-authenticated user are untouched: `get_current_active_superuser` and the per-row station/observation ownership checks keep returning `403`. The login endpoint (`/login/access-token`) is unchanged.
- **Deterministic, most-recent-first list ordering.** `GET /observation/`, `GET /species/`, `GET /station/`, and `GET /classify-task/` gain an explicit total `ORDER BY`: observations and classify-tasks most-recent-first (`observed_at` / `created_at` descending), species by `scientific_name` ascending, stations by `created_at` descending — each with `id` as a unique tiebreaker so the order is total and reproducible.
- **Expose classify-task timestamps.** `ClassifyTaskPublic` adds `created_at` and `updated_at` (already persisted on the `classify_task` table), so they appear in the OpenAPI schema and the generated client.
- **No database migration.** All three are response-model, query, and status-code changes; no column is added or altered (the classify-task timestamps already exist on the table).
- **Out of scope (non-goals):** per-viewer visibility filtering on `GET /observation/` (private-station observations are still returned to anonymous callers — an inherited gap P1 explicitly accepts); authorization on the `/media/` endpoint or the `classify-task` GETs (deferred, as P0/P3 note); keyset pagination (offset/limit remains, with its inherent insert-shift — see design.md); restoring brute-force rate-limiting on the BFF's internal login path (a deploy/architecture decision flagged separately); and any new endpoint, model, or observation-creation path.

## Capabilities

### New Capabilities
- `api-authentication`: the backend's bearer-token validation contract — which failures are authentication failures (`401`, "clear the session") versus authorization failures (`403`, "you may not do this").
- `collection-ordering`: the deterministic, total ordering guarantee for the collection list endpoints, so "most recent" is meaningful and pagination is reproducible.
- `classify-task-fields`: the classify-task response schema exposing the persisted `created_at`/`updated_at` timestamps.

### Modified Capabilities
- None.

## Impact

- **Backend:** `backend/app/api/deps.py` (`_resolve_user` status codes); `backend/app/api/routes/observations.py`, `species.py`, `stations.py`, `classify_tasks.py` (add `.order_by(...)` to list queries); `backend/app/models/classify_task.py` (`ClassifyTaskPublic` gains `created_at`/`updated_at`). New pytest coverage under `backend/tests/api/`.
- **Database:** none — no Alembic migration (no schema change).
- **Deploy / Settings / Dependencies:** none.
- **Frontend:** no frontend files change here, but this **unblocks** P0 (the `401` BFF contract), P1 (most-recent ordering + stable pagination), and P3 (the classify-task table columns and most-recent-task badge). P0–P3 require **no edits** as a result of this change.
- **Sequencing:** build and archive this change **before** P0 (auth), P1 (ordering), and P3 (classify-task fields). Recommended order: `add-frontend-api-prerequisites` → P0 → P1 → P2 → P3.
