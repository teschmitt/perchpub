# station-management Specification

## Purpose
TBD - created by archiving change add-public-observation-browsing. Update Purpose after archive.
## Requirements
### Requirement: Public station list with optional-authentication visibility

The public station list page (`/stations/`) SHALL be server-rendered from `GET /station/` through the generated typed client, using optional-authentication: the server SHALL forward the session bearer only when a `pp_session` cookie is present. Consequently an anonymous visitor SHALL see only public stations, while a logged-in owner SHALL additionally see their own private stations (as the backend's optional-user visibility filter returns). The page SHALL render each station for VIEW only — it SHALL NOT present create, edit, or delete controls in this phase.

#### Scenario: an anonymous visitor sees only public stations
- **WHEN** an anonymous client requests `/stations/`
- **THEN** the server sends no bearer to `GET /station/` and the page lists only public (non-private) stations

#### Scenario: a logged-in owner additionally sees their private stations
- **WHEN** a logged-in owner requests `/stations/` while holding a `pp_session` cookie
- **THEN** the server forwards the bearer to `GET /station/` and the page lists public stations plus that owner's own private stations

#### Scenario: the list is view-only
- **WHEN** any visitor views `/stations/`
- **THEN** the page presents stations for viewing only and shows no create/edit/delete management controls

### Requirement: Public station detail with optional-authentication visibility

The station detail page (`/stations/{id}`) SHALL be server-rendered from `GET /station/{id}` using optional-authentication (forwarding the bearer only when a `pp_session` cookie is present), and SHALL display the station's details (location, owner, visibility) for VIEW only. A backend `404` — whether the station does not exist or is a private station the caller may not see (existence-leak avoidance) — SHALL render as a not-found page.

#### Scenario: a visible station renders its detail
- **WHEN** a client requests `/stations/{id}` for a station it is permitted to see (a public station, or the caller's own private station)
- **THEN** the server-rendered page shows the station's location, owner, and visibility, with no management controls

#### Scenario: a hidden or missing station renders not-found
- **WHEN** a client requests `/stations/{id}` for a station the backend returns `404` for (nonexistent, or a private station the caller may not see)
- **THEN** the page renders a not-found (404) response rather than disclosing the station's existence

### Requirement: Owner creates a station

A logged-in user SHALL be able to create a station from the authenticated zone by submitting `latitude`, `longitude`, and an `is_private` flag, persisted via the backend `POST /station/` through the generated typed client in a server-side form action. The new station's owner SHALL be the creating user (set server-side from the bearer; the browser never supplies `owner_id`). A station-coordinate map picker is out of scope; coordinates are entered as numeric `latitude`/`longitude` values bounded by `-90..90` and `-180..180`. The create page SHALL be reachable only inside the `(app)` zone, behind the P0 server-side auth guard.

#### Scenario: a logged-in user creates a station
- **WHEN** a logged-in user submits the create-station form with a valid latitude, longitude, and `is_private` value
- **THEN** the server-side form action calls `POST /station/`, the created station is owned by that user, and the user is returned to their station list where the new station appears

#### Scenario: invalid coordinates are rejected with a field error
- **WHEN** a user submits the create-station form with a latitude or longitude outside the allowed range
- **THEN** the form action returns a typed validation error and the form re-renders with the submitted values rather than navigating away

#### Scenario: the create page requires authentication
- **WHEN** an unauthenticated client requests the create-station page in the `(app)` zone
- **THEN** P0's `(app)` guard redirects the request to the login route before the page renders

### Requirement: Owner edits their own station

The owner of a station (and a superuser) SHALL be able to edit that station's `latitude`, `longitude`, and `is_private` flag from the authenticated zone via the backend `PUT /station/{id}` through the generated typed client in a server-side form action. Because `StationUpdate` extends `StationBase` with no field overrides — its "all fields optional" docstring is inaccurate; `latitude` and `longitude` are required — the edit form SHALL be pre-filled from the loaded station (`StationPublic` exposes `latitude`, `longitude`, `is_private`) and SHALL resubmit the **complete** `{latitude, longitude, is_private}` body on save, not a partial patch. A user who is neither the owner nor a superuser SHALL NOT be able to edit the station: the UI SHALL reflect the backend's `403` (a public station they do not own) and `404` (a private station they do not own, or an unknown id) without exposing private details. The `is_private` toggle SHALL be editable through this form.

#### Scenario: an owner toggles their station's privacy
- **WHEN** a station's owner submits the edit form with a changed `is_private` value
- **THEN** the form action calls `PUT /station/{id}`, the station's `is_private` flag is updated, and the change is reflected in the owner's station list

#### Scenario: a non-owner cannot edit a foreign public station
- **WHEN** a logged-in user submits the edit form for a public station they do not own
- **THEN** the backend responds `403` and the UI shows an access-denied state instead of saving the change

#### Scenario: a non-owner cannot discover a foreign private station
- **WHEN** a logged-in user requests the edit page for a private station they do not own
- **THEN** the backend responds `404` and the UI shows a not-found state, leaking no detail about the private station

