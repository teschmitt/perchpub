# station-enrollment Specification

## Purpose
TBD - created by archiving change add-ed25519-station-key-support. Update Purpose after archive.
## Requirements
### Requirement: Supported device key types

The enrollment endpoint SHALL accept a station CSR whose public key is **either** Ed25519 **or** EC P-256, sign it via the step-ca `backend-device-enrollment` JWK provisioner with no per-key-type configuration, and pin `SHA-256` of the issued leaf's `SubjectPublicKeyInfo` (DER) as `Station.spki_sha256`. The issued leaf SHALL preserve the CSR's public-key type. Ed25519 SHALL be the recommended default key type for new stations, and EC P-256 SHALL remain fully supported. No CSR SHALL be accepted or rejected on the basis of its key algorithm — the server enforces no single key type.

#### Scenario: Ed25519 CSR yields an Ed25519 leaf pinned by SPKI
- **WHEN** a station submits a CSR carrying an Ed25519 public key to `POST /api/v1/enrollment/confirm/{session_id}` with a valid auth token
- **THEN** enrollment succeeds, the issued leaf carries an Ed25519 public key, and the persisted `Station.spki_sha256` equals the SHA-256 of that leaf's `SubjectPublicKeyInfo` (DER)

#### Scenario: EC P-256 enrollment is unchanged (regression)
- **WHEN** a station submits a CSR carrying an EC P-256 public key with a valid auth token
- **THEN** enrollment succeeds and the station is pinned by the leaf's SPKI exactly as before this change

#### Scenario: the deployed step-ca issues an Ed25519 leaf end-to-end
- **WHEN** the full compose stack runs the enrollment flow with an Ed25519 CSR against the real step-ca JWK provisioner (no template or provisioner change)
- **THEN** step-ca returns a valid Ed25519 leaf that chains to the device CA and whose SPKI matches the submitted CSR

### Requirement: mTLS station identity is key-type-agnostic

A station presenting an Ed25519 client leaf issued by the device CA SHALL authenticate on the mTLS upload entrypoint identically to an EC P-256 station. Identity resolution SHALL match the request on `SHA-256(SubjectPublicKeyInfo)` of the presented leaf against `Station.spki_sha256`, regardless of the leaf's key algorithm.

#### Scenario: Ed25519 station authenticates an mTLS upload
- **WHEN** a station presents its step-ca-issued Ed25519 leaf to the mTLS upload entrypoint serving `/api/v1/upload/`
- **THEN** the request authenticates, the calling station is resolved by matching `SHA-256(SPKI)` to `Station.spki_sha256`, and the upload returns `200`

### Requirement: Documented key generation for supported key types

The station-enrollment documentation SHALL present Ed25519 as the recommended default device key type and SHALL also document EC P-256 as a fully supported alternative, covering OpenSSL and Python `cryptography` for both, and SHALL note that Ed25519 CSRs are signed with no hash algorithm (`.sign(key, None)`). The documentation SHALL NOT present EC P-256 as the default or as the only supported key type.

#### Scenario: operator generates an Ed25519 device key from the runbook
- **WHEN** an operator follows the documented Ed25519 keygen (`openssl genpkey -algorithm ed25519 -out device.key`, or `ed25519.Ed25519PrivateKey.generate()` with CSR `.sign(key, None)`) and enrolls the resulting CSR
- **THEN** the CSR is accepted by the enrollment endpoint without trial and error

#### Scenario: docs recommend Ed25519 and still document EC P-256
- **WHEN** the station-enrollment documentation is reviewed
- **THEN** Ed25519 is presented as the recommended default key type and EC P-256 is documented as a supported alternative

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

