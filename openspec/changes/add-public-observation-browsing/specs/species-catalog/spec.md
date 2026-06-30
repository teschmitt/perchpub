## ADDED Requirements

### Requirement: Public species catalog list

The species catalog page (`/species/`) SHALL be server-rendered from `GET /species/` through the generated typed client, reading the response as the `SpeciesMultiPublic` wrapper (`{data, count}`) and rendering each species' scientific name with a link to its detail page. When `count` exceeds the page size, the list SHALL provide pagination over `skip`/`limit`. The catalog SHALL require no authentication.

#### Scenario: the catalog lists species from the SpeciesMultiPublic wrapper
- **WHEN** an anonymous client requests `/species/`
- **THEN** the server-rendered page lists each species' scientific name from the response `data` array (the `SpeciesMultiPublic` wrapper), each linking to `/species/{id}`

#### Scenario: an empty catalog renders an empty state
- **WHEN** an anonymous client requests `/species/` and `GET /species/` returns `count: 0`
- **THEN** the page renders an empty/placeholder state without error

### Requirement: Species detail page

The species detail page (`/species/{id}`) SHALL be server-rendered from `GET /species/{id}` and SHALL display the species' scientific name. A backend `404` SHALL render as a not-found page. The page SHALL require no authentication.

#### Scenario: detail page renders the species
- **WHEN** an anonymous client requests `/species/{id}` for an existing species
- **THEN** the server-rendered page shows that species' scientific name

#### Scenario: a missing species renders not-found
- **WHEN** `/species/{id}` is requested for an id the backend returns `404` for
- **THEN** the page renders a not-found (404) response rather than a server error
