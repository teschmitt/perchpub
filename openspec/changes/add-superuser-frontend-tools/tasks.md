## 1. Regenerate the typed client and confirm admin endpoints

- [x] 1.1 Run `frontend/scripts/generate-client.sh` against the running backend and confirm `src/lib/api/schema.d.ts` includes `GET/POST /users/`, `PATCH/DELETE /users/{user_id}`, `PUT /observation/{id}`, `GET /classify-task/` (with `status` + `observation` query params), `GET /classify-task/{id}`, `GET /utils/health-check/`, and `POST /utils/test-email/`.
- [x] 1.2 Confirm the generated types expose the fields this change relies on: `UserUpdate.is_active` / `UserUpdate.is_superuser` / `UserUpdate.password`, `UserCreate` (`email`, `password`, `is_active`, `is_superuser`, `full_name`), `ObservationUpdate` (`species_id` + `manually_classified` **and** the inherited, required `confidence_score` + `classification_result`), and the `ClassifyTaskStatus` enum (`Prepared|Queued|Processing|Success|Failed`).

## 2. Admin user management page

- [x] 2.1 Add the route group `frontend/src/routes/(app)/admin/users/+page.server.ts` with a `load` that calls `GET /users/` (typed client, server-side, bearer forwarded) and returns `{ data, count }` from `UsersPublic`. Render the list in `+page.svelte` (email, full_name, is_active, is_superuser, id).
- [x] 2.2 Add a create form action (`?/create`) that POSTs `UserCreate` to `POST /users/`; surface the backend `400` "user already exists" `{detail}` as a form error.
- [x] 2.3 Add an edit route `frontend/src/routes/(app)/admin/users/[id]/+page.server.ts` + `+page.svelte` whose `update` action PATCHes `UserUpdate` to `PATCH /users/{user_id}`, including `is_active` and `is_superuser` checkboxes and an optional password field; surface `404`/`409` `{detail}`.
- [x] 2.4 Add a delete action (`?/delete`) calling `DELETE /users/{user_id}`; surface the backend `403` (superuser cannot delete self) `{detail}` as a form error rather than a crash.
- [x] 2.5 Confirm all four operations run through the generated typed client (no hand-written URLs) and all mutations are SvelteKit form actions (no client-only fetches).

## 3. Superuser guard coverage for the admin zone

- [x] 3.1 Confirm the P0 `(app)/admin/+layout.server.ts` superuser guard covers the new `admin/users/`, `admin/classify-tasks/`, and `admin/ops/` routes (non-superuser authed user is redirected/404'd before any admin `load` runs).
- [x] 3.2 Add the admin nav entries (Users, Classify tasks, Ops) to the `(app)` console shell, shown only when `locals.user.is_superuser`.

## 4. Manual reclassification on the observation detail page

- [x] 4.1 In P1's `frontend/src/routes/(public)/observations/[id]/+page.svelte`, render a reclassification control **only** when `locals.user?.is_superuser`: a species selector (populated from the species list via `GET /species/`, wrapper `SpeciesMultiPublic`) plus a submit.
- [x] 4.2 Add a `?/reclassify` form action in `frontend/src/routes/(public)/observations/[id]/+page.server.ts` that PUTs a **complete** `ObservationUpdate` to `PUT /observation/{id}` via the typed client: `species_id` = chosen species, `manually_classified = true`, and `confidence_score` + `classification_result` carried over unchanged from the loaded observation (both are required on `ObservationUpdate`; `ObservationPublic` exposes them, so the detail `load` already has them — a `{species_id, manually_classified}`-only body 422s). The backend endpoint is superuser-guarded, so surface a backend `403` `{detail}` if a non-superuser somehow reaches it.
- [x] 4.3 After a successful reclassify, the page reflects the new species and a "manually classified" indicator (re-`load` the observation).

## 5. Classification status surface

- [x] 5.1 Add a status-badge component (`frontend/src/lib/components/ClassifyStatusBadge.svelte`) mapping `ClassifyTaskStatus` to a labelled badge (Prepared / Queued / Processing / Success / Failed), with a distinct style for `Failed`.
- [x] 5.2 On the observation detail page, fetch the observation's classify tasks via `GET /classify-task/?observation={id}` in `load` and render the most-recent task's status as the badge (no badge when there are no tasks).
- [x] 5.3 Add the admin classify-task list `frontend/src/routes/(app)/admin/classify-tasks/+page.server.ts` + `+page.svelte`: `load` reads `GET /classify-task/` passing `status` and `observation` query params from the URL search params; render a table (status badge, observation link, object_name, created/updated timestamps) with status + observation filter controls. Read-only.
- [x] 5.4 Note in code (comment) that the classify-task GETs have no backend auth dep; the list is gated only by the client-side superuser guard and is read-only.

## 6. Ops panel

- [x] 6.1 Add `frontend/src/routes/(app)/admin/ops/+page.server.ts` + `+page.svelte`: `load` calls `GET /utils/health-check/` and displays the boolean result (healthy / unreachable on error).
- [x] 6.2 Add a `?/test-email` form action calling `POST /utils/test-email/` (query param `email_to`); display the backend `{message}` on success and the `{detail}` on failure (e.g. email not configured).

## 7. Tests

- [x] 7.1 Playwright: a non-superuser authed user visiting `/admin/users` is redirected away (guard); a superuser sees the user list.
- [x] 7.2 Playwright: superuser edits a user, toggles `is_active` and `is_superuser`, and the saved values render on reload; creating a duplicate-email user shows the backend error.
- [x] 7.3 Playwright: on an observation detail page, the reclassify control is absent for an anonymous/non-superuser visitor and present for a superuser; submitting it sets the species and shows the "manually classified" indicator.
- [x] 7.4 Playwright/Vitest: the status badge renders the correct label per `ClassifyTaskStatus`; the admin classify-task list applies the `status` and `observation` filters from the URL.
- [x] 7.5 Playwright: the ops panel shows the health-check result and surfaces the test-email response/error.

## 8. Verify and gate

- [x] 8.1 Run the frontend checks: `cd frontend && npm run lint && npm run check && npm run test` (Vitest) and the Playwright suite; confirm all pass. (No backend code changes — backend lint/test not required unless the client regen surfaces a schema fix.)
- [x] 8.2 Run `openspec validate add-superuser-frontend-tools --strict` and confirm the change validates.
