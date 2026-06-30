## ADDED Requirements

### Requirement: Collection list endpoints return a deterministic, total order

Each collection list endpoint SHALL apply an explicit `ORDER BY` that yields a total, deterministic order, so that "most recent" is meaningful and repeated identical `skip`/`limit` requests over an unchanged dataset return rows in the identical order (rather than arbitrary database heap order). Specifically: `GET /observation/` SHALL order by observed-at time descending (most recent first); `GET /classify-task/` SHALL order by created-at time descending (most recent first); `GET /species/` SHALL order by scientific name ascending; and `GET /station/` SHALL order by created-at time descending. Every ordering SHALL include the row `id` as a final tiebreaker so the order is total even when the primary sort key ties. The applied order SHALL NOT change which rows are returned (it composes with, and does not replace, each endpoint's existing filtering and visibility rules) and SHALL precede `skip`/`limit`.

#### Scenario: observations are returned most-recent-first
- **WHEN** a client requests `GET /observation/` and multiple observations exist with distinct `observed_at` values
- **THEN** the observations are returned ordered by `observed_at` descending (most recently observed first), with `id` as a stable tiebreaker

#### Scenario: repeated identical requests return a reproducible order
- **WHEN** a client requests `GET /observation/` twice with the same `skip` and `limit` and the underlying data has not changed
- **THEN** both responses list the observations in the identical order

#### Scenario: the species catalogue is ordered alphabetically
- **WHEN** a client requests `GET /species/`
- **THEN** the species are returned ordered by `scientific_name` ascending, with `id` as a tiebreaker

#### Scenario: stations are returned newest-first
- **WHEN** a client requests `GET /station/`
- **THEN** the visible stations are returned ordered by `created_at` descending, with `id` as a tiebreaker, and the optional-authentication visibility filter still determines which stations are included

#### Scenario: an observation's classify tasks are returned most-recent-first
- **WHEN** a client requests `GET /classify-task/?observation={id}` for an observation that has multiple classify tasks
- **THEN** that observation's classify tasks are returned ordered by `created_at` descending, so the most-recent task is first in the list
