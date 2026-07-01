## ADDED Requirements

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
