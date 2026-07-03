## REMOVED Requirements

### Requirement: Owner creates a station

**Reason**: The device-less create form persisted a `Station` with `spki_sha256 = NULL` — a station that can never authenticate an mTLS upload and that no device can ever be bound to afterward (enrollment's `/confirm` only creates its own station or reuses one by SPKI; it never adopts a NULL-SPKI row). It produced only zombie stations that a user mistook for working feeders. Station creation is unified into the enrollment setup wizard (see the `station-enrollment` capability), which creates the real, device-backed station.

**Migration**: Users create stations exclusively through the enrollment setup wizard, which now lives at `/stations/new`. The backend `POST /station/` endpoint is retained for superuser tooling and the test suite but is no longer reachable from any user-facing surface; the device-less `/stations/new` create form is removed and the route is repurposed to host the wizard, and the legacy `/enroll` wizard route redirects to `/stations/new`.

## ADDED Requirements

### Requirement: Adding a station is a secondary action routed to the setup wizard

The authenticated station list (`/stations/mine`) SHALL present the station-creation entry point as a **quiet, secondary** action ("Add station") that routes to the enrollment setup wizard at `/stations/new` (see `station-enrollment`). It SHALL NOT be a primary-styled create button and SHALL NOT be a device-less create form. The list's empty state SHALL direct a user who owns no stations to the setup wizard to set up their first station. Adding a subsequent station SHALL remain possible from this list but SHALL NOT be given primary visual prominence.

#### Scenario: the station list offers a quiet Add-station action

- **WHEN** a logged-in owner who already owns at least one station views `/stations/mine`
- **THEN** the page shows a secondary "Add station" action that links to the enrollment setup wizard, and shows no device-less create form and no primary-styled "New station" button

#### Scenario: the empty station list points to the setup wizard

- **WHEN** a logged-in owner who owns zero stations views `/stations/mine`
- **THEN** the empty state directs them to the enrollment setup wizard to set up their first station

#### Scenario: `/stations/new` serves the setup wizard, not a device-less form

- **WHEN** a client requests `/stations/new`
- **THEN** it serves the enrollment setup wizard, no device-less create form is served there, and there is no user-facing path that persists a station with a null `spki_sha256`

#### Scenario: the legacy enroll route redirects to the setup wizard

- **WHEN** a client requests the legacy `/enroll` route
- **THEN** it redirects to `/stations/new`
