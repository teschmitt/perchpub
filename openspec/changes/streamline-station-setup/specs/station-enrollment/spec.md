## MODIFIED Requirements

### Requirement: Operator starts an enrollment session from the browser

A logged-in operator SHALL be able to start a station enrollment — the **canonical station-setup flow** — from the authenticated zone by submitting the new station's `latitude`, `longitude`, and an `is_private` flag, which the server-side form action sends to the backend `POST /enrollment/create` through the generated typed client. The action SHALL surface the returned `session_id`, the one-time cleartext `auth_token`, and `expires_at` to the operator. The submitted `is_private` value SHALL be persisted on the enrollment session so it can be applied to the `Station` created at confirm time (see "Enrollment carries the operator's privacy choice onto the station"). The enrollment wizard SHALL be reachable only inside the `(app)` zone, behind the P0 server-side auth guard. The device-side `POST /enrollment/confirm/{session_id}` step is performed by the Raspberry Pi and is out of browser scope.

#### Scenario: an operator starts an enrollment session

- **WHEN** a logged-in operator submits the enrollment form with a valid latitude and longitude
- **THEN** the form action calls `POST /enrollment/create` and the page receives a `session_id`, a cleartext one-time `auth_token`, and an `expires_at` timestamp

#### Scenario: the operator chooses the station's privacy at setup

- **WHEN** a logged-in operator submits the enrollment form with the `is_private` flag set
- **THEN** the `POST /enrollment/create` body carries `is_private` and the value is persisted on the enrollment session for application at confirm time

#### Scenario: the enrollment wizard requires authentication

- **WHEN** an unauthenticated client requests the enrollment wizard in the `(app)` zone
- **THEN** P0's `(app)` guard redirects the request to the login route before the wizard renders

## ADDED Requirements

### Requirement: Enrollment carries the operator's privacy choice onto the station

`POST /api/v1/enrollment/create` SHALL accept an optional `is_private` flag (default `false`) and persist it on the enrollment session (the `station_enrollment` record). When the device completes `POST /api/v1/enrollment/confirm/{session_id}` and a **new** `Station` is created, that station's `is_private` SHALL be set from the session's stored value. Re-enrollment of an already-enrolled device (matched by `SHA-256(SPKI)` against an existing `Station.spki_sha256`) SHALL NOT change the existing station's `is_private` — privacy is a station-management operation on an existing station, not a side effect of refreshing a certificate.

#### Scenario: a private-at-setup enrollment yields a private station

- **WHEN** an operator creates an enrollment session with `is_private = true` and the device confirms, creating a new station
- **THEN** the created `Station.is_private` is `true`

#### Scenario: privacy defaults to public when omitted

- **WHEN** an operator creates an enrollment session without an `is_private` flag and the device confirms, creating a new station
- **THEN** the created `Station.is_private` is `false`

#### Scenario: re-enrollment does not alter existing privacy

- **WHEN** a device that is already enrolled (same SPKI) re-enrolls through a session whose `is_private` differs from the existing station's current value
- **THEN** the existing station's `is_private` is left unchanged
