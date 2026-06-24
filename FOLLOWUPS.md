# Follow-ups

Issues found during audit / mTLS-arc remediation. Format matches
[PLAN.md](PLAN.md) work items.

## Open

- **FU-20** `compose-env-files-required-by-default`: `docker-compose.yml`
  services hard-reference `env_file: .env.prod` and
  `docker-compose.override.yml` services reference `.env.dev` — both
  gitignored. Compose v2 *appends* env_file lists during base+override
  merge, so any service defined in both files needs both files on disk
  regardless of which `--env-file` is passed at the CLI. CI works around
  this by `cp .env.example .env.{dev,prod}` before any compose call
  (commits 1ad5894 + 5f3bf68 + 5402d87). Durable fix: mark them optional
  in the compose files (`env_file: [{path: .env.prod, required: false},
  ...]`) so missing files don't break compose-up. Same change makes a
  fresh clone usable before the user runs `cp .env.example .env.dev`.

- **FU-21** `env-example-drift-from-compose-substitutions`: nothing forces
  `.env.example` to cover every `${VAR?Variable not set}` reference in
  `docker-compose.yml`. `STEP_CA_ADMIN_PASSWORD` slipped through —
  added to compose in e603eed, backfilled into `.env.example` only after
  CI broke (d4e2d98). Add a sanity step (lint.sh entry or its own CI
  step) that diffs `${VAR?...}` keys against `.env.example` and fails on
  drift, e.g.
  `comm -23 <(grep -hoE '\$\{[A-Z_][A-Z0-9_]*' docker-compose*.yml | sed 's/^\${//' | sort -u) <(grep -oE '^[A-Z_][A-Z0-9_]*' .env.example | sort -u)`.

- **FU-22** `prestart-sh-not-self-sourcing`: `scripts/prestart.sh` calls
  `python app/backend_pre_start.py` + `alembic upgrade head` +
  `python app/initial_data.py` without sourcing any env file. In the
  backend container this is fine (env is injected via the service's
  `env_file:` directive). On the host (CI, host-dev) `Settings()` raises
  ValidationError because required fields are unset. CI works around it
  by sourcing inline in the migrate step (commit 73f8443). Durable fix:
  mirror `scripts/test.sh`'s pattern at the top of `prestart.sh`:
  `if [ -f ../.env.dev ]; then set -a && . ../.env.dev && set +a; fi`.

- **FU-23** `integration-test-sh-silent-skip-on-no-docker`:
  `backend/scripts/integration-test.sh:13-16` exits 0 when `docker` is
  not on PATH — a host-developer ergonomic so the unit-test loop
  doesn't fail without docker installed. In CI a misconfigured runner
  without docker would silently green the build. Change to `exit 0`
  only when `$CI` (or equivalent runner sentinel) is unset, else
  `exit 1`.

- **FU-26** `prod-classifier-model-not-seeded-by-iac`: classification
  works in prod only because the TF Lite model + labels happen to live
  in the OVH S3 bucket at `CLASSIFICATION_MODEL_OBJECT_NAME` /
  `CLASSIFICATION_LABELS_OBJECT_NAME` (`birdiary-v0.1/classify.tflite`,
  `birdiary-v0.1/labels.txt`). Nothing in the Terraform/compose prod
  bring-up PUTs them there — dev seeds via the dev-only `minio-init`
  one-shot ([docker-compose.override.yml](docker-compose.override.yml),
  `mc cp ./classification/{classify.tflite,probability-labels-en.txt}`),
  which the prod overlay does not run. The objects survive an instance
  rebuild (they sit in object storage, not the block volume), so this is
  latent, not active — but a fresh bucket, a new region, or a bucket wipe
  leaves `_get_classifier()` ([tasks.py](backend/app/tasks.py)) raising on
  first task → every `ClassifyTask` → `Failed`. Durable fix: an idempotent
  seed step in the prod path (Terraform `aws_s3_object` for the two keys,
  or a one-shot uploader container) that pushes
  `backend/classification/{classify.tflite,probability-labels-en.txt}`
  to the configured object keys.

- **FU-27** `perchstation-client-truncates-http2-response-body`
  (cross-repo — perchstation, the Rust station client; NOT a perchpub
  bug): the station's HTTP client parses only the FIRST HTTP/2 DATA frame
  of the `POST /api/v1/upload/` response instead of draining to
  end-of-stream. The prod Traefik `:8443` edge negotiates h2 and splits
  the ~457-byte `ClassifyTaskPublic` body across frames, so serde_json
  fails `premature end of input at line 1 column 394` (the first-frame
  boundary, not a JSON boundary) and the clip is recorded "delivered,
  classify status unknown". Backend + Traefik are verified correct: `curl`
  over the SAME h2 path receives all 457 bytes / valid JSON
  (`content-length: 457`, `size_download=457`). Never surfaced earlier
  because the dev test hit `backend:8000` over plain HTTP/1.1 (one read).
  Fix in perchstation: read the body to EOF (reqwest `.json()`/`.bytes()`,
  or loop `h2` DATA frames until `None`) before deserializing; forcing
  HTTP/1.1 is a stopgap. Recorded here so the next person doesn't
  re-debug the backend.

- **FU-28** `classify-task-read-is-unauthenticated-and-unscoped`: the
  classify-task GET handlers
  ([backend/app/api/routes/classify_tasks.py](backend/app/api/routes/classify_tasks.py))
  take only `SessionDep` — no `CurrentUser`, no `CurrentStation`, no
  per-station filter. `GET /api/v1/classify-task/{id}` returns any task by
  UUID and `GET /api/v1/classify-task/` enumerates every task across all
  stations, exposing `file_metadata`, `object_name`, `station_id`, and the
  linked observation. These are **already** reachable unauthenticated on
  the public `:443` edge (`backend-https` routes all of
  `Host(api.${DOMAIN})` in [docker-compose.yml](docker-compose.yml)), so
  the gap pre-dates the mTLS work; adding the `:8443` `mtls-classify-task`
  router (this change — fixes the station-poll 404) is strictly *more*
  restrictive on its path (requires an enrolled station cert) and does not
  widen the exposure. Not fixed here because the same handler is the
  intended frontend/admin (JWT-user) read path: bolting `CurrentStation`
  on would break that path and the four anonymous unit tests in
  [test_classify_tasks.py](backend/tests/api/routes/test_classify_tasks.py),
  and change the public contract. Durable fix: a dual-auth dependency
  (superuser **or** the calling station) and scope the queries by the
  station that owns the upload (`select(ClassifyTask).join(Upload).where(
  Upload.station_id == current_station.id)` — `ClassifyTask` has no direct
  `station_id`, it joins through `Upload`). The `:8443` router already
  forwards the verified leaf via `pass-client-cert`, so the station
  identity is available the moment scoping lands — no Traefik change
  needed then.

## Resolved

Compressed to one-line summaries; full context in commit messages.

- **FU-01 (8298c4c)** `pre-start-mock-typo`: fixed `called_once_with`
  typo in pre-start tests; uncovered + fixed two latent bugs (wrong
  patch target, mock context-manager protocol).
- **FU-02 (1ca8046)** `ci-python-version`: pinned Forgejo CI to Python
  3.12 to match Dockerfile + pyproject.
- **FU-03 (2258ba7)** `uv-dev-deps-deprecation`: migrated
  `tool.uv.dev-dependencies` → `dependency-groups.dev` per PEP 735.
- **FU-04 (e720bc0)** `lint-script-short-circuits`: dropped `set -e`
  from `scripts/lint.sh`; mypy no longer hides ruff findings.
- **FU-05 (f0a11ce)** `classify-task-handler-misnamed`: renamed
  `read_observation` → `read_classify_task` in `classify_tasks.py`.
- **FU-06 (a987e41)** `species-create-missing-classification-id`:
  `SpeciesCreate` now requires `classification_id`; gives mTLS-06's
  `_lookup_species_id` a working population path.
- **FU-07 (cb3546a)** `station-owner-self-update`: station owners can
  PUT their own station; non-owner-on-private returns 404 (existence-
  leak avoidance, mirrors `read_station`).
- **FU-08 (WI-13)** `tasks-init-uncaught-network`: subsumed by WI-13's
  lazy `_get_classifier()`; `app.tasks` import no longer touches Garage.
- **FU-09 (034a8ea + 04389c4)** `upload-route-broad-except`: dropped
  the bare `except Exception` around `put_object` and around the lazy
  `classify_video` enqueue; storage / enqueue failures route to
  FastAPI's default 500 instead of leaking `str(e)` into the response.
- **FU-10 (c50ba38)** `tasks-worker-fetch-error-handling`: replaced
  `HTTPException` + duplicate `Session` in the worker fetch-failure
  path with `PerchpubTaskError` + outer-session reuse. Surfaced a real
  bug — the duplicate session was *broken*, not just ugly
  (`InvalidRequestError: Object is already attached to session`).
- **FU-11 (f495a9a)** `traefik-docker-provider-broken-in-dev`: dropped
  Traefik from the dev stack entirely; devs hit services on mapped
  ports. mTLS-05's `dynamic.yml` content survives in git history at
  `git show f495a9a^:traefik/dynamic.yml` for the deferred prod-mTLS
  port.
- **FU-12 (2026-04-26, no tracked commit — `.env.*` is gitignored)**
  `secrets-rotation-deferred`: rotated `POSTGRES_PASSWORD`,
  `GARAGE_KEY_ID` / `GARAGE_SECRET`, and `STEP_CA_ADMIN_PASSWORD` in
  `.env.dev` / `.env.prod`. Old Hetzner key revocation is user-side
  panel work; the residual `STEP_CA_ADMIN_PASSWORD` load-bearing gap
  was closed in FU-19; `.env.prod` Garage values stay placeholders
  until self-hosted Garage actually deploys.
- **FU-13 (88c7fcd)** `backend-step-ca-volume-overbroad`: replaced the
  broad `step-ca:/home/step-ca:ro` mount on the backend with two
  `subpath` mounts (`backend-provisioner.jwk` file + `certs/` dir);
  backend no longer sees CA root password / intermediate key /
  templates / db.
- **FU-14 (d3a19bb)** `provisioner-init-jwk-overwrite-fails`: init
  script now `rm -f`s the JWK before redirecting decrypt output;
  consecutive `down/up` cycles work cleanly without manual cleanup.
- **FU-15 (8f51fdf)** `env-file-duplication`: dropped `.env`,
  consolidated on `.env.dev` / `.env.prod` with `--env-file` on every
  `docker compose` call. Removed redundant `environment: -
  VAR=${VAR}` re-imports from `docker-compose.yml`. DB healthcheck
  flipped to container-runtime expansion (`pg_isready -U
  $$POSTGRES_USER`).
- **FU-16 (48e9d7d + c11ed91)** `test-suite-wipes-dev-db`:
  `scripts/test.sh` now exports `POSTGRES_DB=app_test` and provisions
  the test DB itself; `tests/conftest.py` forces the same env at
  import time as defense-in-depth against direct `pytest` invocations
  inheriting `POSTGRES_DB=app`.
- **FU-18 (0a66d56)** `ruff-backlog`: cleared the pre-existing ruff
  findings surfaced once FU-04 stopped lint.sh from short-circuiting
  (one unused import + four format-only files).
- **FU-19** `step-ca-admin-password-not-load-bearing`: pinned step-ca's
  first-init admin password to `STEP_CA_ADMIN_PASSWORD` via
  `DOCKER_STEPCA_INIT_PASSWORD` in `docker-compose.yml`. Fresh-init
  smoke confirms `step-ca-provisioner-init` exits 0 and adds the
  `backend-device-enrollment` provisioner without scraping logs.
  No-op for already-initialized volumes.
- **FU-24 (d8b4bf8)** `prod-worker-runs-fastapi-not-huey`: the `worker`
  service in [docker-compose.yml](docker-compose.yml) had no `command:`,
  so the Huey `huey_consumer` invocation lived ONLY in the dev override.
  Prod composes `docker-compose.yml` + `docker-compose.prod.yml` WITHOUT
  the override, so the worker inherited the image default `CMD ["fastapi",
  "run", ...]` ([backend/Dockerfile](backend/Dockerfile)) — a second API
  server, nothing draining Redis. Uploads enqueued fine
  (`ClassifyTask.status="Prepared"`, `LLEN huey.redis.perchpub` climbing)
  but never classified. Moved the `command:` into the base compose so
  every environment gets it; dropped the now-redundant override copy.
- **FU-25 (d99aa12)** `mtls-station-auth-rejects-traefik-cert-chain`:
  `get_current_station` ([backend/app/api/deps.py](backend/app/api/deps.py))
  assumed `X-Forwarded-Tls-Client-Cert` held a single cert. Traefik's
  `passTLSClientCert(pem: true)` forwards the whole verified chain as
  comma-separated armor-stripped base64 (`<leaf_b64>,<intermediate_b64>`,
  leaf first). The decoder wrapped the entire blob in one PEM armor,
  landing the leaf's `=` padding mid-block → `load_pem_x509_certificate`
  `InvalidByte` → generic 401 "client certificate required" on EVERY
  upload despite clean enrollment and a cert Traefik had already verified
  at the handshake. Fix: split on `,`, pin the leaf (first entry), then
  parse as before. Verified against the captured prod header (old logic
  reproduces the `InvalidByte`; new logic extracts the enrolled leaf and
  computes the matching SPKI pin); regression test added for the chain
  format alongside the armored / body-only shapes.
