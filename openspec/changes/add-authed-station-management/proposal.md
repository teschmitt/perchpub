## Why

P0 (`add-sveltekit-frontend-foundation`) built the SvelteKit shell — BFF cookie auth, the `(public)`/`(app)` zones with a server-side guard, the generated typed client, and the media path — but no product pages. P1 (`add-public-browsing`, the public observation/species/station read surface) introduces the `station-management` capability with the *public, read-only* station view and the `(public)/stations/` pages. **This change (P2) depends on both P0 and P1 being built first**: it reuses P0's `(app)` auth guard and BFF authed `fetch`, and it adds the *owner-facing write* side to the `station-management` capability P1 created.

Today an owner has no way, from the browser, to create a station, edit its privacy/coordinates, enroll a Raspberry Pi device, or manage their own account — the backend exposes all of it (`POST /station/`, `PUT /station/{id}`, `POST /enrollment/create`, `GET/PATCH/DELETE /users/me`, `PATCH /users/me/password`, `POST /users/signup`) but no UI calls it. This change delivers the authenticated management surface in the `(app)` zone plus the rebranded public login/signup pages, all through the P0 generated typed client and SvelteKit form actions.

Two backend facts shape the UI and are honored, not changed, here: enrollment is **operator-starts / device-finishes** — `POST /enrollment/create` returns a `session_id`, a one-time **cleartext** `auth_token`, and `expires_at` (300s TTL), while the device-side `POST /enrollment/confirm/{session_id}` is performed by the Pi and is **out of browser scope**; and there is **no operator-facing poll endpoint**, so the wizard confirms a successful enrollment by re-fetching the owner's station list (a new `Station` row appears once the device confirms). A station-coordinate **map picker is explicitly deferred** — coordinates are plain numeric `latitude`/`longitude` inputs.

## What Changes

- **Owner station management (`(app)/stations/`).** A list of the logged-in user's own stations, a create form (`POST /station/` — `latitude`, `longitude`, `is_private`; `owner_id` is set server-side from the caller), and an edit form (`PUT /station/{id}` — owner-or-superuser only; backend returns `403` on a public foreign station and `404` on a private one). All mutations are SvelteKit form actions running server-side with the BFF bearer.
- **Enrollment wizard (`(app)/enroll/`).** An operator form collects the new station's `latitude`/`longitude` and calls `POST /enrollment/create`; the UI then shows the returned `session_id` and the one-time `auth_token` **once**, with a copy-to-clipboard action and a live countdown to `expires_at` (300s). It instructs the operator to run the enrollment on the Pi, then confirms completion by re-fetching `GET /station/` and reporting when the newly enrolled station appears (no operator poll endpoint exists; the device performs `confirm`).
- **Account self-service (`(app)/account/`).** View and update profile (`GET /users/me`, `PATCH /users/me` — `full_name`, `email`), change password (`PATCH /users/me/password` — `current_password`, `new_password`), and delete the account (`DELETE /users/me`, which the backend forbids for superusers) — each via a form action, with logout/redirect after deletion.
- **Rebranded auth pages.** A PerchPub-branded login page (P0 already wires the login form action and cookie) and a public signup page (`POST /users/signup`, which returns a generic message regardless of whether the email was taken, so the UI never confirms account existence).
- **Guards.** Every page above lives in P0's `(app)` zone behind the server-side auth guard; the proposal notes where P0's reusable **superuser guard** helper will be reused by P3 admin areas (none of P2's owner pages need it — ownership is enforced per-row by the backend).
- **Out of scope (non-goals):** the device-side `POST /enrollment/confirm/{session_id}` flow (performed by the Pi, not the browser); any operator-facing enrollment poll/status endpoint; a station-coordinate map picker; admin/superuser user management pages (P3); password-reset email flow (backend stub only).

## Capabilities

### New Capabilities
- `user-account`: browser self-service for the logged-in user's own account — view/update profile, change password, delete the account — plus public self-registration (signup).

### Modified Capabilities
- `station-management`: adds owner-facing **create** and **edit** of one's own stations (privacy toggle + coordinates), on top of the public read view P1 introduced.
- `station-enrollment`: adds the operator **enrollment-wizard UI** — starting a session and presenting the one-time `auth_token`/`session_id` with a countdown and copy action, then confirming via the station list — on top of the existing device/CA enrollment requirements.

## Impact

- **Frontend:** new `(app)/stations/` (list-own, `new/`, `[id]/edit/`) with `+page.server.ts` load + form actions; new `(app)/enroll/` wizard (`+page.server.ts` with a `create` action + a `confirm`/refresh load); new `(app)/account/` (`+page.server.ts` with `updateProfile`, `changePassword`, `deleteAccount` actions); rebranded `login/` page UI and a new `signup/+page.server.ts` form action. A small client-side countdown + copy-to-clipboard component for the wizard. All API access via the P0 generated typed client (`/station`, `/enrollment/create`, `/users/me`, `/users/me/password`, `/users/signup`).
- **Backend:** none — all endpoints already exist (`backend/app/api/routes/stations.py`, `enrollment.py`, `users.py`) with `owner_id` wired and ownership enforced server-side. No model or migration changes.
- **Deploy:** none beyond P0's cutover.
- **Settings:** none.
- **Dependencies:** none beyond P0's stack (SvelteKit, `openapi-fetch`, the generated client); P2 adds no new packages.
