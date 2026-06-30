## ADDED Requirements

### Requirement: Classify-task responses expose created and updated timestamps

The classify-task response schema (`ClassifyTaskPublic`) SHALL expose the `created_at` and `updated_at` timestamps that are already persisted on the `classify_task` table, so that they appear in the generated OpenAPI schema and the typed client. This enables a client to display a classify task's creation/update time and to confirm "most-recent task" ordering. No database migration is required, because the columns already exist on the table model; this is an additive change to the response schema only.

#### Scenario: a classify task is serialized with its timestamps
- **WHEN** a client requests `GET /classify-task/{id}` for an existing classify task
- **THEN** the response includes the task's `created_at` and `updated_at` timestamps

#### Scenario: the list response carries timestamps for each task
- **WHEN** a client requests `GET /classify-task/`
- **THEN** each task in the `data` array includes its `created_at` and `updated_at` timestamps

#### Scenario: the timestamps appear in the generated schema
- **WHEN** the backend OpenAPI schema is generated
- **THEN** `ClassifyTaskPublic` declares `created_at` and `updated_at`, so the generated typed client includes them and code referencing them type-checks
