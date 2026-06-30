## Why

The SvelteKit foundation (P0) established the `(app)` authed zone and a superuser guard reserved for `admin/`, but built no superuser surface. P1 built public observation/species/station browsing; P2 built the owner-facing management zone. None of the operator-only tooling the backend already exposes has a UI: there is no way to manage user accounts, to correct a misclassified observation, to see whether an observation's classification actually ran (or failed), or to exercise the ops endpoints (health-check, test-email). Operators do this today by hand-crafting authenticated API calls.

This change (P3 — superuser/advanced) builds the superuser tools on top of P0 and P1. It reuses the superuser guard introduced in P0 (`(app)/admin/+layout.server.ts` asserting `locals.user.is_superuser`, with the backend's `get_current_active_superuser` dependency as defense-in-depth) and extends the P1 `observation-browsing` capability with a manual-reclassification control and a classification-status surface. It depends on **add-sveltekit-frontend-foundation (P0)** being built first (the app shell, BFF auth, generated client, and superuser guard) and on **add-public-browsing (P1)** for the observation detail page it augments. It does not depend on P2.

This change is UI-only over endpoints the backend already ships. Two backend facts are inherited, not fixed here, and shape the requirements below: the `PUT /observation/{id}` correction endpoint is superuser-guarded (`get_current_active_superuser`), and the `GET /classify-task/` and `GET /classify-task/{id}` reads currently carry **no** backend auth dependency — so the classification-status surface is read-only and the spec does not assume per-row authorization on those reads.

## What Changes

- **Admin user management page** under `(app)/admin/users/` (behind the superuser guard): list users (`GET /users/`), create (`POST /users/`), edit (`PATCH /users/{id}`), and delete (`DELETE /users/{id}`) via SvelteKit form actions on the typed client. Edit exposes toggles for `is_active` and `is_superuser` (both fields of `UserUpdate`).
- **Manual reclassification control** on the observation detail page (P1's `(public)/observations/[id]`): rendered only for a superuser, a control that sets `species_id` and submits `PUT /observation/{id}` with `manually_classified = true` (a server-side form action; the backend endpoint is superuser-guarded).
- **Classification status badge** on observations: an inline badge showing the observation's classification task status — Prepared / Queued / Processing / Success / Failed (`ClassifyTaskStatus`) — derived from `GET /classify-task/?observation={id}`.
- **Admin classify-task list** under `(app)/admin/classify-tasks/`: a server-rendered table over `GET /classify-task/`, filterable by `status` and `observation` (the two query params the endpoint accepts), each row linking to its observation. Read-only (the underlying GETs have no backend auth; the page is still gated client-side behind the superuser guard).
- **Ops panel** under `(app)/admin/ops/`: displays the result of `GET /utils/health-check/` (public) and offers a form action to send a test email via `POST /utils/test-email/` (superuser-guarded).
- **Out of scope (non-goals):** adding backend auth to the `classify-task` GETs (a known backend gap, flagged in P0's design, not fixed here); per-row classify-task authorization; any new backend endpoint or model/migration; re-queuing or cancelling a classify task (no backend endpoint exists); changing the owner-facing P2 station/account pages; bulk user operations.

## Capabilities

### New Capabilities
- `admin-user-management`: superuser-only management of user accounts from the web frontend — listing, creating, editing (including the `is_active` and `is_superuser` toggles), and deleting users through the typed client and SvelteKit form actions, behind the server-side superuser guard.

### Modified Capabilities
- `observation-browsing`: adds a superuser manual-reclassification control (sets the species and marks the observation `manually_classified`) and surfaces classification-task status as a per-observation badge plus a superuser-only classify-task list.

## Impact

- **Frontend:** new routes under the existing `(app)/admin/` superuser zone — `admin/users/` (list/create/edit/delete with form actions), `admin/classify-tasks/` (filterable list), `admin/ops/` (health-check + test-email); a superuser-only reclassification form and a status badge component added to P1's observation detail page; admin nav entries in the `(app)` console shell. All API access via the generated typed client; all mutations via server-side form actions.
- **Backend:** none. All endpoints (`/users/*`, `PUT /observation/{id}`, `GET /classify-task/*`, `/utils/health-check/`, `/utils/test-email/`) already exist. No model or migration change.
- **Deploy:** none.
- **Settings:** none. (`POST /utils/test-email/` is functional only when the backend's email settings are configured; the page surfaces the backend's response/error rather than introducing config.)
- **Dependencies:** none new — reuses the P0 generated client, BFF auth, and superuser guard.
