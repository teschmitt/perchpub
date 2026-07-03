# enrollment-hardening Specification

## Purpose
TBD - created by archiving change harden-enrollment-for-multitenancy. Update Purpose after archive.
## Requirements
### Requirement: Enrollment endpoints are rate-limited

The service SHALL rate-limit enrollment on a multi-tenant deployment. `POST /api/v1/enrollment/create` SHALL be rate-limited per authenticated user, and `POST /api/v1/enrollment/confirm/{session_id}` SHALL be rate-limited per source (in addition to the existing ≤3-attempts-per-session cap). A request exceeding a rate limit SHALL be rejected with `429` and a `Retry-After` header **before** any enrollment side effect — no CSR sent to step-ca, no `Station` created, no `EnrollmentToken` persisted. Rate limits are a throttle, not the authorization boundary; if the limiter's backing store is unavailable the service MAY fail open, logging the degradation. Superusers MAY be exempt.

#### Scenario: confirm attempts beyond the per-source rate are rejected without signing
- **WHEN** requests to `POST /enrollment/confirm/{session_id}` from one source exceed the configured per-source rate
- **THEN** the excess requests are rejected with `429` and `Retry-After`, and no CSR is sent to step-ca and no `Station` row is created

#### Scenario: create beyond the per-user rate is rejected without persisting a token
- **WHEN** an authenticated user calls `POST /enrollment/create` more often than the configured per-user rate
- **THEN** the excess requests are rejected with `429` and no new `EnrollmentToken` is persisted

### Requirement: Per-user enrollment and station quotas

The service SHALL enforce a per-user ceiling on concurrently-active (unclaimed, unexpired) enrollment sessions and on total owned, non-revoked stations, and SHALL enforce each ceiling atomically per user so that concurrent requests cannot both exceed it. The active-session ceiling SHALL be enforced at `POST /api/v1/enrollment/create` (`403`, no `EnrollmentToken` persisted). The owned-station ceiling SHALL be enforced wherever a **new** station is created — a `POST /api/v1/enrollment/confirm/{session_id}` that would create a new station (rejected **before** any CSR is signed) and `POST /api/v1/station/` — with `403` and no station created. Re-enrolling an **existing** owned station to refresh its certificate SHALL NOT be blocked by the station ceiling (certificate refresh has no other path). Superusers SHALL be exempt from these quotas.

#### Scenario: a user at their station ceiling cannot enroll a new station
- **WHEN** a non-superuser at the configured owned-station ceiling completes `POST /enrollment/confirm/{session_id}` with a CSR for a new device key
- **THEN** the request is rejected with `403` before any CSR is signed and no new `Station` is created

#### Scenario: a user at their station ceiling can still refresh an existing station
- **WHEN** a non-superuser at the configured owned-station ceiling re-enrolls one of their existing stations (a CSR bearing that station's device key, i.e. the same SPKI)
- **THEN** the certificate is refreshed and the request succeeds — the station ceiling does not block refresh

#### Scenario: direct station creation respects the station ceiling
- **WHEN** a non-superuser at the configured owned-station ceiling calls `POST /api/v1/station/`
- **THEN** the request is rejected with `403` and no new `Station` is created

#### Scenario: a user at their active-session ceiling cannot open another session
- **WHEN** a non-superuser holding the configured maximum of active (unclaimed, unexpired) sessions calls `POST /enrollment/create`
- **THEN** the request is rejected with `403` and no new `EnrollmentToken` is persisted

### Requirement: Enrollment actions are recorded in a queryable audit trail

The service SHALL persist an attributable audit record for enrollment lifecycle events in a dedicated table. On session creation it SHALL record the actor user, the source, and the timestamp. On a completed confirm it SHALL record the source, the timestamp, the originating `session_id` and its owner, and the resulting `Station.spki_sha256` and `station_id`. On revocation it SHALL record the actor and the affected `station_id`. The trail SHALL be sufficient to attribute a rogue or unexpected enrollment to its originating session and actor after the fact. Audit rows SHALL be retained for a configurable window and purged thereafter.

#### Scenario: a completed enrollment is attributable
- **WHEN** a device completes `POST /enrollment/confirm/{session_id}` and a `Station` is created
- **THEN** an audit record links the resulting `Station.spki_sha256` and `station_id` to the `session_id`, its creating user, and the confirm's source and timestamp

#### Scenario: audit rows past the retention window are purged
- **WHEN** the retention purge runs and audit rows older than the configured window exist
- **THEN** those rows are deleted and rows within the window are retained

### Requirement: An owner can revoke a station so its certificate no longer authenticates

An owner (and a superuser) SHALL be able to revoke one of their stations via `POST /api/v1/station/{id}/revoke`, non-destructively (observations and uploads are retained). After revocation the station's certificate SHALL no longer authenticate as a station: identity resolution (`get_current_station`) SHALL refuse a revoked station's leaf with the generic mTLS `401`, so no upload is stored and nothing is attributed to it, and the station SHALL no longer appear in the owner's active station list. Recovery SHALL require re-enrolling a fresh device key (a new identity); re-enrolling the revoked key SHALL NOT reactivate it. A non-owner SHALL be refused — `403` for a public station, `404` for a private one, mirroring station update's existence-leak avoidance.

This contract is enforced at the application identity layer — the sole cert→account authority, since station uploads are only accepted through that resolver. Cryptographic revocation at the TLS edge (CRL/OCSP) is out of scope (the current Traefik file-provider edge cannot consult a CRL); the residual window in which a revoked leaf can still complete a TLS *handshake* before being refused with `401` is bounded by the device leaf's own lifetime and is a rate-limiting/DoS concern, not an integrity one. See [design.md](../../design.md) D1.

#### Scenario: a revoked station's leaf no longer authenticates an upload
- **WHEN** an owner revokes a station and that station subsequently presents its previously-valid leaf to the mTLS upload entrypoint
- **THEN** identity resolution refuses it with `401`, no upload is stored, and the station no longer appears in the owner's active station list

#### Scenario: re-enrolling the revoked key does not reactivate it
- **WHEN** a revoked station re-submits `POST /enrollment/confirm/{session_id}` with a CSR bearing the same device key (same SPKI)
- **THEN** the enrollment is refused and the station remains revoked (recovery requires a fresh device key)

#### Scenario: a non-owner cannot revoke another tenant's station
- **WHEN** a user who neither owns the station nor is a superuser calls `POST /station/{id}/revoke`
- **THEN** the request is refused (`403` for a public station, `404` for a private one) and the station is not revoked

### Requirement: Station identity is resolved only by SPKI pin

Station identity SHALL be resolved **only** by matching `SHA-256(SubjectPublicKeyInfo)` of the presented leaf against `Station.spki_sha256` (and thence `owner_id`). No authorization decision SHALL depend on the leaf's Common Name or Subject Alternative Names, since a station controls those via its CSR and the step-ca OTT authorizes CSR-requested SANs verbatim. This guarantee SHALL be covered by a regression test.

#### Scenario: a leaf with a spoofed SAN is resolved only by SPKI
- **WHEN** a station presents a valid device-CA leaf whose CN/SAN names another tenant's station
- **THEN** identity resolves to whichever `Station` matches the leaf's `SHA-256(SPKI)` (or none, yielding `401`), and the CN/SAN has no effect on which account or resources the request may touch

