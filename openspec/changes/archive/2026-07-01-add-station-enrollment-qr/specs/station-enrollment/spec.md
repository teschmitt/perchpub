## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Enrollment create returns the device-CA pin

`POST /api/v1/enrollment/create` SHALL include in its response a `ca_pin`: the lowercase-hex `SHA-256` of the `SubjectPublicKeyInfo` (DER) of the device-CA **root** certificate (`settings.STEP_CA_ROOT_CERT_PATH`). The value SHALL equal `SHA-256(SPKI)` of the trust root that the certificate issuing station leaves chains to, so that a station can verify the `ca_chain_pem` returned by `POST /enrollment/confirm/{session_id}` against it out-of-band. Computing `ca_pin` SHALL NOT require signing a CSR or a step-ca round trip, and SHALL reuse the same SPKI-SHA256 construction used for `Station.spki_sha256`.

#### Scenario: create returns the root SPKI pin
- **WHEN** a logged-in operator submits the enrollment form with a valid latitude and longitude
- **THEN** the response includes `ca_pin` equal to the lowercase-hex `SHA-256` of the `SubjectPublicKeyInfo` (DER) of the certificate at `settings.STEP_CA_ROOT_CERT_PATH`

#### Scenario: the pin matches the root the confirmed leaf chains to
- **WHEN** the same enrollment flow later completes `POST /enrollment/confirm/{session_id}` and receives a signed leaf plus `ca_chain_pem`
- **THEN** the leaf chains `leaf → intermediate → root` through the returned chain, and the `SHA-256(SPKI(DER))` of that root equals the `ca_pin` returned at create time

### Requirement: Enrollment confirm returns the full device-CA chain

`POST /api/v1/enrollment/confirm/{session_id}` SHALL return, in `ca_chain_pem`, the full device-CA chain — the issuing **intermediate** followed by the device-CA **root** — so that a station can build the path from its issued leaf to the root and verify the root against the `ca_pin` carried in the QR. step-ca returns the intermediate; the backend SHALL append the root from `settings.STEP_CA_ROOT_CERT_PATH`. This change SHALL NOT alter CSR signing or the mTLS entrypoint.

#### Scenario: confirm returns intermediate and root
- **WHEN** a station completes `POST /enrollment/confirm/{session_id}` with a valid auth token and CSR
- **THEN** the response `ca_chain_pem` contains the issuing intermediate and the device-CA root, and the issued leaf chains `leaf → intermediate → root`

### Requirement: Enrollment QR encodes the perchstation pairing payload

The enrollment wizard SHALL encode the enrollment credential as a **single, non-animated, byte-mode QR** symbol with a quiet zone, whose data segment is the raw UTF-8 bytes of one compact JSON object with exactly the fields `session_id` (canonical UUID), `auth_token` (the one-time cleartext token), and `ca_pin` (as defined by "Enrollment create returns the device-CA pin"), matching the perchstation enrollment-QR contract. The QR SHALL NOT carry the device-CA chain, a keypair, or a CSR. The wizard SHALL be able to decode its own emitted symbol back to the three fields.

#### Scenario: the QR encodes the three contract fields
- **WHEN** an enrollment session is created and its QR is rendered
- **THEN** decoding the QR yields a single JSON object containing exactly `session_id`, `auth_token`, and `ca_pin`, and no device-CA chain, keypair, or CSR

#### Scenario: the emitted symbol round-trips
- **WHEN** the wizard encodes the payload and the symbol is decoded by a standard QR reader
- **THEN** the decoded `session_id`, `auth_token`, and `ca_pin` are byte-for-byte equal to the values the wizard encoded
