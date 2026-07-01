# PerchPub

PerchPub is a self-hosted bird-feeder observation server built on top of [FastAPI](https://github.com/fastapi/fastapi).

This is an early-stage project under active development. The end-to-end ingest path — station enrollment, mTLS-authenticated upload, background classification, and observation persistence — is wired up; the frontend and ActivityPub publishing are not. Submit a PR or an issue if you want to help it along.

The goal of the project is to:

- Receive photos (and optionally short videos) of birds visiting a feeder.
- Identify bird species using image recognition.
- Store and display observations for authenticated users.
- Optionally publish observations into the Fediverse via ActivityPub (so they can be followed from Mastodon, Pixelfed, etc.).

The overall system consists of:

- **Station software (Raspberry Pi)** – built in a separate project and responsible for capturing media at the feeder and sending it to this server.
- **PerchPub server (this repository)** – receives uploads, runs image classification, stores observations, and exposes them via an API and web UI.

A link to the Raspberry Pi station project will be added later.

## Backend: Observation, Classification, and Sharing

This repository contains the backend that powers PerchPub. At a high level, the backend:

- Exposes an authenticated HTTP API for stations and users.
- Manages users, stations, species, and observations in a relational database.
- Accepts media uploads (images/videos) for each observation.
- Schedules and tracks classification tasks for uploaded media.
- Optionally publishes new observations via ActivityPub.

The backend is organized around a few core concepts:

- **Users and authentication** – standard user accounts with secure password hashing, JWT-based authentication, and optional email-based flows inherited from the template.
- **Stations** – registered devices (e.g. Raspberry Pis) that are allowed to upload observations. Each station authenticates with an mTLS client certificate issued during enrollment by the bundled [step-ca](https://smallstep.com/docs/step-ca/); the server pins the station's identity to the SHA-256 of the certificate's `SubjectPublicKeyInfo`, so cert renewal is a non-event as long as the keypair stays the same.
- **Uploads** – raw media files (images or videos) sent by stations.
- **Observations** – domain objects that connect an upload with a timestamp, a station, and later a species classification.
- **Species** – known bird species that can be referenced by observations.
- **Classification tasks** – background tasks that run image recognition for newly uploaded media and attach the result to an observation.

### API surface

The API is structured into versioned routes under `/api/v1`. It includes endpoints for:

- Managing users and authentication flows.
- Registering and managing stations.
- Creating uploads and observations from stations.
- Listing and querying observations and species.

These endpoints are implemented as FastAPI routers under `backend/app/api/routes`.

### Data model

The data model is implemented using SQLModel and lives under `backend/app/models`. The main models are:

- `User`, `Token`, and related authentication models.
- `Station` and `Enrollment` for managing devices.
- `Upload` and `Observation` for media and bird sightings.
- `Species` for known bird species.
- `ClassifyTask` for tracking image-recognition jobs.

Migrations are managed with Alembic and are stored under `backend/app/alembic`.

### Background processing

Classification and other non-blocking work is handled via background tasks defined in `backend/app/tasks.py`. These tasks are responsible for:

- Scheduling classification for new uploads.
- Updating observations with recognition results.
- Preparing data that can later be sent via ActivityPub.

### ActivityPub and Fediverse integration

PerchPub is intended to optionally publish new observations into the Fediverse:

- New observations can be exposed as ActivityPub activities.
- Fediverse users (e.g. Mastodon, Pixelfed) can follow the bird feeder as if it were an account.

The details of the ActivityPub integration are experimental and may evolve, but the goal is to make each station or server instance publish a stream of bird sightings.

## Running locally

The dev stack runs entirely in Docker Compose. From the repo root:

```bash
cp .env.example .env.dev  # then fill in real values; see "Environment" below
docker compose --env-file .env.dev watch
```

Every `docker compose` invocation in dev needs `--env-file .env.dev` — without it, compose loads no env file and `${STACK_NAME?Variable not set}` substitutions error out. Aliasing `dc='docker compose --env-file .env.dev'` saves repetition.

`docker compose --env-file .env.dev watch` brings up Postgres, Redis, the backend, the worker (Huey + TF Lite classifier), step-ca (device-cert issuance), the frontend, mailcatcher, and adminer. Object storage is an external S3-compatible endpoint configured via `GARAGE_*` (any S3 provider in dev; OVH Object Storage on a Terraform/OVH deploy — see [deploy/terraform/README.md](./deploy/terraform/README.md)); the TF Lite model and media live there and the model is fetched on first classification. The `watch` mode live-syncs backend code into the container as you edit. Once it's up:

| Service | URL |
| --- | --- |
| Backend API + OpenAPI | <http://localhost:8000> / <http://localhost:8000/docs> |
| Frontend | <http://localhost:5173> |
| Adminer (DB) | <http://localhost:8080> |
| Mailcatcher (SMTP UI) | <http://localhost:1080> |
| step-ca | <https://localhost:9000> |

The first superuser is seeded automatically by `prestart` on each startup. To re-seed manually (e.g. after wiping `pgdata`):

```bash
docker compose --env-file .env.dev exec backend python app/initial_data.py
```

For the full local-dev workflow (host-Python alternative, debugger, watch overrides) see [development.md](./development.md) and [backend/README.md](./backend/README.md).

### Environment

The backend's `Settings` does **not** auto-load any env file. In Docker, `.env.dev` is injected via each service's `env_file:` entry; on the host you need `set -a && . .env.dev && set +a` before `fastapi dev`. The minimum to boot is `PROJECT_NAME`, `POSTGRES_*`, `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`, `SECRET_KEY`, `GARAGE_*`, `HUEY_REDIS_HOST`, and `ENROLLMENT_HMAC_KEY_HEX`. Generate fresh secrets with `python -c 'import secrets; print(secrets.token_urlsafe(32))'`.

## Running the tests

Two equivalent paths.

**Against a running stack** (fast, what you'll use day-to-day):

```bash
docker compose --env-file .env.dev exec backend bash scripts/tests-start.sh
```

Pytest args pass through, e.g. `docker compose --env-file .env.dev exec backend bash scripts/tests-start.sh -x -k upload` to stop on the first failure in upload tests.

**Standalone, on the host** (also what CI runs):

```bash
cd backend
uv sync
bash scripts/test.sh
```

`scripts/test.sh` sources `../.env.dev` itself if present and runs pytest under `coverage`; the HTML report lands in `backend/htmlcov/index.html`.

Lint and typecheck:

```bash
cd backend
bash scripts/lint.sh   # mypy + ruff check + ruff format --check
bash scripts/format.sh # ruff format + ruff check --fix
```

## Deploying a server

Production deploys to a **single OVH Public Cloud instance, provisioned by Terraform**. The runbook — OVH/OpenStack bootstrap, `terraform apply`, and the post-apply smoke test — is in [deploy/terraform/README.md](./deploy/terraform/README.md). Terraform owns the infrastructure (instance + block volume + S3 bucket/credentials + DNS) and generates the app secrets; `cloud-init` then installs Docker, renders `/opt/perchpub/.env.prod`, and brings the Compose stack up with the prod overlay. At a high level the deploy gives you:

- One OVH instance with an attached block volume holding the stateful data (`pgdata` / `redis` / `step-ca` under `/mnt/perchpub-data`).
- OVH-managed DNS A records for the apex, `api`, `dashboard`, and `adminer`.
- Media + the TF Lite model in **OVH Object Storage** (S3), not on the box.
- An **in-stack Traefik edge** (`docker-compose.prod.yml`) terminating HTTPS via Let's Encrypt on `:443` and enforcing station mTLS on `:8443` for `/api/v1/upload/` (`RequireAndVerifyClientCert` against the device CA + a `passTLSClientCert` middleware). The dev stack runs no proxy — devs and tests hit services on their mapped host ports.
- App secrets generated by Terraform (no placeholder values shipped; see [SECURITY.md](./SECURITY.md)).

Migrations apply automatically on backend start via `prestart`; new migrations are committed under `backend/app/alembic/versions/` and picked up at boot.

## Built on Full Stack FastAPI Template

PerchPub uses the Full Stack FastAPI Template as its foundation. That provides:

- A FastAPI backend with SQLModel models, authentication, and migrations.
- A Docker Compose setup for running the stack locally or in production.
- Built-in testing, email-based password recovery, and reverse proxy configuration.

For more detailed technical information see [backend/README.md](./backend/README.md), [deployment.md](./deployment.md), and [development.md](./development.md).

## License

PerchPub is licensed under the **GNU Affero General Public License v3.0 or later** (`AGPL-3.0-or-later`); see [LICENSE](LICENSE). Because PerchPub is a network server, the AGPL's section 13 applies: if you run a modified version and let users interact with it over a network, you must offer those users the corresponding source.

Portions derive from the [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template), © 2019 Sebastián Ramírez, used under the MIT License — which permits this relicensing. The template's MIT text is preserved in [LICENSE.mit](LICENSE.mit); see [NOTICE](NOTICE) for details.
