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

### Requirement: One-time auth token is shown once with a countdown and copy action

The enrollment wizard SHALL present the one-time enrollment credential exactly once, **primarily as a scannable QR** (see "Enrollment QR encodes the perchstation pairing payload") and **additionally as copyable `auth_token` and `session_id` text** with copy-to-clipboard actions as a fallback, and SHALL show a live countdown to the `expires_at` deadline (a **configurable TTL, default 60 seconds**). Neither the `auth_token` nor the rendered QR SHALL be placed in a URL, query string, or persisted client store; the QR SHALL be generated **in-memory** (never fetched via a token-bearing URL) and served `no-store`; and the credential SHALL NOT be re-displayed after navigating away. When the countdown reaches zero the wizard SHALL mark the credential expired.

#### Scenario: the credential is presented as a QR with a text fallback and a countdown
- **WHEN** an enrollment session is created
- **THEN** the wizard shows a scannable QR for the session and, as a fallback, the `auth_token` and `session_id` with copy-to-clipboard controls, plus a countdown that ticks down toward `expires_at`

#### Scenario: the credential expires visibly
- **WHEN** the countdown reaches the `expires_at` deadline before the device confirms
- **THEN** the wizard marks the credential expired and stops offering the QR and token as usable

#### Scenario: the credential is not leaked beyond the one-time display
- **WHEN** the operator navigates away from the wizard and returns
- **THEN** the previously shown `auth_token` and QR are not re-displayed, never appear in a URL, query string, or persisted client store, and the QR was built in-memory rather than fetched from a token-bearing URL

### Requirement: Wizard confirms enrollment via the station list

Because there is no operator-facing enrollment poll or status endpoint, the wizard SHALL confirm a completed enrollment by re-fetching the operator's station list (`GET /station/` through the generated typed client) and reporting when a newly enrolled station appears — the backend creates the `Station` row only when the device completes `POST /enrollment/confirm/{session_id}`.

#### Scenario: a confirmed station appears in the list
- **WHEN** the device completes its enrollment confirmation and the operator triggers the wizard's "check" action
- **THEN** the wizard re-fetches `GET /station/`, finds the newly enrolled station, and reports the enrollment as confirmed with a link to manage the station

#### Scenario: no station yet appears before the device confirms
- **WHEN** the operator triggers the "check" action before the device has confirmed
- **THEN** the wizard reports that no new station has appeared yet and offers to check again, without calling any nonexistent poll endpoint

### Requirement: Enrollment create returns the device-CA pin

`POST /api/v1/enrollment/create` SHALL include in its response a `ca_pin`: the lowercase-hex `SHA-256` of the `SubjectPublicKeyInfo` (DER) of the device-CA **root** certificate (`settings.STEP_CA_ROOT_CERT_PATH`). The value SHALL equal `SHA-256(SPKI)` of the trust root that the certificate issuing station leaves chains to, so that a station can verify the `ca_chain_pem` returned by `POST /enrollment/confirm/{session_id}` against it out-of-band. Computing `ca_pin` SHALL NOT require signing a CSR or a step-ca round trip, and SHALL reuse the same SPKI-SHA256 construction used for `Station.spki_sha256`.

#### Scenario: create returns the root SPKI pin
- **WHEN** a logged-in operator submits the enrollment form with a valid latitude and longitude
- **THEN** the response includes `ca_pin` equal to the lowercase-hex `SHA-256` of the `SubjectPublicKeyInfo` (DER) of the certificate at `settings.STEP_CA_ROOT_CERT_PATH`

#### Scenario: the pin matches the root the confirmed leaf chains to
- **WHEN** the same enrollment flow later completes `POST /enrollment/confirm/{session_id}` and receives a signed leaf plus `ca_chain_pem`
- **THEN** the leaf chains `leaf → intermediate → root` through the returned chain, and the `SHA-256(SPKI(DER))` of that root equals the `ca_pin` returned at create time

### Requirement: Enrollment advertises the public station edge URL

`POST /api/v1/enrollment/create` SHALL include in its response — and the enrollment QR SHALL carry — a `perchpub_url`: the public station-facing enrollment origin (the `:443` edge) a station talks to and derives its `:8443` upload endpoint from. The value SHALL be sourced from a per-deployment setting (`settings.STATION_EDGE_URL`) and emitted verbatim as an absolute `https://` URL in **origin form** — scheme + host [+ optional port], with no path and no trailing slash — so a station can enroll with zero pre-configuration. It SHALL be the canonical public origin whose edge certificate SAN matches, never an internal hostname, container name, or IP. Adding `perchpub_url` SHALL be additive: `session_id`, `auth_token`, and `ca_pin` retain their meaning and a station that does not read `perchpub_url` is unaffected. `settings.STATION_EDGE_URL` SHALL be required in staging/production (an unset value SHALL fail fast at settings load) and SHALL be normalized to strip any trailing slash.

#### Scenario: create returns the public station edge origin
- **WHEN** a logged-in operator submits the enrollment form with a valid latitude and longitude
- **THEN** the response includes `perchpub_url` equal to `settings.STATION_EDGE_URL`, an absolute `https://` URL with a scheme and host and no trailing slash

#### Scenario: the QR carries the same enrollment origin
- **WHEN** an enrollment session is created and its QR is rendered
- **THEN** the decoded QR's `perchpub_url` is byte-for-byte equal to the `perchpub_url` returned by `POST /enrollment/create`

#### Scenario: an unset station edge URL fails fast in production
- **WHEN** the backend loads settings in `production` with `STATION_EDGE_URL` unset
- **THEN** settings validation raises rather than serving an empty `perchpub_url`

### Requirement: Enrollment confirm returns the full device-CA chain

`POST /api/v1/enrollment/confirm/{session_id}` SHALL return, in `ca_chain_pem`, the full device-CA chain — the issuing **intermediate** followed by the device-CA **root** — so that a station can build the path from its issued leaf to the root and verify the root against the `ca_pin` carried in the QR. step-ca returns the intermediate; the backend SHALL append the root from `settings.STEP_CA_ROOT_CERT_PATH`. This change SHALL NOT alter CSR signing or the mTLS entrypoint.

#### Scenario: confirm returns intermediate and root
- **WHEN** a station completes `POST /enrollment/confirm/{session_id}` with a valid auth token and CSR
- **THEN** the response `ca_chain_pem` contains the issuing intermediate and the device-CA root, and the issued leaf chains `leaf → intermediate → root`

### Requirement: Enrollment QR encodes the perchstation pairing payload

The enrollment wizard SHALL encode the enrollment credential as a **single, non-animated, byte-mode QR** symbol with a quiet zone, whose data segment is the raw UTF-8 bytes of one compact JSON object with exactly the fields `session_id` (canonical UUID), `auth_token` (the one-time cleartext token), `ca_pin` (as defined by "Enrollment create returns the device-CA pin"), and `perchpub_url` (as defined by "Enrollment advertises the public station edge URL"), matching the perchstation enrollment-QR contract. The QR SHALL NOT carry the device-CA chain, a keypair, or a CSR. The wizard SHALL be able to decode its own emitted symbol back to the four fields.

#### Scenario: the QR encodes the four contract fields
- **WHEN** an enrollment session is created and its QR is rendered
- **THEN** decoding the QR yields a single JSON object containing exactly `session_id`, `auth_token`, `ca_pin`, and `perchpub_url`, and no device-CA chain, keypair, or CSR

#### Scenario: the emitted symbol round-trips
- **WHEN** the wizard encodes the payload and the symbol is decoded by a standard QR reader
- **THEN** the decoded `session_id`, `auth_token`, `ca_pin`, and `perchpub_url` are byte-for-byte equal to the values the wizard encoded

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

