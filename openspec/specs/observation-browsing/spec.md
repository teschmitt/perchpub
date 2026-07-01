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

