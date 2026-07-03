## Why

PerchPub exposes **two** overlapping ways to make a `Station`, and one is a foot-gun. "Create new station" (`POST /station/`) writes a `Station` row immediately with `spki_sha256 = NULL` — a station that can **never** receive an upload (uploads authenticate over mTLS matched by `Station.spki_sha256`) and that no device can ever be bound to afterward (enrollment's `/confirm` only ever *creates* its own station or reuses one by SPKI; it never adopts a NULL-SPKI row). It is a zombie. Meanwhile "Enroll a device" already creates the real, working station as a side effect — so enrollment is a strict superset of create, and the standalone create path produces nothing but dead rows a user mistakes for feeders.

The overwhelming majority of operators will own exactly **one** station. Setting up that first station should be the recommended first step immediately after account creation; adding further stations should be possible but quiet. Today the two paths sit as equal-weight peers in the nav and dashboard, and the more prominent, primary-styled button ("New station") is the broken one.

## What Changes

- **Unify station creation and device enrollment into one canonical "set up a station" wizard.** The enrollment flow (coordinates + device pairing/QR) becomes the single station-setup route users see.
- **BREAKING (user-facing):** Remove the device-less create UI at `/stations/new`. A station without a paired device is never a legitimate artifact and is removed from every user-facing surface — no flag, no fallback. The backend `POST /station/` endpoint is **kept** (superuser tooling and the test suite still use it); only the user's path to it is retired.
- **"Add station" becomes a quiet secondary action** on the My-stations list, pointing at the wizard. No dashboard card, no nav item, no primary-styled button for subsequent stations.
- **Capture `is_private` during enrollment.** Add `is_private` to the enrollment session so privacy is chosen at setup and carried onto the `Station` when the device confirms (today enrollment ignores privacy and every enrolled station lands public). Requires a new column on the `station_enrollment` table and an Alembic migration, because the `Station` is born at confirm time, not create time.
- **Remove "Enroll device" from the sidebar nav.** It is not a destination; it is the *create* action, reachable from the dashboard onboarding hero and the My-stations "Add station" button.
- **Make the dashboard onboarding-aware.** With zero owned stations it leads with a prominent "set up your first station" hero; with one or more it shows the normal dashboard. This is the standing recommendation until the user owns a working station.
- **Signup auto-logs-in and hands off to the first-station workflow**, with a "do it later" escape that lands on `/dashboard` (where the same onboarding hero keeps nudging). The signup action chains into the password grant with the just-entered credentials and sets the session cookie; anti-enumeration is preserved because a pre-existing account with a different password simply fails the follow-up grant and falls back to the login form.

## Capabilities

### New Capabilities
<!-- None. All behavior changes land as deltas on existing capabilities. -->

### Modified Capabilities
- `station-management`: retire the device-less create UI; "Add station" is a quiet secondary action pointing at the setup wizard; subsequent-station creation is de-emphasized (no dashboard card, no nav item, no primary button). The device-less `POST /station/` create path is no longer user-reachable.
- `station-enrollment`: the enrollment wizard is the canonical station-setup flow; `is_private` is captured at session creation and carried onto the `Station` at confirm.
- `user-account`: signup auto-logs-in and hands the user off into the first-station workflow, with a defer-to-later escape.
- `web-frontend`: remove "Enroll device" from the sidebar nav; the dashboard becomes onboarding-aware (0 stations → "set up your first station" hero, ≥1 → normal dashboard); the setup wizard carries a "do it later" escape to `/dashboard`.

## Impact

- **Frontend (majority of the work):**
  - Repurpose `/stations/new` as the setup wizard: delete the device-less `frontend/src/routes/(app)/stations/new/+page.svelte`, its `+page.server.ts`, and `create-action.spec.ts`, then **move** the enrollment wizard from `frontend/src/routes/(app)/enroll/` into `frontend/src/routes/(app)/stations/new/`. Redirect the legacy `/enroll` route to `/stations/new`.
  - `frontend/src/routes/(app)/stations/mine/+page.svelte` — demote "New station" to a quiet "Add station" secondary action pointing at the wizard; update the empty-state copy.
  - `frontend/src/routes/(app)/+layout.svelte` — remove the "Enroll device" nav item.
  - `frontend/src/routes/(app)/dashboard/+page.svelte` + new `+page.server.ts` — load owned-station count and render the onboarding hero when zero.
  - The relocated wizard at `frontend/src/routes/(app)/stations/new/` — add the `is_private` control and thread it through the create action; add a "do it later" escape to `/dashboard`.
  - `frontend/src/routes/(public)/signup/+page.server.ts` — chain into the password grant, set the session cookie, redirect into the first-station workflow; keep the anti-enumeration fallback.
- **Backend (single vertical slice):**
  - `backend/app/models/enrollment.py` — add `is_private` to `EnrollmentSessionCreate` and an `is_private` column to the `EnrollmentToken` table.
  - `backend/app/api/routes/enrollment.py` — persist `is_private` on the session at `/create` and apply it to the `Station(...)` built at `/confirm`.
  - New Alembic migration adding `station_enrollment.is_private` (default `False`).
- **Non-goals / out of scope:** rate limits, quotas, per-user station caps, revocation, and cert lifecycle — those belong to the separate `harden-enrollment-for-multitenancy` change, which is complementary and must not be contradicted here (the "Add station" affordance should assume a station quota may later exist).
- **Tests:** Vitest for the SvelteKit server actions/loaders; Playwright e2e for the onboarding + setup flow (needs the real stack); pytest for the `is_private` enrollment slice; `openspec validate --strict`.
