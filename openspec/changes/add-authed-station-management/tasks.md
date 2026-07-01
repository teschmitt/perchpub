## 1. Owner station management (list + create)

- [x] 1.1 Create `frontend/src/routes/(app)/stations/+page.server.ts`: a `load` that fetches the owner's stations via the P0 generated client (`GET /station/`) using the request-scoped authed `fetch` from `event.locals`, and filters/marks the rows whose `owner.id === locals.user.id` as "mine" (the backend returns the owner's private stations because the bearer is forwarded). It sits under P0's `(app)` guard, so no extra auth check is needed here.
- [x] 1.2 Create `frontend/src/routes/(app)/stations/+page.svelte`: render the owner's stations (coordinates, `is_private` badge), a "New station" link to `stations/new`, and an "Edit" link per owned row to `stations/[id]/edit`.
- [x] 1.3 Create `frontend/src/routes/(app)/stations/new/+page.svelte` + `new/+page.server.ts`: a form with `latitude`, `longitude` (numeric inputs; range -90..90 and -180..180 mirroring `StationBase`) and an `is_private` checkbox; the default `create` action POSTs to `POST /station/` via the typed client (no hand-written URL) and redirects to `stations/` on success. Add a code comment noting the map picker is deferred (plain numeric coordinate inputs for now).
- [x] 1.4 Map backend validation/`{detail}` errors to typed `fail(...)` form errors and re-render the form with the submitted values.

## 2. Owner station edit

- [x] 2.1 Create `frontend/src/routes/(app)/stations/[id]/edit/+page.server.ts`: a `load` that fetches the station via the typed client (`GET /station/{id}`) and a default `update` action that PUTs to `PUT /station/{id}` with `latitude`, `longitude`, `is_private`.
- [x] 2.2 Create `frontend/src/routes/(app)/stations/[id]/edit/+page.svelte`: the edit form pre-filled from `load`, with the same fields and the `is_private` toggle.
- [x] 2.3 Surface the backend ownership responses cleanly: a `403` (foreign public station) and a `404` (foreign private station, or unknown id) from `PUT /station/{id}` map to an access-denied / not-found page state rather than a raw error.

## 3. Enrollment wizard

- [x] 3.1 Create `frontend/src/routes/(app)/enroll/+page.server.ts`: a `create` form action collecting `latitude`/`longitude` and calling `POST /enrollment/create` via the typed client; return the response `session_id`, the one-time cleartext `auth_token`, and `expires_at` to the page (only on this action's result — do not persist or re-expose the token).
- [x] 3.2 Create `frontend/src/routes/(app)/enroll/+page.svelte`: after a successful `create`, display `session_id` and `auth_token` **once**, each with a copy-to-clipboard button, plus a live countdown to `expires_at` (300s TTL) that disables copy/marks the token expired at zero. Show the operator instruction to run the enrollment on the Pi device (which performs `POST /enrollment/confirm/{session_id}` — out of browser scope).
- [x] 3.3 Add a "Check for the new station" action/load that re-fetches `GET /station/` and reports whether a newly enrolled station has appeared (there is no operator poll endpoint — confirmation is observed via the station list growing). Link to `stations/` on success.
- [x] 3.4 Add a small client-side component for the countdown + clipboard copy (Svelte 5 runes); keep the token value out of any URL, query string, or persisted store.

## 4. Account self-service

- [x] 4.1 Create `frontend/src/routes/(app)/account/+page.server.ts`: a `load` reading `GET /users/me` (or reusing `locals.user`) and three named form actions — `updateProfile` (`PATCH /users/me` with `full_name`, `email`), `changePassword` (`PATCH /users/me/password` with `current_password`, `new_password`), `deleteAccount` (`DELETE /users/me`).
- [x] 4.2 Create `frontend/src/routes/(app)/account/+page.svelte`: a profile section (full name, email), a change-password section (current + new password, min length 8 per `UpdatePassword`), and a destructive delete-account section behind a confirm step.
- [x] 4.3 On successful `deleteAccount`, clear the BFF session cookie and redirect to the public landing (reuse P0's logout cookie-clearing); surface the backend `403` for superuser self-deletion as a disabled/explained delete control.
- [x] 4.4 Map `changePassword` backend `400`s ("Incorrect password", "New password cannot be the same as the current one") and `updateProfile` `409` ("email already exists") to typed field errors.

## 5. Rebranded auth pages (login + signup)

- [x] 5.1 Rebrand `frontend/src/routes/login/+page.svelte` to PerchPub (P0 already provides the login form action + cookie); add a link to `signup`.
- [x] 5.2 Create `frontend/src/routes/(public)/signup/+page.svelte` + `(public)/signup/+page.server.ts`: a `register` form action POSTing `email`, `password`, `full_name` to `POST /users/signup` via the typed client. Because the backend returns the same generic message whether or not the email existed, the UI shows that generic confirmation and never asserts whether an account was created.
- [x] 5.3 Confirm both pages live in the `(public)` zone (no auth guard) and redirect an already-logged-in user away from login/signup.

## 6. Guards note

- [x] 6.1 Confirm every `(app)/stations`, `(app)/enroll`, and `(app)/account` route inherits P0's `(app)/+layout.server.ts` auth guard (redirect to `/login` when unauthenticated); add no per-page auth check.
- [x] 6.2 Add a code comment at the `(app)` admin boundary noting that P0's reusable **superuser guard** helper is reserved for P3 admin pages and is intentionally NOT applied to P2 owner pages (ownership is enforced per-row by the backend `PUT /station/{id}` and `DELETE /users/me`).

## 7. Tests and verification gate

- [x] 7.1 Vitest: the station create/edit form actions build the correct typed-client calls and map `{detail}` errors; the account actions map the `400`/`409` cases; the enrollment `create` action surfaces `session_id`/`auth_token`/`expires_at`; the countdown helper reports "expired" past `expires_at`.
- [x] 7.2 Playwright (P0 compose service): a logged-in owner creates a station and sees it in their list; editing toggles `is_private`; the enroll wizard shows the one-time token with a copy button and a running countdown; the account page changes the password and updates the profile; an unauthenticated visit to `(app)/stations` redirects to `/login`; signup shows the generic confirmation.
- [x] 7.3 Run frontend `npm run lint && npm run check && npm run test`. (No backend code changes in this phase; run `cd backend && bash scripts/lint.sh && bash scripts/test.sh` only if any backend file is touched.)
- [x] 7.4 Run `openspec validate add-authed-station-management --strict` and confirm the change validates.

## Implementation notes (deviations from the literal task text)

- **Owner list URL is `/stations/mine`, not `/stations`.** SvelteKit route groups add no URL segment, so `(app)/stations/+page` would resolve to `/stations` and collide with P1's canonical `(public)/stations/+page` (a hard `svelte-kit sync` error). The owner *list index* was relocated to `(app)/stations/mine/`; the child routes stay exactly as specified — `(app)/stations/new/` (`/stations/new`) and `(app)/stations/[id]/edit/` (`/stations/{id}/edit`) — since a static segment and P1's dynamic `[id]` coexist. The authed sidebar "My stations" link and the create/edit redirects point at `/stations/mine`. No spec scenario mandates a specific URL for the owner list.
- **In-sandbox gate is green** (`npm run lint`, `npm run check`, `npm run test:unit` → 92, `npm run build`, `openspec validate --strict`). The **Playwright e2e specs (7.2) are written but require the real compose stack** (backend + SSR preview) to run — same posture as the still-pending P0/P1 e2e runs. The unauthenticated-redirect spec targets `/stations/mine` (the relocated list).
