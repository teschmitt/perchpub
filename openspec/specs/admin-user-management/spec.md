# admin-user-management Specification

## Purpose
TBD - created by archiving change add-superuser-frontend-tools. Update Purpose after archive.
## Requirements
### Requirement: Superuser-only access to user administration

The user-administration area SHALL be reachable only by an authenticated superuser. The server-side superuser guard (the P0 `(app)/admin/` guard asserting `locals.user.is_superuser`) SHALL run during `load` and SHALL deny non-superusers before any administration data is fetched, and the backend's `get_current_active_superuser` dependency on `/users/` and `/users/{user_id}` SHALL remain in force as defense-in-depth.

#### Scenario: a non-superuser cannot reach user administration
- **WHEN** an authenticated non-superuser requests the admin users route
- **THEN** the server guard denies access (redirect or 404) before any `GET /users/` call is made, and no user list is rendered

#### Scenario: a superuser reaches user administration
- **WHEN** an authenticated superuser requests the admin users route
- **THEN** the page renders the user list returned by `GET /users/` (the `UsersPublic` `{data, count}` shape)

### Requirement: List, create, edit, and delete users

The frontend SHALL let a superuser list users (`GET /users/`), create a user (`POST /users/` with `UserCreate`), edit a user (`PATCH /users/{user_id}` with `UserUpdate`), and delete a user (`DELETE /users/{user_id}`). All four operations SHALL go through the generated typed client (no hand-written URLs), and all mutations SHALL be SvelteKit server-side form actions that forward the session bearer.

#### Scenario: superuser creates a user
- **WHEN** a superuser submits the create-user form with a unique email and a password
- **THEN** `POST /users/` is called through the typed client, the new user appears in the list on reload

#### Scenario: creating a duplicate email surfaces the backend error
- **WHEN** a superuser submits the create-user form with an email that already exists
- **THEN** the backend `400` `{detail}` ("The user with this email already exists in the system.") is shown as a form error and no new user is created

#### Scenario: superuser deletes a user
- **WHEN** a superuser triggers delete on another user's row
- **THEN** `DELETE /users/{user_id}` is called and the user is removed from the list

#### Scenario: deleting oneself surfaces the backend refusal
- **WHEN** a superuser triggers delete on their own row
- **THEN** the backend `403` `{detail}` is shown as a form error and the user is not deleted (the page does not crash)

### Requirement: Toggle is_active and is_superuser on edit

The user edit form SHALL expose the `is_active` and `is_superuser` fields (both present on `UserUpdate`) as toggles and SHALL persist them via `PATCH /users/{user_id}`. The saved values SHALL be reflected when the user list or edit form is reloaded.

#### Scenario: superuser deactivates a user
- **WHEN** a superuser sets `is_active` to false on a user's edit form and saves
- **THEN** `PATCH /users/{user_id}` is called with `is_active = false` and the user shows as inactive on reload

#### Scenario: superuser grants superuser rights
- **WHEN** a superuser sets `is_superuser` to true on a user's edit form and saves
- **THEN** `PATCH /users/{user_id}` is called with `is_superuser = true` and the user shows as a superuser on reload

