> Work top to bottom. Each `#### Scenario` in the spec deltas is an acceptance test — write it failing first, then implement (TDD). Backend slice ships and goes green before any frontend work. Verify with the real commands (§6); a checked box is not evidence.

## 1. Backend — `is_private` enrollment slice (TDD)

- [x] 1.1 Write failing pytest (`backend/tests/api/routes/test_enrollment.py`): confirm with a session created `is_private=true` yields a new `Station.is_private == True` (scenario: *a private-at-setup enrollment yields a private station*).
- [x] 1.2 Write failing pytest: session created without `is_private` (omitted) yields a new `Station.is_private == False` (scenario: *privacy defaults to public when omitted*).
- [x] 1.3 Write failing pytest: re-enrolling an existing device (same SPKI) through a session whose `is_private` differs leaves the existing station's `is_private` unchanged (scenario: *re-enrollment does not alter existing privacy*).
- [x] 1.4 Add `is_private: bool = False` to `EnrollmentSessionCreate` and an `is_private` column (default `False`) to the `EnrollmentToken` table in `backend/app/models/enrollment.py`.
- [x] 1.5 Generate the Alembic migration for `station_enrollment.is_private` (`alembic revision --autogenerate -m "add is_private to station_enrollment"`); review it (additive, defaulted `False`) and `alembic upgrade head`.
- [x] 1.6 Persist `is_private` on the `EnrollmentToken` in `create_enrollment_session`; apply `enrollment_session.is_private` to the `Station(...)` built in the **new-station** branch of `enroll_station` (leave the existing-SPKI reuse branch untouched) in `backend/app/api/routes/enrollment.py`.
- [x] 1.7 Run `bash scripts/lint.sh && bash scripts/test.sh`; tasks 1.1–1.3 now pass and the existing enrollment/regression tests stay green.

## 2. Frontend — relocate the wizard to `/stations/new` + privacy (TDD)

- [x] 2.1 Regenerate the typed API client so `EnrollmentSessionCreate` carries `is_private` (run the committed generate-client script against the backend).
- [x] 2.2 Route move (TDD): delete the device-less `frontend/src/routes/(app)/stations/new/` (`+page.svelte`, `+page.server.ts`, `create-action.spec.ts`); relocate the enrollment wizard from `frontend/src/routes/(app)/enroll/` into `frontend/src/routes/(app)/stations/new/` (page, server action, and its specs — `enroll-action.spec.ts`, `enroll-qr.spec.ts`, etc.); add a `308` redirect from `/enroll` to `/stations/new`. Tests: `/stations/new` serves the wizard and no device-less create form; `/enroll` redirects (scenarios: *`/stations/new` serves the setup wizard, not a device-less form* / *the legacy enroll route redirects to the setup wizard*).
- [x] 2.3 Write failing Vitest for the wizard `create` action (now at `(app)/stations/new/`): a submitted `is_private` is forwarded in the `POST /enrollment/create` body (scenario: *the operator chooses the station's privacy at setup*); assert the lat/long path still works (regression: *an operator starts an enrollment session*).
- [x] 2.4 Add an `is_private` checkbox to the wizard form (`(app)/stations/new/+page.svelte`) and thread it through `parseStationForm`/the create action in `+page.server.ts`.
- [x] 2.5 `npm run lint && npm run check && npm run test` green.

## 3. Frontend — app shell: nav + dashboard onboarding + quiet add-station (TDD)

- [x] 3.1 Write failing test: the `(app)` sidebar shows Dashboard / My stations / Account and **no** standalone "Enroll device" item (scenario: *the sidebar has no standalone enroll destination*). Remove the `nav-enroll` link from `frontend/src/routes/(app)/+layout.svelte`.
- [x] 3.2 Write failing test for a new dashboard `load` (`frontend/src/routes/(app)/dashboard/+page.server.ts`): it counts the user's owned stations (reusing `GET /station/` + `isOwnStation`, as `stations/mine` does). Implement the loader.
- [x] 3.3 Write failing test: dashboard with **zero** owned stations renders a prominent "set up your first station" CTA linking to `/stations/new`; with **≥1** it does not (scenarios: *a user with no stations sees the setup call to action* / *a user with a station sees the normal dashboard*). Implement in `dashboard/+page.svelte`, replacing the equal-weight three-card layout.
- [x] 3.4 Write failing test: `/stations/mine` shows a **secondary** "Add station" action linking to `/stations/new`, no primary "New station" button, and its empty state points to `/stations/new` (scenarios: *the station list offers a quiet Add-station action* / *the empty station list points to the setup wizard*). Update `stations/mine/+page.svelte`.
- [x] 3.5 `npm run lint && npm run check && npm run test` green.

## 4. Frontend — signup auto-login + handoff (TDD)

- [x] 4.1 Write failing Vitest for the signup action (`frontend/src/routes/(public)/signup/+page.server.ts`): on a successful signup it performs the password grant, sets the `pp_session` cookie, and redirects into first-station setup (`/stations/new`) (scenario: *a new visitor is signed in and sent to first-station setup*).
- [x] 4.2 Write failing Vitest: when the follow-up grant fails (existing email / different password), the action sets no session and falls back to the login form, asserting nothing about existence (scenario: *signup for an existing email falls back to login without enumeration*); keep the authenticated-redirect regression (scenario: *an authenticated user is redirected away from signup*).
- [x] 4.3 Implement the signup → `POST /login/access-token` chain using the existing BFF helpers (`SESSION_COOKIE`, `sessionCookieOptions`), then `redirect` to `/stations/new`; keep the anti-enumeration fallback.
- [x] 4.4 Write failing test + implement the wizard "do it later" escape → `/dashboard`, creating no station (scenario: *a user defers first-station setup*). Confirm the dashboard hero still shows for the zero-station user afterward.
- [x] 4.5 `npm run lint && npm run check && npm run test` green.

## 5. End-to-end (real stack)

- [x] 5.1 Playwright e2e: signup → auto-login → land on `/stations/new` (first-station setup wizard); assert redirect + session cookie.
- [x] 5.2 Playwright e2e: "do it later" from the wizard → dashboard still shows the "set up your first station" hero (zero stations).
- [x] 5.3 Playwright e2e: enroll with `is_private` checked → after device confirm, the station appears private in `/stations/mine`.
- [x] 5.4 Playwright e2e: `/stations/new` serves the setup wizard (not a device-less form) and `/enroll` redirects to it; `/stations/mine` add-station is a secondary action to `/stations/new`; sidebar has no "Enroll device" item.

## 6. Verify, review, archive

- [x] 6.1 Backend: `bash scripts/lint.sh && bash scripts/test.sh` (green: mypy/ruff clean, 150 passed / 6 deselected).
- [x] 6.2 Frontend: `npm run lint && npm run check && npm run test` green (lint 0, check 504 files 0 errors, Vitest 141 passed). Playwright suite **verified green on the host: 42/42 passed** (incl. station-setup ×4, signup ×3, owner-stations ×3, enroll-wizard ×2).
- [x] 6.3 `openspec validate streamline-station-setup --strict` passes.
- [x] 6.4 `requesting-code-review` done; the one Important finding (overstated anti-enumeration claim) is fixed in `user-account`/`design.md`; Minors (100-row count window, email prefill) accepted/deferred to `harden-enrollment-for-multitenancy`.
- [x] 6.5 Archive the change (`opsx:archive`), folding the four deltas into `openspec/specs/` — after the host Playwright run (6.2) is green.
