## ADDED Requirements

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
