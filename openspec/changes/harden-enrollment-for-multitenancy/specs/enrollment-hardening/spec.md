## ADDED Requirements

> Requirements are stated as behavioral contracts; their *mechanisms* are open questions in [design.md](../../design.md) and MUST be resolved (and these scenarios expanded) before implementation.

### Requirement: Enrollment endpoints are rate-limited and quota-bounded

The service SHALL bound enrollment abuse on a multi-tenant deployment: `POST /api/v1/enrollment/create` SHALL be rate-limited per authenticated user, and `POST /api/v1/enrollment/confirm/{session_id}` SHALL be rate-limited per source and per session (in addition to the existing per-session attempt cap). The service SHALL enforce a per-user ceiling on concurrently-active enrollment sessions and on total owned stations. Requests exceeding a limit SHALL be rejected without performing the enrollment side effect (no CSR signing, no `Station` creation).

#### Scenario: confirm attempts beyond the limit are rejected without signing
- **WHEN** requests to `POST /enrollment/confirm/{session_id}` exceed the configured per-source or per-session rate
- **THEN** the excess requests are rejected and no CSR is sent to step-ca and no `Station` row is created

#### Scenario: a user beyond their station quota cannot create more sessions
- **WHEN** a user who is at their configured station/active-session ceiling calls `POST /enrollment/create`
- **THEN** the request is rejected and no new `EnrollmentToken` is persisted

### Requirement: Enrollment actions are recorded in an audit trail

The service SHALL record an attributable audit record for enrollment lifecycle events: for session creation, the actor user, the source, and the timestamp; and for a completed confirm, the source, the timestamp, and the resulting `Station.spki_sha256`. The audit trail SHALL be sufficient to attribute a rogue or unexpected enrollment to its originating session and actor after the fact.

#### Scenario: a completed enrollment is attributable
- **WHEN** a device completes `POST /enrollment/confirm/{session_id}` and a `Station` is created
- **THEN** an audit record links the resulting `Station.spki_sha256` to the session, its creating user, and the confirm's source and timestamp

### Requirement: A station can be revoked so its certificate no longer authenticates

An owner (and a superuser) SHALL be able to revoke one of their stations such that the station's certificate can **no longer authenticate an mTLS upload** at the edge — not merely be de-attributed. The mechanism (short-lived certs + renewal vs CRL/OCSP) is a design decision, but the observable contract is that after revocation the revoked leaf is rejected on the mTLS entrypoint serving `/api/v1/upload/`.

#### Scenario: a revoked station is refused at the mTLS edge
- **WHEN** an owner revokes a station and that station subsequently presents its previously-valid leaf to the mTLS upload entrypoint
- **THEN** the request is refused (the revoked certificate no longer authenticates), and the station no longer appears as an active station for the owner

### Requirement: Station identity is resolved only by SPKI pin

Station identity SHALL be resolved **only** by matching `SHA-256(SubjectPublicKeyInfo)` of the presented leaf against the enrollment-time `Station.spki_sha256` (and thence `owner_id`). No authorization decision SHALL depend on the leaf's Common Name or Subject Alternative Names, since a station controls those via its CSR and the OTT authorizes CSR-requested SANs verbatim.

#### Scenario: a leaf with a spoofed SAN is still resolved only by SPKI
- **WHEN** a station presents a valid device-CA leaf whose CN/SAN name another tenant's station
- **THEN** identity resolves to whichever `Station` matches the leaf's `SHA-256(SPKI)` (or none), and the CN/SAN has no effect on which account or resources the request may touch
