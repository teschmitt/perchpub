# api-authentication Specification

## Purpose
TBD - created by archiving change add-frontend-api-prerequisites. Update Purpose after archive.
## Requirements
### Requirement: Bearer-token authentication failures return 401

The backend SHALL distinguish authentication failures from authorization failures on JWT-protected endpoints. When a request to a protected endpoint cannot be authenticated — the bearer token is expired, malformed, or otherwise invalid; or the token resolves to a user that no longer exists; or the token resolves to an inactive user; or no bearer token is presented — the backend SHALL respond `401 Unauthorized`, carrying the generic detail `"Could not validate credentials"` for the token-validation cases (without revealing which of the failure cases occurred). When a request is successfully authenticated but the authenticated user is not permitted to perform the operation (insufficient role such as a non-superuser on a superuser route, or non-ownership of a resource), the backend SHALL continue to respond `403 Forbidden`. This contract lets a backend-for-frontend treat any `401` as "the session is no longer usable" (clear the cookie) while leaving `403` to mean "authenticated, but not allowed".

#### Scenario: an expired or invalid token is rejected with 401
- **WHEN** a request presents an expired, malformed, or otherwise invalid JWT as a bearer token to a JWT-protected endpoint
- **THEN** the backend responds `401` with the detail `"Could not validate credentials"`

#### Scenario: a token for a deleted user is rejected with 401
- **WHEN** a request presents an otherwise-valid JWT whose subject no longer corresponds to an existing user
- **THEN** the backend responds `401` (not `404`), without disclosing that the user is missing

#### Scenario: a token for an inactive user is rejected with 401
- **WHEN** a request presents an otherwise-valid JWT whose subject is an inactive (deactivated) user
- **THEN** the backend responds `401` (not `400`)

#### Scenario: a missing bearer token is rejected with 401
- **WHEN** a request to a JWT-protected endpoint presents no bearer token
- **THEN** the backend responds `401`

#### Scenario: an authorization failure remains 403 (regression)
- **WHEN** a successfully-authenticated non-superuser requests a superuser-only endpoint
- **THEN** the backend responds `403` (authorization failure), not `401` — the authentication contract does not change authorization responses

