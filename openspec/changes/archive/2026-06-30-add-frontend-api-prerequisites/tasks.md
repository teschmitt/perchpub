## 1. Auth: bearer-validation failures return 401

- [x] 1.1 (test-first) Add `backend/tests/api/test_auth_contract.py` asserting, against a JWT-protected route (`GET {API_V1_STR}/users/me`): an **expired** JWT → `401`; a **malformed/garbage** bearer → `401` with detail `"Could not validate credentials"`; a valid-shaped JWT whose `sub` is a **deleted** user → `401`; a valid JWT for an **inactive** user → `401`; and **no** bearer → `401`. Add a regression case: a **non-superuser** token on a superuser route (`GET {API_V1_STR}/users/`) still returns `403`. Build the expired/forged tokens via `app.core.security.create_access_token` with a past `expires_delta` (and a hand-forged "sub points at a random uuid" token for the deleted-user case). These all fail today (the bearer path returns `403`/`404`/`400`).
- [x] 1.2 Change `_resolve_user` in `backend/app/api/deps.py:43-59`: raise `HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")` for the `(InvalidTokenError, ValidationError)` branch (was `403`); raise `401` (same generic detail) when `session.get(User, sub)` is `None` (was `404 "User not found"`); raise `401` when the user is inactive (was `400 "Inactive user"`). Do **not** touch `get_current_active_superuser` (`deps.py:78-83`) or any station/observation ownership branch — authorization stays `403`.
- [x] 1.3 Confirm the change does not bleed into authorization: `get_current_active_superuser` still returns `403`; the per-row station checks in `backend/app/api/routes/stations.py:111-114` (403 public / 404 private) are unchanged. Grep the suite for any assertion of `403`/`404`/`400` on the *bearer-resolution* path and update it (current grep: none — the inactive-user test at `tests/api/routes/test_login.py:42` targets the login endpoint and is unaffected).

## 2. Deterministic, most-recent-first collection ordering

- [x] 2.1 (test-first) Add ordering assertions (extend `backend/tests/api/routes/test_observations.py` or add one): seed ≥3 observations with distinct `observed_at`; `GET /observation/` returns them `observed_at`-descending; two identical `skip`/`limit` requests over an unchanged dataset return the identical order. Add equivalent assertions for `GET /species/` (`scientific_name` ascending), `GET /station/` (`created_at` descending, visibility filter still applied), and `GET /classify-task/?observation={id}` (that observation's tasks `created_at`-descending, most-recent first). These fail today (no `ORDER BY`).
- [x] 2.2 `backend/app/api/routes/observations.py` read_observations: add `.order_by(Observation.observed_at.desc(), Observation.id.desc())` to the `statement` before `.offset(skip).limit(limit)` (line 28). Leave the `count` query unchanged.
- [x] 2.3 `backend/app/api/routes/species.py` read__multiple_species: add `.order_by(Species.scientific_name.asc(), Species.id.asc())` to the list `statement` (line 22).
- [x] 2.4 `backend/app/api/routes/stations.py` read_stations: add `.order_by(Station.created_at.desc(), Station.id.desc())` after the existing visibility filter and before `offset`/`limit`.
- [x] 2.5 `backend/app/api/routes/classify_tasks.py` read_classify_tasks: add `.order_by(ClassifyTask.created_at.desc(), ClassifyTask.id.desc())` to the `stmt` after the `status`/`observation` filters and before `.offset(skip).limit(limit)` (line 43).

## 3. Expose classify-task timestamps

- [x] 3.1 (test-first) Assert `GET /classify-task/{id}` and `GET /classify-task/` responses include `created_at` and `updated_at` for each task (extend `backend/tests/api/routes/test_classify_tasks.py` or add one). Fails today (fields absent from `ClassifyTaskPublic`).
- [x] 3.2 `backend/app/models/classify_task.py`: add `created_at: datetime` and `updated_at: datetime` to `ClassifyTaskPublic` (lines 66-69). No migration — the columns already exist on the `ClassifyTask` table (`classify_task.py:56-63`).
- [x] 3.3 Confirm the timestamps now appear on `ClassifyTaskPublic` in the generated OpenAPI schema (dump `app.main.app.openapi()` and assert both keys), so P3's generated client will type them.

## 4. Verify and gate

- [x] 4.1 Run the backend gate from `backend/`: `bash scripts/lint.sh` (mypy + ruff) and `bash scripts/test.sh`; confirm all green. Confirm no Alembic migration was generated (`alembic revision --autogenerate` would be empty — schema is unchanged).
- [x] 4.2 Run `openspec validate add-frontend-api-prerequisites --strict` and confirm the change validates.
- [x] 4.3 Sanity-check the unblocking: the `GET /users/me` 401 path matches P0's BFF expiry handling; `GET /observation/` is most-recent-first for P1's landing; `ClassifyTaskPublic` carries timestamps for P3's table. (No frontend code is touched in this change.)
