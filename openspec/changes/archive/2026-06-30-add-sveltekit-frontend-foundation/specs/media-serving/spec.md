## ADDED Requirements

### Requirement: Browser-facing media retrieval endpoint

The backend SHALL expose `GET /api/v1/media/{object_name:path}` that streams the stored object identified by `object_name` (the S3 key persisted on an observation, of the form `<h[:2]>/<h[2:4]>/<h><ext>`) from the configured object store via the existing Garage/minio client. The response SHALL carry a `Content-Type` derived from the key's extension and a `Cache-Control: public, max-age=31536000, immutable` header (objects are content-addressed, so a key's bytes never change). A request for a key with no stored object SHALL return `404`. The endpoint SHALL be implemented so that a per-station `is_private` visibility check can later be enforced without changing the URL contract.

#### Scenario: an existing object is streamed with caching headers
- **WHEN** a client requests `GET /api/v1/media/{object_name}` for a key that exists in the bucket
- **THEN** the backend responds `200` with the object bytes, a `Content-Type` matching the key extension, and `Cache-Control: public, max-age=31536000, immutable`

#### Scenario: a missing object returns 404
- **WHEN** a client requests a media key that does not exist in the bucket
- **THEN** the backend responds `404`

### Requirement: Same-origin media delivery to the browser

The web frontend SHALL serve media to the browser from its own origin via a `/media/{object_name}` pass-through that proxies the backend media endpoint over the internal network, so that `<img>`/`<video>` sources are plain same-origin URLs. A helper SHALL convert an observation's `object_name` into its `/media/{object_name}` URL.

#### Scenario: media renders from a same-origin URL
- **WHEN** a rendered page references an observation's media
- **THEN** the media element's URL is `/media/{object_name}` on the page's own origin, and the SvelteKit server streams the bytes from the backend media endpoint
