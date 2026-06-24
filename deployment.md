# PerchPub - Deployment

Production deploys to a **single OVH Public Cloud instance, provisioned by Terraform**. Terraform owns the infrastructure *around* the app (instance + block volume + S3 bucket/credentials + OVH DNS + generated secrets); `cloud-init` installs Docker, mounts the block volume, clones this repo to `/opt/perchpub`, renders `/opt/perchpub/.env.prod`, and brings the Compose stack up with the in-stack Traefik edge.

> **The infra runbook lives in [deploy/terraform/README.md](./deploy/terraform/README.md)** — OVH/OpenStack bootstrap, the one-time DNS-zone + registrar-NS repoint, `terraform apply`, and the post-apply smoke test. This document covers the application-level pieces that runbook references: how the prod stack is composed, secret generation, S3 model placement, and the step-ca / mTLS bootstrap.

## Topology

A Terraform deploy brings up the existing Compose topology (backend, worker, db, redis, step-ca + provisioner-init, frontend, adminer) plus an **in-stack Traefik** added by the prod overlay [docker-compose.prod.yml](./docker-compose.prod.yml):

- HTTPS termination via Let's Encrypt on `:443` for `api.<domain>`, `dashboard.<domain>`, and `adminer.<domain>`.
- A dedicated **mTLS entrypoint on `:8443`** for `/api/v1/upload/`, configured with `RequireAndVerifyClientCert` against the device CA and a `passTLSClientCert` middleware (dynamic config in [deploy/traefik/dynamic/dynamic.yml](./deploy/traefik/dynamic/dynamic.yml)). Traefik mounts the device CA read-only from the shared `step-ca` volume's `certs/` subpath.
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
