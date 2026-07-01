# observation-browsing Specification

## Purpose
TBD - created by archiving change add-public-observation-browsing. Update Purpose after archive.
## Requirements
### Requirement: Recent observations on the landing page

The public landing page SHALL be server-rendered and SHALL present a bounded set of the most recent observations, retrieved from `GET /observation/` through the generated typed client with a small `limit`. Each entry SHALL render its media as a thumbnail served from `/media/{object_name}` and SHALL link to that observation's detail page. The landing page SHALL require no authentication.

#### Scenario: the landing page renders recent observations server-side
- **WHEN** an anonymous client requests the landing page (`/`)
- **THEN** the server-rendered HTML already contains a bounded list of recent observations, each with a `/media/{object_name}` thumbnail and a link to `/observations/{id}`

#### Scenario: an empty database renders an empty landing state
- **WHEN** an anonymous client requests the landing page and `GET /observation/` returns `count: 0`
- **THEN** the page renders an empty/placeholder state without error

### Requirement: Paginated observation feed

The public observation feed (`/observations/`) SHALL be server-rendered from `GET /observation/` using `skip`/`limit` derived from the request's page query parameter, and SHALL render each observation with its media thumbnail (via `/media/{object_name}`), classified species, capturing station, and confidence score. It SHALL provide pagination controls driven by the response `count`, with the previous control disabled on the first page and the next control disabled once `skip + limit >= count`. The feed SHALL require no authentication.

Assumption (inherited gap, not addressed here): `GET /observation/` currently applies **no** per-viewer visibility filtering, so observations captured at private stations are returned to all callers, including anonymous ones. The "public" framing of this feed therefore reflects current backend behavior and is NOT an enforced visibility guarantee; closing that gap is a deferred backend change out of scope for this phase.

#### Scenario: the feed lists observations with media thumbnails
- **WHEN** an anonymous client requests `/observations/`
- **THEN** the server-rendered page lists observations, each showing a `/media/{object_name}` thumbnail, its species (or an "unclassified" indicator when the species is null), its station, and its confidence score

#### Scenario: paging forward advances the result window
- **WHEN** the next-page control is followed from `/observations/`
- **THEN** the next request increases `skip` by `limit` and the server renders the subsequent slice of observations

#### Scenario: an out-of-range page renders empty, not an error
- **WHEN** a page beyond the last is requested (computed `skip` is greater than or equal to `count`)
- **THEN** the feed renders an empty list with the next control disabled, and does not error

### Requirement: Shareable observation detail page

The observation detail page (`/observations/{id}`) SHALL be server-rendered from `GET /observation/{id}` and SHALL display the observation's media (an image, or a `<video>` for a video key) served from `/media/{object_name}`, together with its classified species, capturing station, observed-at time, and confidence score. The page SHALL emit Open Graph and share-preview `<meta>` tags (title, description, image, url) in the server-rendered head so the URL unfurls into a preview card, with the image being the absolute `/media/{object_name}` URL built from `PUBLIC_SITE_URL`. A backend `404` SHALL render as a not-found page. The detail page SHALL require no authentication.

#### Scenario: detail page renders species, station, and confidence
- **WHEN** an anonymous client requests `/observations/{id}` for an existing observation
- **THEN** the server-rendered page shows the media via `/media/{object_name}`, the classified species (or "unclassified" when null), the capturing station (linking to its station detail page), the observed-at time, and the confidence score

#### Scenario: share-preview meta tags are present in the SSR HTML
- **WHEN** the server-rendered HTML for an observation detail page is inspected
- **THEN** it contains Open Graph tags including `og:title`, `og:description`, `og:url`, and an `og:image` pointing at the absolute `/media/{object_name}` URL for that observation's media

#### Scenario: a missing observation renders not-found
- **WHEN** `/observations/{id}` is requested for an id the backend returns `404` for
- **THEN** the page renders a not-found (404) response rather than a server error

### Requirement: Superuser manual reclassification of an observation

The observation detail page SHALL present a manual-reclassification control **only** to an authenticated superuser. The control SHALL let the superuser choose a species (from the species catalogue served by `GET /species/`, wrapper `SpeciesMultiPublic`) and SHALL submit `PUT /observation/{id}` via a server-side SvelteKit form action through the generated typed client. Because `ObservationUpdate` inherits `confidence_score` and `classification_result` from `ObservationBase` as **required** fields, the submitted body SHALL be a complete `ObservationUpdate`: `species_id` set to the chosen species, `manually_classified = true`, and `confidence_score` + `classification_result` carried over **unchanged** from the loaded observation (`ObservationPublic` exposes both). A partial body of only `species_id` + `manually_classified` is rejected by the backend with `422` and SHALL NOT be sent. The control SHALL NOT be rendered for anonymous or non-superuser visitors, and the backend's superuser guard on `PUT /observation/{id}` SHALL remain in force as defense-in-depth.

#### Scenario: the control is hidden from non-superusers
- **WHEN** an anonymous visitor or an authenticated non-superuser loads an observation detail page
- **THEN** no reclassification control is rendered

#### Scenario: a superuser corrects the species
- **WHEN** a superuser selects a species in the reclassification control and submits it
- **THEN** `PUT /observation/{id}` is called with a complete `ObservationUpdate` body — `species_id` = the chosen species, `manually_classified = true`, and `confidence_score` + `classification_result` carried over unchanged from the loaded observation — and on reload the observation shows the corrected species and a "manually classified" indicator

#### Scenario: a non-superuser request to the endpoint is refused
- **WHEN** a non-superuser somehow submits the reclassify action
- **THEN** the backend `403` `{detail}` is surfaced as a form error and the observation is unchanged

### Requirement: Classification status badge on observations

An observation SHALL surface the status of its classification work as an inline badge whose value is one of `ClassifyTaskStatus` — Prepared, Queued, Processing, Success, or Failed — derived from `GET /classify-task/?observation={id}` (the observation's most-recent classify task). When the observation has no classify task, no badge SHALL be shown. The `Failed` state SHALL be visually distinguishable from the others.

#### Scenario: a successful classification shows a Success badge
- **WHEN** an observation's most-recent classify task has status `Success`
- **THEN** the detail page renders a badge labelled "Success"

#### Scenario: a failed classification is visually distinct
- **WHEN** an observation's most-recent classify task has status `Failed`
- **THEN** the detail page renders a "Failed" badge styled distinctly from the non-failed states

#### Scenario: an observation with no classify task shows no badge
- **WHEN** `GET /classify-task/?observation={id}` returns an empty list for the observation
- **THEN** no status badge is rendered

### Requirement: Superuser classify-task list

The frontend SHALL provide a superuser-only, read-only classify-task list backed by `GET /classify-task/`, filterable by the `status` and `observation` query parameters the endpoint accepts, with each row linking to its observation. Because the `GET /classify-task/` and `GET /classify-task/{id}` reads carry no backend authorization dependency, this surface SHALL be gated only by the client-side superuser guard and SHALL be read-only (it SHALL offer no mutation of classify tasks).

#### Scenario: the list is gated behind the superuser guard
- **WHEN** an authenticated non-superuser requests the admin classify-task list route
- **THEN** the server guard denies access (redirect or 404) and the list is not rendered

#### Scenario: filtering by status
- **WHEN** a superuser opens the classify-task list with a `status` filter (e.g. `Failed`) set in the URL search params
- **THEN** `GET /classify-task/` is called with that `status` query param and only matching tasks are listed

#### Scenario: filtering by observation
- **WHEN** a superuser opens the classify-task list with an `observation` filter set in the URL search params
- **THEN** `GET /classify-task/` is called with that `observation` query param and only that observation's tasks are listed

