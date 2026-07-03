# PerchPub - Deployment

Production deploys to a **single OVH Public Cloud instance, provisioned by Terraform**. Terraform owns the infrastructure *around* the app (instance + block volume + S3 bucket/credentials + OVH DNS + generated secrets); `cloud-init` installs Docker, mounts the block volume, clones this repo to `/opt/perchpub`, renders `/opt/perchpub/.env.prod`, and brings the Compose stack up with the in-stack Traefik edge.

> **The infra runbook lives in [deploy/terraform/README.md](./deploy/terraform/README.md)** — OVH/OpenStack bootstrap, the one-time DNS-zone + registrar-NS repoint, `terraform apply`, and the post-apply smoke test. This document covers the application-level pieces that runbook references: how the prod stack is composed, secret generation, S3 model placement, and the step-ca / mTLS bootstrap.

## Topology

A Terraform deploy brings up the existing Compose topology (backend, worker, db, redis, step-ca + provisioner-init, frontend, adminer) plus an **in-stack Traefik** added by the prod overlay [docker-compose.prod.yml](./docker-compose.prod.yml):

- HTTPS termination via Let's Encrypt on `:443` for `api.<domain>`, `dashboard.<domain>`, and `adminer.<domain>`.
- A dedicated **mTLS entrypoint on `:8443`** for the station-facing routes — `/api/v1/upload/` (POST media) and `/api/v1/classify-task/` (poll the classification result) — configured with `RequireAndVerifyClientCert` against the device CA and a `passTLSClientCert` middleware (dynamic config in [deploy/traefik/dynamic/dynamic.yml](./deploy/traefik/dynamic/dynamic.yml)). Both arrive on `:8443` because a station's outbound allowlist permits only this mTLS base. Traefik mounts the device CA read-only from the shared `step-ca` volume's `certs/` subpath.
- The stateful named volumes (`pgdata`, `redis`, `step-ca`) are bound to the attached block volume under `/mnt/perchpub-data` so data survives an instance rebuild.

There is no separately-deployed proxy and no `traefik-public` network to create by hand — the prod overlay declares it. The dev stack runs no proxy at all (FU-11); devs and tests hit services on their mapped host ports.

The prod stack is brought up (by cloud-init, or by hand for a non-Terraform host) with:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

`--env-file .env.prod` is the single source of truth for both compose-parse-time `${VAR}` substitution (image tags, Traefik labels, the ACME `EMAIL`) and per-service `env_file:` injection. The two `-f` files are the base stack plus the prod overlay; omitting `docker-compose.override.yml` keeps dev-only services out.

## Environment variables

Everything runtime-configurable lives in `backend/app/core/config.py` and is supplied through `.env.prod`. On a Terraform deploy, cloud-init renders `/opt/perchpub/.env.prod` from Terraform-generated values — you do not edit it by hand. The notable keys:

- `ENVIRONMENT=production`, `DOMAIN`, `FRONTEND_HOST`, `BACKEND_CORS_ORIGINS`, `PROJECT_NAME`, `STACK_NAME`.
- `EMAIL` — Let's Encrypt registration address for the Traefik ACME resolver.
- `SECRET_KEY`, `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`, `ENROLLMENT_HMAC_KEY_HEX`.
- `POSTGRES_*`.
- Object storage `GARAGE_*` — `GARAGE_ENDPOINT`, `GARAGE_BUCKET_NAME`, `GARAGE_KEY_ID`, `GARAGE_SECRET`, `GARAGE_USE_TLS`, and `GARAGE_REGION`. `GARAGE_REGION` is the SigV4 signature region: `garage` for self-hosted Garage / Minio, and the bucket's lowercase region for a cloud provider (OVH `GRA` → `gra`).
- `CA_NAME`, `STEP_CA_*` — step-ca integration (see below).
- `CLASSIFICATION_MODEL_OBJECT_NAME` / `CLASSIFICATION_LABELS_OBJECT_NAME`, `HUEY_*`.
- Enrollment safety controls (multi-tenant) — `ENROLLMENT_CREATE_RATE_PER_MIN`, `ENROLLMENT_CONFIRM_RATE_PER_MIN`, `MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER`, `MAX_STATIONS_PER_USER`, `ENROLLMENT_AUDIT_RETENTION_DAYS`. See [Enrollment safety controls](#enrollment-safety-controls-multi-tenant).

### Generate secret keys

On a **Terraform deploy these are generated for you** (`deploy/terraform/secrets.tf`) and rendered into `/opt/perchpub/.env.prod`; the steps below apply only to a **manual / non-Terraform** host.

`SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD`, `POSTGRES_PASSWORD`, `ENROLLMENT_HMAC_KEY_HEX`, and `STEP_CA_ADMIN_PASSWORD` need real values before the first deploy. Generate with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# for ENROLLMENT_HMAC_KEY_HEX use bytes(32).hex():
python -c "import secrets; print(secrets.token_bytes(32).hex())"
```

`STEP_CA_ADMIN_PASSWORD` is wired into step-ca's first-boot init via `DOCKER_STEPCA_INIT_PASSWORD: ${STEP_CA_ADMIN_PASSWORD}` (FU-19): set it in `.env.prod` *before* the first `docker compose up` and step-ca initializes its admin password to that value. No log-scraping, no second-pass env edit.

## URLs

### Production

- Frontend: `https://dashboard.perchpub.net`
- Backend API docs: `https://api.perchpub.net/docs`
- Backend API base URL: `https://api.perchpub.net`
- Adminer: `https://adminer.perchpub.net`
- Station mTLS upload: `https://api.perchpub.net:8443/api/v1/upload/`
- Station mTLS classify-task poll: `https://api.perchpub.net:8443/api/v1/classify-task/{id}`

(Staging and managed-K8s/Postgres are deliberately out of scope for now.)

## Setting up Perchpub services

### Persisting classification data in S3

Models and labels must be made available in the S3 storage. Let Perchpub know where they are through the `CLASSIFICATION_MODEL_OBJECT_NAME` and `CLASSIFICATION_LABELS_OBJECT_NAME` env vars. On a Terraform deploy the bucket is created by `deploy/terraform/storage.tf`; upload the model + labels into it before the first classification.

### Setting up the CA for mTLS

The dev/prod stacks both ship a `step-ca-provisioner-init` container that automates the historical manual recipe (CA bootstrap → provisioner add → JWK extract). On first `up -d` it idempotently creates the `backend-device-enrollment` JWK provisioner against the running CA and writes the decrypted private JWK to the `step-ca` named volume at `/home/step/backend-provisioner.jwk`. The backend mounts that file (subpath-narrow per FU-13) and the `certs/` dir; it never sees the CA root keys or the admin password. The prod Traefik mounts the same `certs/` subpath read-only to enforce station mTLS.

Backend reads `STEP_CA_JWK_PATH=/home/step-ca/backend-provisioner.jwk` and derives the JWK's `kid` at runtime via `PyJWK.key_id`. There is no `STEP_CA_PROVISIONER_KID` env var to paste; mTLS-03 dropped it.

#### step-ca first boot

Set `STEP_CA_ADMIN_PASSWORD` in `.env.prod` *before* the first `docker compose up` (on a Terraform deploy this is the generated value already in the rendered env). step-ca's first-boot init reads it via `DOCKER_STEPCA_INIT_PASSWORD: ${STEP_CA_ADMIN_PASSWORD}` (FU-19) and pins the admin password to that value; `step-ca-provisioner-init` then authenticates with the same env value, decrypts the admin JWK, and adds the `backend-device-enrollment` provisioner. No log-scraping required.

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Verify:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec step-ca step ca provisioner list
```

You should see `admin` (auto-init) and `backend-device-enrollment` (the init container's work).

(`DOCKER_STEPCA_INIT_PASSWORD` only takes effect on a fresh `step-ca` named volume. To re-init from scratch — for instance, to rotate the CA — `down -v` or `docker volume rm perchpub_step-ca` first.)

#### Manual recovery / inspection

```bash
# Inspect or rotate the admin provisioner manually:
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec step-ca step ca token admin

# Check what file the backend is actually reading:
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec backend ls -la /home/step-ca/
# Should show only `backend-provisioner.jwk` and `certs/` — not `secrets/` (FU-13).
```

The backend never needs the admin password directly; only `step-ca-provisioner-init` does, and only on first boot (subsequent runs short-circuit because the provisioner already exists).

#### Generating a device key + CSR (station enrollment)

A station enrolls by generating its **own** keypair + CSR and POSTing the CSR to `/api/v1/enrollment/confirm/{session_id}`. The backend forwards it to step-ca and pins `SHA-256(SubjectPublicKeyInfo)` of the issued leaf as the station identity. The **station** chooses the key type — the server accepts any key algorithm and enforces none — and the issued leaf preserves the CSR's key type.

**Ed25519 is the recommended default** for new stations: smaller and faster to generate on Raspberry Pi-class hardware. **EC P-256 remains fully supported** as an alternative.

**OpenSSL** — Ed25519 (recommended; note there is **no** `-sha256`, an Ed25519 CSR carries no separate hash):

```bash
openssl genpkey -algorithm ed25519 -out device.key
openssl req -new -key device.key -subj '/CN=station-01' -out device.csr
```

EC P-256 (supported alternative):

```bash
openssl ecparam -genkey -name prime256v1 -noout -out device.key
openssl req -new -key device.key -subj '/CN=station-01' -sha256 -out device.csr
```

**Python (`cryptography`)** — Ed25519 signs the CSR with **no** hash algorithm (`.sign(key, None)`); EC/RSA pass `hashes.SHA256()`:

```python
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import NameOID

subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "station-01")])

# Ed25519 (recommended default): no hash algorithm.
key = ed25519.Ed25519PrivateKey.generate()
csr = x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, None)

# EC P-256 (supported alternative): SHA-256.
# key = ec.generate_private_key(ec.SECP256R1())
# csr = x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, hashes.SHA256())

csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")
# POST csr_pem to /api/v1/enrollment/confirm/{session_id}; keep `key` on the
# station to present the issued leaf on mTLS uploads.
```

The `device.crt` / `device.key` used by the post-apply smoke test ([deploy/terraform/README.md](./deploy/terraform/README.md) §4) are, respectively, the leaf returned by enrollment for this CSR and the private key generated here.

## Enrollment safety controls (multi-tenant)

When PerchPub is exposed to many mutually-distrusting users sharing one device CA, the enrollment flow is bounded by rate limits, per-user quotas, an audit trail, and application-layer revocation (the `harden-enrollment-for-multitenancy` change). All are env-configurable via `backend/app/core/config.py` → `.env.prod`; the defaults are conservative starting points and can be tuned without a code change.

### Rate limits and quotas

| Setting | Default | Applies to |
| --- | --- | --- |
| `ENROLLMENT_CREATE_RATE_PER_MIN` | `5` | `POST /api/v1/enrollment/create`, per authenticated user |
| `ENROLLMENT_CONFIRM_RATE_PER_MIN` | `10` | `POST /api/v1/enrollment/confirm/{session_id}`, per source IP (on top of the ≤3-attempts-per-session cap) |
| `MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER` | `5` | ceiling on concurrently-active (unclaimed, unexpired) sessions |
| `MAX_STATIONS_PER_USER` | `25` | ceiling on owned, non-revoked stations |

- **Rate limits are a throttle, not the security boundary.** They are Redis-backed (the in-stack Huey Redis) and **fail open**: if Redis is unreachable the limiter logs a warning and allows the request. Exceeding a rate yields `429` + `Retry-After` *before* any CSR is signed or row written.
- **Quotas are DB-backed and always enforced.** Exceeding a quota yields `403` with nothing persisted. The station ceiling is checked when an enrollment **session is created**, so the true station count can overshoot `MAX_STATIONS_PER_USER` by at most `MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER`.
- **Superusers are exempt** from the create-rate and both quotas.
- **The confirm limit and the audit `source` key on the leftmost `X-Forwarded-For` hop.** This is trustworthy only because Traefik is the direct edge with no trusted upstream (it rewrites inbound XFF from the real peer). If you ever front PerchPub with a CDN/LB — or set Traefik `forwardedHeaders.trustedIPs` — revisit this: the leftmost hop becomes client-controlled, letting the per-source limit be bypassed and the audit source poisoned. Note also that many stations behind one NAT share the per-source confirm budget, so raise `ENROLLMENT_CONFIRM_RATE_PER_MIN` for sites enrolling several devices at once.

### Enrollment audit trail

Session creation, successful confirms, and revocations are recorded in the `enrollment_audit` table (actor, source IP, user-agent, originating session, resulting `spki_sha256` + `station_id`, timestamp) so a leaked-token incident is reconstructable and a rogue enrollment is attributable. Query it directly (Adminer, or `docker compose ... exec db psql`). Rows are purged after `ENROLLMENT_AUDIT_RETENTION_DAYS` (default `180`) by a nightly Huey periodic task in the `worker` container.

### Revoking a station

Revocation is enforced at the **application identity layer** — `get_current_station`, the sole cert→account authority (the only place a certificate is mapped to a station/owner). The Traefik file-provider mTLS edge cannot consult a CRL/OCSP, so cryptographic revocation at the TLS handshake is a separate, deferred effort; app-layer revocation plus short leaf lifetimes is the current control.

Revoke as the station's **owner** (or a superuser) — obtain an access token from `POST /api/v1/login/access-token`, then:

```bash
curl -X POST https://api.perchpub.net/api/v1/station/<STATION_ID>/revoke \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

What revocation does — immediately, at the resolver:

- The station's certificate **no longer authenticates**: an mTLS upload presenting its leaf is refused with the generic `401` — no upload is stored and nothing is attributed to it.
- The station **drops out of the active station list** (`GET /api/v1/station/`), for its owner and superusers alike.
- It is **non-destructive** (existing observations and uploads are retained) and writes a `station_revoked` audit row; and **idempotent** (re-revoking keeps the original `revoked_at`).
- A non-owner is refused — `403` for a public station, `404` for a private one (mirroring station update's existence-leak avoidance).

Residual window and recovery:

- A revoked leaf can still complete a **TLS handshake** until it expires, then is refused with `401` — so it performs no action (an integrity-neutral, rate-limited concern). The window is bounded by the device leaf's own lifetime.
- **Recovery is a fresh device key, not un-revoking:** re-enrolling the *same* key (same SPKI) is refused with `409`. Generate a new keypair → new CSR → new SPKI → a new `Station`.

## Post-deploy smoke test

[`scripts/deploy-smoke.py`](./scripts/deploy-smoke.py) automates the whole station lifecycle against a live deployment as a single command — the manual login → enroll → upload → poll dance in [deploy/terraform/README.md](./deploy/terraform/README.md) §4 condensed into one exit code. It is the canonical post-deploy verification step; run it after `terraform apply` (give DNS + the Let's Encrypt cert time to settle first).

It walks: operator login → enrollment session → device keypair + CSR → step-ca-signed leaf → **real mTLS** media upload (httpx `cert=`, a genuine client-auth handshake against the `:8443` edge — not a hand-stuffed header) → poll `/classify-task/` until an `Observation` is persisted. Exit 0 means the deployment ingested *and classified* an upload end-to-end; a non-zero exit names the failing stage.

The script is self-contained — [PEP 723](https://peps.python.org/pep-0723/) inline metadata declares its only deps (`httpx`, `cryptography`), and a tiny valid MP4 is embedded so no fixture file is needed. Run it with `uv`:

```bash
PERCHPUB_OPERATOR_PASSWORD=<FIRST_SUPERUSER_PASSWORD> \
  uv run scripts/deploy-smoke.py \
    --api-url https://api.perchpub.net \
    --operator-email <owner_email>
```

- `--api-url` is the public `:443` base (health, login, enrollment). The mTLS upload/poll base defaults to the same host on `:8443`; override with `--mtls-url` if it differs.
- The password comes from `$PERCHPUB_OPERATOR_PASSWORD` (read it from the box's `/opt/perchpub/.env.prod` or `terraform output`) or `--operator-password`.
- `--key-type ed25519` (default) or `ec`; `--media-file PATH` to upload a real clip instead of the embedded sample; `--out-dir` keeps the issued `device.crt` / `device.key` / `ca_chain.pem`.
- `--no-mtls` skips the real handshake and hand-stuffs the `X-Forwarded-Tls-Client-Cert` header against `--api-url` — for rehearsing the full ingest path against the **dev** stack (no Traefik, FU-11) before a real deploy exists, e.g. `--api-url http://localhost:8001 --no-mtls`.
- `--cacert` / `--insecure` adjust **server** TLS verification (prod uses a public Let's Encrypt cert, so neither is needed there).

A `Failed` task or a poll timeout is a real signal: most often the classifier model + labels were never seeded into the prod bucket (latent **FU-26** — `_get_classifier()` raises on first task), so the smoke doubles as a model-presence check.
