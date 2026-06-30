# Design — backend prerequisites for the SvelteKit frontend

Small, surgical backend change that makes three load-bearing assumptions in the P0–P3 frontend specs actually hold. Scoped deliberately tight so it can ship first and unblock the rewrite without touching the frontend changes.

## Decisions (and why)

| Decision | Choice | Why |
| --- | --- | --- |
| Fix the backend vs rework P0/P1/P3 | **Fix the backend** | P0 already specifies "a backend `401` clears the cookie"; P1 already says "most recent observations"; P3 already renders "created/updated timestamps". Making the backend match those statements keeps the four frontend changes valid as authored — the alternative (teaching the BFF to treat `403` as session-invalid, re-framing P1 away from "recent", and dropping P3's timestamp columns) spreads the same fix across three changes and degrades the product. |
| Auth: which failures become `401` | **All `_resolve_user` failures** (invalid/expired token, missing user, inactive user) | A BFF needs one unambiguous "this session is dead → clear the cookie" signal. RFC 7235: `401` = "lacks valid authentication credentials"; a token that is expired, or names a deleted/disabled principal, lacks valid credentials. Authorization decisions (role/ownership) on a *valid* principal stay `403`. |
| Keep `403` for authorization | **Yes — untouched** | `get_current_active_superuser` (`deps.py:78-83`) and the station/observation ownership checks (`stations.py:111-114`, etc.) are *authorization*, not authentication. P2/P3 scenarios depend on those exact `403`s. The change must not bleed `401` into them. |
| Ordering keys | observations/classify-tasks **`*_at` DESC**, species **`scientific_name` ASC**, stations **`created_at` DESC**, all with **`id` tiebreaker** | Product-meaningful recency for feeder events and tasks; alphabetical for a catalogue; newest-first for stations. `id` (a UUID, unique) makes every ordering *total*, so identical requests are byte-for-byte reproducible. |
| Pagination model | **Keep offset/limit** | Fixes the real bug (arbitrary heap order → non-reproducible pages) without a larger keyset-pagination rework. Offset/limit's inherent insert-shift remains (see Risks); acceptable for P1's volumes. |
| Classify-task timestamps | **Add to `ClassifyTaskPublic`, no migration** | The columns already exist on the `ClassifyTask` table (`classify_task.py:56-63`); exposing them on the response schema is purely additive and surfaces them in `openapi.json` → the generated client. |

## Auth: the `401` vs `403` contract

`backend/app/api/deps.py` `_resolve_user(session, token)` currently raises:

- `403 "Could not validate credentials"` on `InvalidTokenError | ValidationError` (expired/malformed/invalid-claims JWT) — **→ becomes `401`**
- `404 "User not found"` when the token's `sub` has no row — **→ becomes `401`** (same generic detail; do not leak which case)
- `400 "Inactive user"` when the user is deactivated — **→ becomes `401`**

`get_current_user` and `get_optional_current_user` flow through `_resolve_user`, so both the `(app)` guard path and optional-auth public path get the new code. The *missing-token* case already yields `401` via `OAuth2PasswordBearer(auto_error=True)` on `reusable_oauth2` — unchanged; `optional_oauth2(auto_error=False)` still returns `None` for the no-cookie public path.

**Untouched (stay `403`):** `get_current_active_superuser` (insufficient role) and the per-row ownership branches in `stations.py`/`observations.py`. A regression test asserts a non-superuser still gets `403` on a superuser route.

**Blast radius:** none on the existing suite — no current test asserts `403`/`404`/`400` on the bearer path (the inactive-user test at `tests/api/routes/test_login.py:42` exercises the *login* endpoint, which is unchanged). New tests assert the `401`s.

**Minimal-variant note (for the reviewer):** if a narrower change is preferred, converting only the `InvalidTokenError | ValidationError` branch to `401` satisfies P0's literal "expired or invalid token" requirement; the missing/inactive-user conversions additionally cover the admin-deactivates-a-logged-in-user edge case and give the BFF a single uniform signal. This design takes the fuller option.

## Ordering

Add an explicit `.order_by(...)` to each list query, before `.offset(skip).limit(limit)`:

- `observations.py` read_observations → `order_by(Observation.observed_at.desc(), Observation.id.desc())`
- `classify_tasks.py` read_classify_tasks → `order_by(ClassifyTask.created_at.desc(), ClassifyTask.id.desc())` (after the existing `status`/`observation` filters)
- `species.py` read__multiple_species → `order_by(Species.scientific_name.asc(), Species.id.asc())`
- `stations.py` read_stations → `order_by(Station.created_at.desc(), Station.id.desc())` (after the existing visibility filter)

The `count` query is unaffected. `observed_at`/`created_at` come from the fields verified to exist (`PerchPubBase.created_at` for Observation/Species/Station; `ClassifyTask.created_at`; `Observation.observed_at`).

## Classify-task timestamps

`ClassifyTaskPublic(ClassifyTaskBase)` adds `created_at: datetime` and `updated_at: datetime`. These read straight off the ORM instance (the table already has them), so serialization needs no other change. The generated client then types `task.created_at`/`task.updated_at`, satisfying P3 task 5.3's columns and giving 5.2 a field to confirm the most-recent ordering.

## Testing

- **pytest (auth):** an expired/garbage bearer on a protected route (`GET /users/me`) → `401`; a token for a deleted user → `401`; a token for an inactive user → `401`; a missing bearer → `401` (regression, already true); an authenticated **non-superuser** on a superuser route (`GET /users/`) → `403` (regression — authorization unchanged).
- **pytest (ordering):** seed ≥3 observations with distinct `observed_at` → `GET /observation/` lists them `observed_at`-descending; two identical `skip`/`limit` requests over an unchanged dataset return the identical order; species list is `scientific_name`-ascending; stations are `created_at`-descending; `GET /classify-task/?observation={id}` returns that observation's tasks most-recent-first.
- **pytest (timestamps):** `GET /classify-task/{id}` (and the list) includes `created_at` and `updated_at`; the generated OpenAPI schema lists both on `ClassifyTaskPublic`.

## Risks / open notes

- **Offset/limit insert-shift remains.** Ordering makes a page reproducible for a *static* dataset; concurrent inserts at the top of the order can still shift rows across page boundaries (a universal property of offset pagination). Keyset/cursor pagination is the future fix if it matters; out of scope here and not needed at P1 volumes.
- **`GET /observation/` still returns private-station observations to anonymous callers.** This change does **not** add visibility filtering — that inherited gap is explicitly accepted by P1 and deferred. Ordering does not change which rows are returned, only their order.
- **`observed_at` recency vs `created_at`.** Observations are ordered by `observed_at` (the feeder-event time) so "most recent observation" means most-recently-observed, not most-recently-ingested. If back-dated/back-filled observations should sort by ingestion instead, switch the key to `created_at` — a one-line change; flagged so the choice is explicit.
