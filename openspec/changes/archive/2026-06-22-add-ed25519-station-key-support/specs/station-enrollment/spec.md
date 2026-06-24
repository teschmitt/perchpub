## ADDED Requirements

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
