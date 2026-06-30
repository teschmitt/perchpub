## ADDED Requirements

### Requirement: Operator starts an enrollment session from the browser

A logged-in operator SHALL be able to start a station enrollment from the authenticated zone by submitting the new station's `latitude` and `longitude`, which the server-side form action sends to the backend `POST /enrollment/create` through the generated typed client. The action SHALL surface the returned `session_id`, the one-time cleartext `auth_token`, and `expires_at` to the operator. The enrollment wizard SHALL be reachable only inside the `(app)` zone, behind the P0 server-side auth guard. The device-side `POST /enrollment/confirm/{session_id}` step is performed by the Raspberry Pi and is out of browser scope.

#### Scenario: an operator starts an enrollment session
- **WHEN** a logged-in operator submits the enrollment form with a valid latitude and longitude
- **THEN** the form action calls `POST /enrollment/create` and the page receives a `session_id`, a cleartext one-time `auth_token`, and an `expires_at` timestamp

#### Scenario: the enrollment wizard requires authentication
- **WHEN** an unauthenticated client requests the enrollment wizard in the `(app)` zone
- **THEN** P0's `(app)` guard redirects the request to the login route before the wizard renders

### Requirement: One-time auth token is shown once with a countdown and copy action

The enrollment wizard SHALL display the one-time `auth_token` and its `session_id` exactly once, each with a copy-to-clipboard action, and SHALL show a live countdown to the `expires_at` deadline (300-second TTL). The token value SHALL NOT be placed in a URL, query string, or persisted client store, and SHALL NOT be re-displayed after navigating away. When the countdown reaches zero the wizard SHALL mark the token expired.

#### Scenario: the token is presented with a copy control and a countdown
- **WHEN** an enrollment session is created
- **THEN** the wizard shows the `auth_token` and `session_id` with copy-to-clipboard controls and a countdown that ticks down toward `expires_at`

#### Scenario: the token expires visibly
- **WHEN** the countdown reaches the `expires_at` deadline before the operator confirms
- **THEN** the wizard marks the token expired and stops offering it as usable

#### Scenario: the token is not leaked beyond the one-time display
- **WHEN** the operator navigates away from the wizard and returns
- **THEN** the previously shown `auth_token` is not re-displayed and never appears in a URL, query string, or persisted client store

### Requirement: Wizard confirms enrollment via the station list

Because there is no operator-facing enrollment poll or status endpoint, the wizard SHALL confirm a completed enrollment by re-fetching the operator's station list (`GET /station/` through the generated typed client) and reporting when a newly enrolled station appears — the backend creates the `Station` row only when the device completes `POST /enrollment/confirm/{session_id}`.

#### Scenario: a confirmed station appears in the list
- **WHEN** the device completes its enrollment confirmation and the operator triggers the wizard's "check" action
- **THEN** the wizard re-fetches `GET /station/`, finds the newly enrolled station, and reports the enrollment as confirmed with a link to manage the station

#### Scenario: no station yet appears before the device confirms
- **WHEN** the operator triggers the "check" action before the device has confirmed
- **THEN** the wizard reports that no new station has appeared yet and offers to check again, without calling any nonexistent poll endpoint
