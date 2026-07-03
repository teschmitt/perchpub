## Context

PerchPub has two user-facing paths that both end in a `Station` row, but only one produces a usable station:

- **Device-less create** — `/stations/new` → `POST /station/` (`backend/app/api/routes/stations.py:82`). Writes a `Station` immediately with `spki_sha256 = NULL`. Uploads authenticate over mTLS matched by `Station.spki_sha256`, so a NULL-SPKI station can never receive media, and nothing can bind a device to it later: `enroll_station` (`backend/app/api/routes/enrollment.py:200-229`) only reuses a station by SPKI match or creates a fresh one — it never adopts a NULL-SPKI row. The result is a zombie.
- **Enrollment** — `/enroll` → `POST /enrollment/create`, then the Raspberry Pi calls `POST /enrollment/confirm/{session_id}`, which signs the device CSR and creates the `Station` with a real `spki_sha256`. This is the only path to a working station, and it already does everything create does (coordinates, owner) — so it is a strict superset.

Today both sit as equal-weight peers (sidebar nav + three dashboard cards), and the more prominent, primary-styled control ("New station" on `/stations/mine`) is the broken one. The overwhelming majority of operators will own exactly one station, so first-station setup should be the guided next step after account creation, and additional stations should be quiet.

This change is frontend-heavy. The only backend change is threading an `is_private` choice from enrollment-create through to the `Station` created at confirm.

## Goals / Non-Goals

**Goals:**
- One canonical, user-facing station-setup flow (the enrollment wizard). No user-reachable path creates a device-less station.
- First-station setup is the recommended step immediately after signup; subsequent stations are possible but visually de-emphasized.
- Privacy (`is_private`) is chosen at setup and lands on the created station.
- Signup drops the user straight into first-station setup, with a friction-free "do it later" that keeps nudging from the dashboard.

**Non-Goals:**
- Rate limits, per-user station quotas, enrollment audit trail, station revocation, and certificate lifecycle. Those belong to the separate `harden-enrollment-for-multitenancy` change and are explicitly out of scope here.
- Removing or changing the backend `POST /station/` endpoint itself (kept for superuser tooling and tests).
- A map-based coordinate picker (still numeric lat/long, unchanged from today).
- Adopting a pre-existing device-less station during enrollment (we delete the device-less path rather than teach confirm to adopt).

## Decisions

### Decision 1 — Keep the `POST /station/` endpoint; remove only the device-less UI
The zombie problem is a *UI* problem: the endpoint is still wanted by superuser tooling and the existing pytest suite. We delete the `/stations/new` device-less form and repoint every user-facing "create" affordance at the enrollment wizard. **Alternative considered:** delete the endpoint outright — rejected because it churns backend tests and removes a legitimate superuser/test primitive for no user-facing benefit.

### Decision 2 — A device-less station is never legitimate; delete the path, no flag
There is no product scenario for a feeder with no camera. We remove the create-a-zombie path from every user surface outright rather than gating it behind a flag or role. **Alternative considered:** teach enrollment's `/confirm` to *adopt* an existing device-less station (create the pin now, pair the Pi later) — rejected as over-engineered for "most users have one station," and it keeps the zombie failure mode alive (a location with no device).

### Decision 3 — `is_private` rides the enrollment session onto the `Station`
The station is born at confirm, not at create, so the operator's privacy choice must be *stored* on the session and applied when the row is created. This means a new `is_private` column on the `station_enrollment` table (Alembic migration), not just a request field. Threading:
`EnrollmentSessionCreate.is_private` → `EnrollmentToken.is_private` (persisted at `/create`) → `Station(is_private=...)` in the `else`/new-station branch of `enroll_station` at confirm.
Re-enrollment (existing SPKI) leaves privacy untouched — consistent with how the confirm handler already treats coordinates as create-only and refuses to mutate an existing station's location on a cert refresh (`enrollment.py:214-227`). **Alternative considered:** default every enrolled station public and let the owner toggle privacy afterward on the edit page — rejected because it silently publishes a feeder's location for a window and adds a required second step; capturing it at setup is one field.

### Decision 4 — Signup auto-logs-in and hands off to first-station setup
Today signup returns a generic message and leaves the user at the login form (`frontend/src/routes/(public)/signup/+page.server.ts`). To make first-station setup the immediate next step, the signup action, on a successful `POST /users/signup`, chains into the password grant (`POST /login/access-token`) with the just-submitted credentials, sets the `pp_session` cookie via the existing BFF helpers (`sessionCookieOptions`, `SESSION_COOKIE`), and redirects into the setup workflow. A "do it later" control in the wizard returns the user to `/dashboard`, whose zero-stations onboarding hero is the *same* recommendation surfaced until a station exists — so "later" is never a dead end and needs no extra state.

**Auto-login chaining + anti-enumeration.** The backend keeps its non-enumeration property: `POST /users/signup` returns the same generic response whether or not the email already exists. The new observable is the *outcome* of the follow-up grant:
- Unregistered email → account created → grant with the submitted password succeeds → session + redirect to setup.
- Existing email (different password) → signup is a no-op → grant fails → fall back to the login form, asserting nothing about existence.

This narrows enumeration asymmetrically but does not fully close it — an accepted trade-off at this scale: positive confirmation that an email is *unregistered* is inseparable from having just registered it (self-defeating for probing — the probe squats the address). An *already-registered* email, however, is confirmable side-effect-free: a probe with an arbitrary password fails the grant and lands on the login form, so the redirect *destination* (login vs. first-station setup) is a clean existence oracle for registered addresses. That is strictly more than the login form itself leaks (which returns a uniform error for both a wrong password and a non-existent account), but it is acceptable for a self-hosted / small-multi-tenant service and closing it is deferred to `harden-enrollment-for-multitenancy`. We record this reasoning here rather than in the spec so the requirement stays crisp and testable.

### Decision 5 — The setup wizard lives at `/stations/new`
**Settled:** rename the enrollment wizard route to `/stations/new` and retire `/enroll`. `/stations/new` currently serves the device-less create form; that form is deleted and the route is repurposed to host the wizard, so the URL that reads as "create a station" *is* the canonical setup flow. The legacy `/enroll` route redirects (`308`) to `/stations/new` to preserve any existing links. **Alternative considered:** keep the wizard at `/enroll` and merely point the affordances at it (smaller diff, no route move) — rejected because leaving a separate, device-oriented `/enroll` create path perpetuates exactly the create-vs-enroll split this change exists to erase; `/stations/new` collapses the two into one mental model. The specs stay route-name-agnostic ("the station-setup wizard") except in `station-management`, which names the concrete `/stations/new` route it repurposes and the `/enroll` redirect.

## Risks / Trade-offs

- **[Auto-login weakens strict signup non-enumeration]** → As argued in Decision 4, enumeration is narrowed *asymmetrically*, not closed: confirming an *unregistered* address requires squatting it (self-defeating), but an *already-registered* address is confirmable side-effect-free — the redirect destination (login vs. first-station setup) is an existence oracle for registered emails. Documented and accepted for a self-hosted/small-multi-tenant service; closing the registered-address oracle is deferred to `harden-enrollment-for-multitenancy`'s siblings.
- **[Removing the device-less create is user-facing breaking]** → No data migration needed (no schema change to `station`); it is a UI/route change. Any existing NULL-SPKI zombie rows are orphaned already and unaffected; cleaning them up is out of scope (optionally note them for a superuser). `/stations/new` keeps working — it now serves the wizard — and bookmarks to the old `/enroll` wizard redirect to `/stations/new` rather than 404.
- **[`is_private` migration on `station_enrollment`]** → Additive, nullable/defaulted `False` column; safe forward migration, trivial rollback. Rows created before the migration simply default to public at confirm.
- **[Dashboard now needs a data load]** → The dashboard gains a `+page.server.ts` that counts owned stations (reusing the same `GET /station/` + `isOwnStation` filter as `/stations/mine`). One extra backend call on dashboard render; negligible, and consistent with existing loaders.
- **[Overlap with `harden-enrollment-for-multitenancy`]** → Complementary, not contradictory: both converge on "enrollment is the station lifecycle." That change will add a per-user cap on owned stations; the "Add station" affordance here must assume a quota may exist (i.e., surface a future "limit reached" gracefully) but implements none of it now.

## Migration Plan

1. Backend slice first (keeps the vertical testable in isolation): add `EnrollmentToken.is_private` column + Alembic migration; add `is_private` to `EnrollmentSessionCreate`; persist at `/create`; apply in the new-station branch at `/confirm`. Ship + green pytest before touching the frontend.
2. Wizard: add the `is_private` control and thread it through the enroll form action.
3. Route + app shell: delete the device-less `/stations/new` form and move the enrollment wizard from `/enroll` to `/stations/new`, redirecting `/enroll` → `/stations/new`; remove the "Enroll device" nav item; add the dashboard `+page.server.ts` station-count load and the zero-stations onboarding hero; demote `/stations/mine`'s create control to a secondary "Add station" pointing at `/stations/new`.
4. Signup handoff: chain signup → password grant → cookie → redirect into setup; wizard "do it later" → `/dashboard`.
5. Verify: frontend `npm run lint && npm run check && npm run test` + Playwright e2e on the real stack; backend `bash scripts/lint.sh && bash scripts/test.sh`; `openspec validate streamline-station-setup --strict`.

**Rollback:** each step is independently revertible; the only stateful piece is the additive `station_enrollment.is_private` column (drop to roll back).

## Open Questions

- **Zombie cleanup:** do we surface/offer deletion of any pre-existing NULL-SPKI stations (a superuser ops nicety), or leave them? Proposed: leave them, out of scope.
