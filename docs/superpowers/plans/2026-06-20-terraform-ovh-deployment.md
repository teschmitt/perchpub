# Terraform-based OVH Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing PerchPub Docker Compose stack reproducibly deployable to a single OVH Public Cloud instance via Terraform, with media + the TF-Lite model in OVH Object Storage, TF-generated secrets rendered on the box, OVH-managed DNS, and an in-stack Traefik edge that terminates HTTPS (Let's Encrypt) and enforces station mTLS on `:8443/api/v1/upload/`.

**Architecture:** Terraform owns the infrastructure *around* the app (instance + block volume + S3 bucket/creds + DNS + secrets); cloud-init installs Docker, mounts the block volume, clones the public repo, renders `/opt/perchpub/.env.prod`, and runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. The Compose topology (backend, worker, db, redis, step-ca + provisioner-init, frontend, adminer) is preserved as-is; a new prod overlay adds the Traefik edge and binds stateful volumes to the block device. Only one application code change is required (a configurable S3 region).

**Tech Stack:** Terraform (`ovh/ovh ~> 2.0`, `terraform-provider-openstack/openstack ~> 3.0`, `hashicorp/random ~> 3.6`); cloud-init; Docker Compose v2; Traefik 3.x (docker + file providers, ACME/Let's Encrypt, `passTLSClientCert`); smallstep `step-ca`; FastAPI/SQLModel backend; minio-py 7.2.x S3 client.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec / verified against the codebase.

- **Domain:** `perchpub.net`. Subdomains (A records): `@` (apex), `api`, `dashboard`, `adminer`. Frontend host `https://dashboard.perchpub.net`; API host `api.perchpub.net`.
- **OVH Object Storage:** endpoint `s3.gra.io.cloud.ovh.net`; `GARAGE_USE_TLS=True`; **API region casing is uppercase `GRA`**, **S3 SigV4 signature region is lowercase `gra`**; bucket type **`standard`** (NOT `high_performance` — `EXPRESS_ONEZONE` breaks the Minio default upload path, D8).
- **OVH region knob:** default `GRA` (Gravelines); one tfvars variable, trivially changed to `DE`/`SBG`/`WAW`.
- **mTLS edge:** entrypoint on `:8443`; router rule ``Host(`api.perchpub.net`) && PathPrefix(`/api/v1/upload/`)``; middleware `passTLSClientCert` with `pem: true`; header name **`X-Forwarded-Tls-Client-Cert`** (must match `settings.MTLS_CLIENT_CERT_HEADER`).
- **Host firewall is the ingress enforcement mechanism** (OVH OpenStack security groups do NOT reliably filter ingress on `Ext-Net`, §5). cloud-init `nftables`/`ufw` allows inbound **22, 80, 443, 8443 only**. The OpenStack security group is attached for egress hygiene/intent only.
- **Persistent data mount:** `/mnt/perchpub-data`, with `pgdata/`, `redis/`, `step-ca/` subdirs bound into the corresponding named volumes. Media + TF-Lite model live in **S3**, not on the block volume.
- **Repo on the box:** cloned to `/opt/perchpub`; rendered env at `/opt/perchpub/.env.prod`.
- **TF state:** local, gitignored (`*.tfstate*`, `.terraform/`, `*.tfvars` except `*.example`).
- **`GARAGE_REGION` default is `"garage"`** (preserves Garage/dev + Minio/test behaviour; only prod sets `gra`). The minio client exposes its region at `client._base_url.region` (minio 7.2.20 — verified).
- **No `apply` in CI.** Full `terraform apply` needs real OVH credentials + billing and is a documented manual step. IaC tasks gate on `terraform fmt -check` + `terraform validate` + `shellcheck`, not apply.
- **`ssh_allowed_cidr`** tfvars var defaults to `0.0.0.0/0` with a doc warning to narrow it.

---

## Spec corrections & decisions (read before starting)

These resolve ambiguities / errors discovered while verifying the spec against the codebase. They are baked into the tasks below.

1. **`.env.prod` and `.env.dev` are gitignored and were never committed** (`git ls-files` shows only `.env.example`, `.env.test`, `frontend/.env` tracked; `.gitignore` has `.env.*` with `!.env.example`/`!.env.test`). The spec §6's "committed `.env.prod` holds live secrets now in git history" is **inaccurate** for `.env.prod`. Consequence: the repo-level env change is to the **tracked** templates `.env.example` and `.env.test` only. Editing local `.env.dev`/`.env.prod` is local hygiene, not a repo change. The live secrets currently in the working-tree `.env.prod` are still **compromised** (real values on disk) and are replaced by TF-generated ones on a fresh deploy — but **no git-history purge is needed for `.env.prod`** (it was never in history). The root `.env` is a separate historical artifact (already untracked); out of scope.

2. **The mTLS encoding contract is already implemented and tested on the backend.** `backend/app/api/deps.py:113-127` documents that Traefik 3.x `passTLSClientCert.pem=true` URL-encodes the leaf with the PEM armor stripped; the backend uses `urllib.parse.unquote` (NOT `unquote_plus`) and re-attaches the armor. `backend/tests/integration/test_compose_smoke.py:99-108` exercises exactly this header. **No backend mTLS code change is required** — only the Traefik edge (Tasks 3–4). Task 3 includes an end-to-end encoding verification.

3. **`https-redirect` middleware must stay a `@docker`-provider middleware.** The existing labels in `docker-compose.yml` reference it bare (`middlewares=https-redirect`), which Traefik resolves to `https-redirect@docker`. Defining it in the file provider would create `https-redirect@file` and the labels would NOT resolve. → The in-stack Traefik defines `https-redirect` via its own Docker labels (ported from `docker-compose.traefik.yml`), and the file provider carries only the mTLS dynamic config.

4. **`traefik-public` network name must be pinned.** `docker-compose.yml` declares `traefik-public` as `external: true`. The prod overlay redeclares it `external: false` with `name: traefik-public` so the `traefik.docker.network=traefik-public` labels resolve to a compose-created network (no project prefix). This resolves the §14 open item ("keep the external network or collapse to default") in favour of *keep the name, drop external*.

5. **An `EMAIL` env var is added** (ACME registration address for the `le` resolver), rendered by cloud-init from `owner_email`. The base `docker-compose.yml` has no `EMAIL`; the standalone `docker-compose.traefik.yml` used `${EMAIL}`. The prod overlay's Traefik references `${EMAIL?Variable not set}`.

6. **`scripts/test.sh` does not forward pytest args to pytest** (it only uses `$@` for the coverage HTML title). Targeted single-test runs use a direct `python -m pytest` inside the backend container after the `app_test` DB exists (created once by `scripts/test.sh`/`tests-start.sh`). The full canonical run remains `cd backend && bash scripts/test.sh` (host) or `docker compose --env-file .env.dev exec backend bash scripts/tests-start.sh` (stack).

7. **This is one ordered plan, not independent subsystems.** The pieces share contracts (env-var names, file paths, the Traefik header). Phase 1 (the app change) is independently mergeable; Phases 3–4 are coupled (cloud-init brings up the prod overlay). Phase/task ordering below is the build order.

8. **Scope deferred (YAGNI, §15):** staging env, managed K8s/Postgres, remote TF state backend, CI/CD auto-deploy, multi-region/HA, git-history secret purge, registry-based image delivery.

---

## File Structure

**Create:**
- `backend/tests/test_garage_region.py` — unit tests for the configurable S3 region.
- `docker-compose.prod.yml` — prod overlay: in-stack Traefik (http/https/mtls), `https-redirect` label, `traefik-public` name pin, block-volume binds for `pgdata`/`redis`/`step-ca`.
- `deploy/traefik/dynamic/dynamic.yml` — Traefik file-provider dynamic config: `tls.options.mtls` (clientAuth), `passTLSClientCert` middleware, mtls router + backend service.
- `deploy/terraform/providers.tf`, `variables.tf`, `secrets.tf`, `storage.tf`, `compute.tf`, `dns.tf`, `outputs.tf`, `cloud-init.yaml.tftpl`, `terraform.tfvars.example`, `README.md`, `.gitignore`.

**Modify:**
- `backend/app/core/config.py` — add `GARAGE_REGION: str = "garage"`.
- `backend/app/api/routes/uploads.py:25` — `region="garage"` → `region=settings.GARAGE_REGION`.
- `backend/app/tasks.py:48` — `region="garage"` → `region=settings.GARAGE_REGION`.
- `.env.example` (tracked) — add `GARAGE_REGION`, `GARAGE_USE_TLS`, `EMAIL`.
- `.env.test` (tracked) — add `GARAGE_REGION=garage`.
- Local (gitignored) `.env.dev` — add `GARAGE_REGION=garage`; local `.env.prod` — add OVH S3 + `GARAGE_REGION=gra` + `EMAIL` and scrub live secrets to placeholders.
- `README.md`, `deployment.md`, `CLAUDE.md` — replace Hetzner/standalone-Traefik/manual-host deployment narrative with the Terraform runbook; keep step-ca + secret-generation guidance.
- `docker-compose.override.yml` (comments referencing the standalone Traefik file).

**Remove (Task 14):**
- `docker-compose.traefik.yml` — superseded by the in-stack Traefik (after doc references are updated).

---

## Phase 1 — Application change: configurable S3 region

### Task 1: Add `GARAGE_REGION` setting and wire it into both Minio clients

**Files:**
- Modify: `backend/app/core/config.py` (Settings, near the `GARAGE_*` block, lines 58-62)
- Modify: `backend/app/api/routes/uploads.py:25`
- Modify: `backend/app/tasks.py:48`
- Test: `backend/tests/test_garage_region.py` (create)

**Interfaces:**
- Produces: `settings.GARAGE_REGION: str` (default `"garage"`); both module-level `garage_client` instances built with `region=settings.GARAGE_REGION`. Consumed by Task 2 (env templates) and Task 9 (cloud-init renders `GARAGE_REGION=gra`).

**Prerequisite (one-time):** the `app_test` DB must exist + be migrated so the autouse `db` fixture in `conftest.py` can connect. If it doesn't yet, run the canonical setup once: `docker compose --env-file .env.dev exec backend bash scripts/tests-start.sh` (or, host: `cd backend && bash scripts/test.sh`). The dev stack must be up (`docker compose --env-file .env.dev watch`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_garage_region.py`:

```python
import importlib

from app.core.config import Settings, settings


def test_garage_region_defaults_to_garage() -> None:
    # Default preserves Garage/dev + Minio/test behaviour (no signature change).
    assert settings.GARAGE_REGION == "garage"


def test_garage_region_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("GARAGE_REGION", "gra")
    # Pass the other required/secret fields explicitly so construction is
    # warning-free regardless of the ambient env; leave GARAGE_REGION unset
    # as a kwarg so it is sourced from the environment we just set.
    s = Settings(
        PROJECT_NAME="t",
        POSTGRES_SERVER="db",
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="pw",
        FIRST_SUPERUSER="a@b.co",
        FIRST_SUPERUSER_PASSWORD="pw",
        SECRET_KEY="x" * 43,
        ENROLLMENT_HMAC_KEY_HEX="ab" * 32,
    )
    assert s.GARAGE_REGION == "gra"


def test_uploads_client_uses_configured_region(monkeypatch) -> None:
    # Reloading the module re-runs the module-level Minio(...) construction
    # with the patched setting, proving the region is read from config (a
    # hardcoded "garage" would not become "test-region-xyz").
    monkeypatch.setattr(settings, "GARAGE_REGION", "test-region-xyz")
    from app.api.routes import uploads

    importlib.reload(uploads)
    try:
        assert uploads.garage_client._base_url.region == "test-region-xyz"
    finally:
        monkeypatch.setattr(settings, "GARAGE_REGION", "garage")
        importlib.reload(uploads)


def test_tasks_client_uses_settings_region() -> None:
    from app import tasks

    assert tasks.garage_client._base_url.region == settings.GARAGE_REGION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose --env-file .env.dev exec backend python -m pytest tests/test_garage_region.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'GARAGE_REGION'` (and the default/reload assertions error out).

- [ ] **Step 3: Add the setting**

In `backend/app/core/config.py`, add the field immediately after `GARAGE_USE_TLS: bool = True` (line 62):

```python
    GARAGE_USE_TLS: bool = True
    # SigV4 credential-scope region. Default "garage" preserves Garage(dev)
    # and Minio(test) behaviour; OVH prod sets this to "gra" (lowercase —
    # the S3 signature region, distinct from the uppercase "GRA" OVH API
    # region). A mismatch against the bucket's region yields
    # SignatureDoesNotMatch on OVH.
    GARAGE_REGION: str = "garage"
```

- [ ] **Step 4: Wire it into the upload route client**

In `backend/app/api/routes/uploads.py`, change the `garage_client` construction (line 25):

```python
garage_client = Minio(
    endpoint=settings.GARAGE_ENDPOINT,
    access_key=settings.GARAGE_KEY_ID,
    secret_key=settings.GARAGE_SECRET,
    secure=settings.GARAGE_USE_TLS,
    region=settings.GARAGE_REGION,
)
```

- [ ] **Step 5: Wire it into the worker task client**

In `backend/app/tasks.py`, change the `garage_client` construction (line 48):

```python
garage_client = Minio(
    endpoint=settings.GARAGE_ENDPOINT,
    access_key=settings.GARAGE_KEY_ID,
    secret_key=settings.GARAGE_SECRET,
    secure=settings.GARAGE_USE_TLS,
    region=settings.GARAGE_REGION,
)
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `docker compose --env-file .env.dev exec backend python -m pytest tests/test_garage_region.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Run the existing upload suite + lint to confirm no regression**

Run: `docker compose --env-file .env.dev exec backend python -m pytest tests/api/routes/test_uploads.py -v`
Expected: PASS (existing tests unchanged).
Run: `docker compose --env-file .env.dev exec backend bash scripts/lint.sh`
Expected: `mypy app`, `ruff check app`, `ruff format app --check` all clean (exit 0).

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/config.py backend/app/api/routes/uploads.py backend/app/tasks.py backend/tests/test_garage_region.py
git commit -m "feat(storage): make S3 region configurable via GARAGE_REGION"
```

---

## Phase 2 — Environment templates

### Task 2: Add `GARAGE_REGION`/`GARAGE_USE_TLS`/`EMAIL` to tracked templates; document local prod scrub

**Files:**
- Modify: `.env.example` (tracked)
- Modify: `.env.test` (tracked)
- Modify (local, gitignored — instructions only): `.env.dev`, `.env.prod`

**Interfaces:**
- Produces: `GARAGE_REGION`, `GARAGE_USE_TLS`, `EMAIL` documented in `.env.example`; `GARAGE_REGION=garage` in `.env.test`. Consumed by Task 9 (cloud-init env render mirrors `.env.example`'s keys) and Task 4 (Traefik reads `${EMAIL}`).

- [ ] **Step 1: Add the new keys to `.env.example`**

In `.env.example`, in the object-storage block (after the `GARAGE_SECRET=changethis` line, ~line 59), add:

```bash
# SigV4 region for the S3 endpoint. "garage" for self-hosted Garage / Minio;
# set to the bucket's lowercase region for a cloud provider (OVH GRA => "gra").
GARAGE_REGION=garage
# Whether the S3 endpoint is HTTPS. True for cloud providers; False for a
# plain-HTTP local Minio.
GARAGE_USE_TLS=True
```

And in the Domain block (after `DOMAIN=localhost`, ~line 11) add the ACME email used by the prod Traefik edge:

```bash
# Let's Encrypt registration email — used by the production Traefik edge's
# ACME resolver (docker-compose.prod.yml). Unused in local dev (no proxy).
EMAIL=changethis
```

- [ ] **Step 2: Add `GARAGE_REGION` to `.env.test`**

In `.env.test`, in the object-storage block (after `GARAGE_USE_TLS=False`, ~line 43) add:

```bash
GARAGE_REGION=garage
```

(`.env.test` keeps `GARAGE_USE_TLS=False` — the in-stack Minio is plain HTTP and lenient on region.)

- [ ] **Step 3: Verify the tracked templates parse and keys are present**

Run:
```bash
grep -n "GARAGE_REGION\|GARAGE_USE_TLS\|^EMAIL=" .env.example .env.test
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config >/dev/null && echo "compose-config OK"
```
Expected: `GARAGE_REGION` present in both files, `GARAGE_USE_TLS`/`EMAIL` present in `.env.example`; `compose-config OK`.

- [ ] **Step 4: Update local (gitignored) env files — not a repo change**

These files are gitignored; edit them on the working machine so local dev/integration keep working. They will NOT appear in `git status`.

In local `.env.dev`, in the object-storage block add:
```bash
GARAGE_REGION=garage
```

In local `.env.prod`: add the production object-storage + ACME values and **scrub the live secrets to placeholders** (the real values are compromised and are replaced by Terraform-generated ones on deploy; the rendered `/opt/perchpub/.env.prod` on the box supersedes this file). Set:
```bash
EMAIL=changethis
SECRET_KEY=changethis
FIRST_SUPERUSER_PASSWORD=changethis
ENROLLMENT_HMAC_KEY_HEX=changethis
POSTGRES_PASSWORD=changethis
STEP_CA_ADMIN_PASSWORD=changethis
GARAGE_ENDPOINT=s3.gra.io.cloud.ovh.net
GARAGE_USE_TLS=True
GARAGE_REGION=gra
GARAGE_KEY_ID=changethis
GARAGE_SECRET=changethis
```

- [ ] **Step 5: Commit (tracked files only)**

```bash
git add .env.example .env.test
git commit -m "chore(env): document GARAGE_REGION/GARAGE_USE_TLS/EMAIL; GARAGE_REGION in .env.test"
```

(Local `.env.dev`/`.env.prod` are gitignored — nothing to add for them.)

---

## Phase 3 — Traefik edge + station mTLS (Compose)

### Task 3: Traefik file-provider dynamic config (mTLS tls.options + passTLSClientCert + router)

**Files:**
- Create: `deploy/traefik/dynamic/dynamic.yml`

**Interfaces:**
- Consumes: the `step-ca` named volume's `certs/` subdir mounted into Traefik at `/certs` (root + intermediate CA), and a backend reachable at `http://backend:8000` on the `default` network (both provided by Task 4).
- Produces: file-provider objects `tls.options.mtls`, `http.middlewares.pass-client-cert`, `http.routers.mtls-upload`, `http.services.backend-mtls`. The router emits header `X-Forwarded-Tls-Client-Cert` to the backend's `/api/v1/upload/` (consumed by `app/api/deps.py:get_current_station`).

- [ ] **Step 1: Create the dynamic config**

Create `deploy/traefik/dynamic/dynamic.yml`:

```yaml
# Traefik file-provider dynamic config (loaded via
# --providers.file.directory=/etc/traefik/dynamic). Carries ONLY the mTLS
# edge wiring. The https-redirect middleware is intentionally a @docker
# middleware (defined on the Traefik service in docker-compose.prod.yml) so
# the existing bare `middlewares=https-redirect` labels in docker-compose.yml
# resolve to https-redirect@docker.
#
# Hardcodes api.perchpub.net and the device-CA container paths. If DOMAIN
# ever changes, update the router rule below.

tls:
  options:
    mtls:
      # Stations MUST present a client certificate, verified against the
      # device CA. Reaching the backend's /api/v1/upload/ over any other
      # entrypoint leaves the cert header attacker-controlled — entrypoint
      # isolation is the trust boundary (see app/api/deps.py docstring).
      clientAuth:
        clientAuthType: RequireAndVerifyClientCert
        # Both files: device leaf certs are issued by the step-ca
        # intermediate (backend verifies verify_directly_issued_by(intermediate)
        # in deps.py); including the root lets Traefik build the full chain
        # whether or not the station presents the intermediate in the
        # handshake. VERIFY at first apply: if the handshake fails with
        # "unknown certificate authority", confirm which CA actually signs
        # device leaves and adjust this list (see Task 3 Step 4).
        caFiles:
          - /certs/root_ca.crt
          - /certs/intermediate_ca.crt
      minVersion: VersionTLS12

http:
  middlewares:
    pass-client-cert:
      # pem: true emits the verified leaf as X-Forwarded-Tls-Client-Cert,
      # URL-encoded with the PEM armor stripped. The backend decodes with
      # urllib.parse.unquote (NOT unquote_plus) and re-attaches the armor —
      # contract documented in app/api/deps.py:113-127.
      passTLSClientCert:
        pem: true

  routers:
    mtls-upload:
      rule: "Host(`api.perchpub.net`) && PathPrefix(`/api/v1/upload/`)"
      entryPoints:
        - mtls
      service: backend-mtls
      middlewares:
        - pass-client-cert
      tls:
        certResolver: le
        options: mtls

  services:
    backend-mtls:
      loadBalancer:
        servers:
          - url: "http://backend:8000"
```

- [ ] **Step 2: Validate YAML syntax**

Run: `docker run --rm -v "$PWD/deploy/traefik/dynamic:/d:ro" mikefarah/yq:latest 'deploy/traefik/dynamic/dynamic.yml' < /dev/null >/dev/null 2>&1 || python3 -c "import yaml,sys; yaml.safe_load(open('deploy/traefik/dynamic/dynamic.yml')); print('yaml OK')"`
Expected: `yaml OK` (the python fallback parses the file).

- [ ] **Step 3: Cross-check the header contract against the backend decoder**

Read `backend/app/api/deps.py:113-152` and confirm three things hold for `passTLSClientCert.pem=true`:
  1. Header key is `X-Forwarded-Tls-Client-Cert` (== `settings.MTLS_CLIENT_CERT_HEADER`).
  2. Backend uses `urllib.parse.unquote` (handles `%0A` newlines; leaves `+` literal).
  3. Backend re-attaches `-----BEGIN/END CERTIFICATE-----` when absent (Traefik strips the armor).
Also read `backend/tests/integration/test_compose_smoke.py:99-108` — it URL-encodes a full PEM (armor included) and the backend accepts it, proving the re-attach path. Both armored and stripped forms are accepted. No code change needed; this step is the documented §14 encoding verification.

Expected: all three confirmed. If any drift is found, STOP and reconcile before Task 4.

- [ ] **Step 4: Note the caFiles verification for apply-time**

Add a one-line reminder to the Task 13 README runbook smoke test: *"If the mTLS upload fails the TLS handshake (`tls: unknown certificate authority`), the device leaf chains differently than assumed — inspect `step-ca` `certs/` and adjust `dynamic.yml` `caFiles`."* (This is a doc note; the actual fix only matters at apply.)

- [ ] **Step 5: Commit**

```bash
git add deploy/traefik/dynamic/dynamic.yml
git commit -m "feat(edge): add Traefik mTLS dynamic config for station uploads"
```

---

### Task 4: Production Compose overlay (`docker-compose.prod.yml`)

**Files:**
- Create: `docker-compose.prod.yml`

**Interfaces:**
- Consumes: `deploy/traefik/dynamic/` (Task 3); env vars `DOMAIN`, `STACK_NAME`, `EMAIL` (Task 2 / Task 9 render); the `step-ca` named volume.
- Produces: an in-stack `traefik` service (entrypoints `http:80`, `https:443`, `mtls:8443`); `https-redirect@docker` middleware; `traefik-public` network pinned to `name: traefik-public`; `pgdata`/`redis`/`step-ca` named volumes bound under `/mnt/perchpub-data`. Brought up with `-f docker-compose.yml -f docker-compose.prod.yml`. Consumed by Task 9 (cloud-init compose-up) and Task 14 (docs).

- [ ] **Step 1: Create the overlay**

Create `docker-compose.prod.yml`:

```yaml
# Production overlay — in-stack Traefik edge + block-volume binds.
# Bring the stack up with:
#   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build
#
# Supersedes the standalone docker-compose.traefik.yml (removed): a single
# host lets Traefik mount step-ca's device CA over the shared step-ca volume
# and enforce station mTLS on :8443.
services:

  traefik:
    image: traefik:3.1
    restart: always
    networks:
      - traefik-public
      - default
    ports:
      - "80:80"
      - "443:443"
      - "8443:8443"
    depends_on:
      # Start after step-ca + provisioner-init have populated certs/ (backend
      # gates on step-ca-provisioner-init completing); the file provider reads
      # /certs/*.crt at load time.
      backend:
        condition: service_started
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --providers.docker.network=traefik-public
      - --providers.file.directory=/etc/traefik/dynamic
      - --providers.file.watch=true
      - --entrypoints.http.address=:80
      - --entrypoints.https.address=:443
      - --entrypoints.mtls.address=:8443
      - --certificatesresolvers.le.acme.email=${EMAIL?Variable not set}
      - --certificatesresolvers.le.acme.storage=/certificates/acme.json
      - --certificatesresolvers.le.acme.tlschallenge=true
      - --accesslog
      - --log
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik-certificates:/certificates
      - ./deploy/traefik/dynamic:/etc/traefik/dynamic:ro
      # Device CA (root + intermediate) for the mtls clientAuth, read-only
      # from the shared step-ca volume's certs/ subpath.
      - type: volume
        source: step-ca
        target: /certs
        read_only: true
        volume:
          subpath: certs
    labels:
      # Enable label parsing on this container so the @docker https-redirect
      # middleware below is registered. No router is defined for Traefik
      # itself (no dashboard exposed in prod).
      - traefik.enable=true
      - traefik.docker.network=traefik-public
      # https-redirect@docker — referenced bare by the backend/adminer/frontend
      # http routers in docker-compose.yml. Ported from the old standalone
      # docker-compose.traefik.yml.
      - traefik.http.middlewares.https-redirect.redirectscheme.scheme=https
      - traefik.http.middlewares.https-redirect.redirectscheme.permanent=true

volumes:
  traefik-certificates:
  # Bind the stateful named volumes to the attached block volume so Postgres
  # data and the step-ca root survive instance rebuild/replacement (§9).
  # cloud-init creates /mnt/perchpub-data/{pgdata,redis,step-ca} before up.
  pgdata:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/perchpub-data/pgdata
  redis:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/perchpub-data/redis
  step-ca:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/perchpub-data/step-ca

networks:
  # Pin the name so the existing `traefik.docker.network=traefik-public`
  # labels resolve (base compose declares this external: true).
  traefik-public:
    external: false
    name: traefik-public
```

- [ ] **Step 2: Validate the merged prod compose parses**

The bind `device:` paths don't need to exist for `config` to parse. Run with a throwaway env that supplies the required `${VAR}` substitutions:

```bash
docker compose --env-file .env.example \
  -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null && echo "prod-compose OK"
```
Expected: `prod-compose OK`. (`.env.example` supplies `DOMAIN`, `STACK_NAME`, `EMAIL`, `DOCKER_IMAGE_*`, etc. — enough to satisfy parse-time substitution. If `DOCKER_IMAGE_BACKEND`/`TAG` cause errors, export `TAG=latest` for the check.)

- [ ] **Step 3: Confirm the three entrypoints and the network pin**

Run:
```bash
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.prod.yml config \
  | grep -E "8443|traefik-public|/etc/traefik/dynamic|mtls.address"
```
Expected: shows `:8443`, the `mtls` entrypoint, the dynamic mount, and `name: traefik-public`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "feat(edge): in-stack Traefik prod overlay with http/https/mtls + volume binds"
```

---

## Phase 4 — Terraform infrastructure

> **Toolchain prerequisite for Phase 4:** install Terraform (`>= 1.6`) and `shellcheck` locally (none are on PATH). All `terraform` commands run from `deploy/terraform/`. `terraform validate` requires a one-time `terraform init -backend=false` (downloads providers — needs network once; no OVH/OpenStack credentials needed for `fmt`/`validate`/`init`). **No `apply` in this plan** — apply needs real credentials + billing (Task 13 runbook).

### Task 5: Terraform scaffolding — providers, variables, tfvars example, gitignore

**Files:**
- Create: `deploy/terraform/providers.tf`, `deploy/terraform/variables.tf`, `deploy/terraform/terraform.tfvars.example`, `deploy/terraform/.gitignore`

**Interfaces:**
- Produces: provider config (`ovh`, `openstack`, `random`); input variables consumed by every later TF task — `ovh_cloud_project_id`, `region` (default `"GRA"`), `flavor_name` (default `"b3-8"`), `image_name` (default `"Debian 12"`), `domain` (default `"perchpub.net"`), `owner_email`, `ssh_pubkey`, `ssh_allowed_cidr` (default `"0.0.0.0/0"`), `repo_url` (default the public GitHub URL), `volume_size_gb` (default `40`), `bucket_name` (default `"perchpub-bucket"`).

- [ ] **Step 1: Create `providers.tf`**

```hcl
terraform {
  required_version = ">= 1.6"

  required_providers {
    ovh = {
      source  = "ovh/ovh"
      version = "~> 2.0"
    }
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# OVH API credentials come from env vars (OVH_ENDPOINT, OVH_APPLICATION_KEY,
# OVH_APPLICATION_SECRET, OVH_CONSUMER_KEY) — see README bootstrap. Endpoint
# pinned to the EU region.
provider "ovh" {
  endpoint = "ovh-eu"
}

# OpenStack auth comes from a sourced openrc / clouds.yaml (OS_* env vars) —
# see README bootstrap.
provider "openstack" {}

provider "random" {}
```

- [ ] **Step 2: Create `variables.tf`**

```hcl
variable "ovh_cloud_project_id" {
  description = "OVH Public Cloud project ID (service_name)."
  type        = string
}

variable "region" {
  description = "OVH region (API casing, uppercase). EU default GRA."
  type        = string
  default     = "GRA"
}

variable "flavor_name" {
  description = "OpenStack flavor for the instance."
  type        = string
  default     = "b3-8"
}

variable "image_name" {
  description = "OpenStack image name."
  type        = string
  default     = "Debian 12"
}

variable "domain" {
  description = "Root domain hosted in the OVH DNS zone."
  type        = string
  default     = "perchpub.net"
}

variable "owner_email" {
  description = "Owner email: FIRST_SUPERUSER and Let's Encrypt ACME address."
  type        = string
}

variable "ssh_pubkey" {
  description = "SSH public key authorized on the instance."
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to reach SSH (22). WARNING: 0.0.0.0/0 exposes SSH to the world — narrow to your IP/32 in production."
  type        = string
  default     = "0.0.0.0/0"
}

variable "repo_url" {
  description = "Public git URL cloned on the box and built with compose."
  type        = string
  default     = "https://github.com/teschmitt/perchpub.git"
}

variable "volume_size_gb" {
  description = "Block volume size (GB) mounted at /mnt/perchpub-data."
  type        = number
  default     = 40
}

variable "bucket_name" {
  description = "OVH Object Storage (S3) bucket for media + the TF-Lite model."
  type        = string
  default     = "perchpub-bucket"
}
```

> Note: confirm the `repo_url` default matches the project's actual public GitHub path before deploy; override in tfvars if different.

- [ ] **Step 3: Create `terraform.tfvars.example`**

```hcl
# Copy to terraform.tfvars (gitignored) and fill in.
ovh_cloud_project_id = "0123456789abcdef0123456789abcdef"
owner_email          = "t.e.schmitt@posteo.de"
ssh_pubkey           = "ssh-ed25519 AAAA... you@host"

# Recommended: narrow SSH to your own address.
# ssh_allowed_cidr   = "203.0.113.4/32"

# Optional overrides (defaults shown):
# region          = "GRA"
# flavor_name     = "b3-8"
# image_name      = "Debian 12"
# domain          = "perchpub.net"
# repo_url        = "https://github.com/teschmitt/perchpub.git"
# volume_size_gb  = 40
# bucket_name     = "perchpub-bucket"
```

- [ ] **Step 4: Create `.gitignore`**

```gitignore
# Local, gitignored TF state (D5) and anything secret-bearing.
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl
crash.log
crash.*.log
# tfvars hold the project id / ssh key — keep only the example.
*.tfvars
!*.tfvars.example
override.tf
override.tf.json
*_override.tf
*_override.tf.json
```

- [ ] **Step 5: Init + validate + fmt**

Run:
```bash
cd deploy/terraform
terraform init -backend=false
terraform fmt -check
terraform validate
```
Expected: `init` succeeds (providers downloaded); `fmt -check` exits 0 (no diff); `validate` → `Success! The configuration is valid.`

- [ ] **Step 6: Commit**

```bash
git add deploy/terraform/providers.tf deploy/terraform/variables.tf deploy/terraform/terraform.tfvars.example deploy/terraform/.gitignore
git commit -m "feat(deploy): terraform scaffolding (providers, variables, gitignore)"
```

---

### Task 6: Generated secrets (`secrets.tf`)

**Files:**
- Create: `deploy/terraform/secrets.tf`

**Interfaces:**
- Produces: `random_password.secret_key`, `random_password.postgres_password`, `random_password.first_superuser_password`, `random_password.step_ca_admin_password` (each `.result`), and `random_id.enrollment_hmac` (`.hex` → 64 hex chars). Consumed by Task 8 (cloud-init `templatefile` vars) via Task 9. The special-char set is restricted to `-_` so the values are safe to drop into a `.env` file unquoted (no `$`, `"`, `\`, spaces).

- [ ] **Step 1: Create `secrets.tf`**

```hcl
# App secrets generated by Terraform and rendered onto the box (D3). They
# live only in the gitignored local state + on the instance. override_special
# = "-_" keeps every value safe to write into .env.prod unquoted (no $, ",
# \, backticks or whitespace that compose/bash would choke on).

resource "random_password" "secret_key" {
  length           = 43
  special          = true
  override_special = "-_"
}

resource "random_password" "postgres_password" {
  length           = 32
  special          = true
  override_special = "-_"
}

resource "random_password" "first_superuser_password" {
  length           = 24
  special          = true
  override_special = "-_"
}

resource "random_password" "step_ca_admin_password" {
  length           = 32
  special          = true
  override_special = "-_"
}

# ENROLLMENT_HMAC_KEY_HEX must be exactly 64 hex chars (32 bytes) — config.py
# validates length + hex. random_id.hex of 32 bytes is exactly that.
resource "random_id" "enrollment_hmac" {
  byte_length = 32
}
```

- [ ] **Step 2: Validate + fmt**

Run: `cd deploy/terraform && terraform fmt -check && terraform validate`
Expected: `fmt` clean; `validate` → `Success!`

- [ ] **Step 3: Commit**

```bash
git add deploy/terraform/secrets.tf
git commit -m "feat(deploy): terraform-generated app secrets"
```

---

### Task 7: OVH Object Storage bucket + scoped S3 credentials (`storage.tf`)

**Files:**
- Create: `deploy/terraform/storage.tf`

**Interfaces:**
- Produces: `ovh_cloud_project_storage.media` (bucket, type `standard`, region `var.region`); `ovh_cloud_project_user_s3_credential.media` exposing `.access_key_id` + `.secret_access_key`. Consumed by Task 8/9 (rendered `GARAGE_KEY_ID`/`GARAGE_SECRET`) and Task 12 (outputs).

> **Schema pin (D8/§14):** the OVH provider's `ovh_cloud_project_storage` / S3-user / credential / policy argument names and the bucket-type field MUST be confirmed against the installed provider schema, using Mastodon's [`terraform-ovh-s3`](https://github.com/mastodon/terraform-ovh-s3) module as the reference pattern. The HCL below is the reference shape; `terraform validate` (Step 2) catches any argument-name drift — fix names against the schema before moving on.

- [ ] **Step 1: Create `storage.tf`**

```hcl
# Object storage for media + the TF-Lite model (D8: type "standard"; the
# high_performance class uses EXPRESS_ONEZONE which breaks Minio's default
# upload path). Pattern mirrors mastodon/terraform-ovh-s3.

# A dedicated Public Cloud user holding the S3 credential.
resource "ovh_cloud_project_user" "s3" {
  service_name = var.ovh_cloud_project_id
  description  = "perchpub-s3-${lower(var.region)}"
  role_names   = ["objectstore_operator"]
}

# S3-compatible access key / secret for the user above.
resource "ovh_cloud_project_user_s3_credential" "media" {
  service_name = var.ovh_cloud_project_id
  user_id      = ovh_cloud_project_user.s3.id
}

# The bucket itself. VERIFY argument names (region_name vs region, the
# standard/high_performance selector) against `terraform providers schema
# -json | jq '.provider_schemas[].resource_schemas.ovh_cloud_project_storage'`.
resource "ovh_cloud_project_storage" "media" {
  service_name = var.ovh_cloud_project_id
  region_name  = var.region
  name         = var.bucket_name

  versioning {
    status = "disabled"
  }
}

# Least-privilege policy scoping the user to this one bucket.
resource "ovh_cloud_project_user_s3_policy" "media" {
  service_name = var.ovh_cloud_project_id
  user_id      = ovh_cloud_project_user.s3.id
  policy = jsonencode({
    statements = [
      {
        sid       = "perchpub-bucket-rw"
        effect    = "allow"
        action    = ["s3:*"]
        resource  = [
          "arn:aws:s3:::${var.bucket_name}",
          "arn:aws:s3:::${var.bucket_name}/*",
        ]
      }
    ]
  })
}
```

- [ ] **Step 2: Validate + fmt; pin schema if validate complains**

Run: `cd deploy/terraform && terraform fmt -check && terraform validate`
Expected: `Success!`. If validate reports an unknown argument/block (e.g. `region_name`, `versioning`, the policy shape), run `terraform providers schema -json` and correct the field names to match, then re-run until valid.

- [ ] **Step 3: Commit**

```bash
git add deploy/terraform/storage.tf
git commit -m "feat(deploy): OVH S3 bucket + scoped credentials"
```

---

### Task 8: cloud-init template (`cloud-init.yaml.tftpl`)

**Files:**
- Create: `deploy/terraform/cloud-init.yaml.tftpl`

**Interfaces:**
- Consumes (templatefile vars, passed by Task 10's `openstack_compute_instance_v2.user_data`): `domain`, `owner_email`, `repo_url`, `secret_key`, `postgres_password`, `first_superuser_password`, `step_ca_admin_password`, `enrollment_hmac_hex`, `s3_endpoint`, `s3_region`, `s3_bucket`, `s3_key_id`, `s3_secret`, `ssh_allowed_cidr`.
- Produces: a cloud-config that installs Docker, mounts the block volume at `/mnt/perchpub-data` (with `pgdata`/`redis`/`step-ca` subdirs), configures `nftables` (22/80/443/8443), clones `repo_url` to `/opt/perchpub`, renders `/opt/perchpub/.env.prod`, and runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.

> **Terraform templating gotcha:** `templatefile` interpolates every `${...}`. TF vars use `${var_name}`; **all shell `${VAR}` expansions must be escaped as `$${VAR}`** to survive rendering. Shell `$(...)` command substitution is NOT intercepted and is left as-is. The `.env.prod` heredoc body contains only literal values (TF-interpolated), no `${}`.

- [ ] **Step 1: Create `cloud-init.yaml.tftpl`**

```yaml
#cloud-config
package_update: true
package_upgrade: false

write_files:
  # nftables ruleset — host firewall is the ingress enforcement mechanism
  # (OVH security groups do not reliably filter Ext-Net ingress, §5).
  - path: /etc/nftables.conf
    permissions: "0755"
    content: |
      #!/usr/sbin/nft -f
      flush ruleset
      table inet filter {
        chain input {
          type filter hook input priority 0; policy drop;
          ct state established,related accept
          iif "lo" accept
          ip protocol icmp accept
          ip6 nexthdr ipv6-icmp accept
          tcp dport 22 ip saddr ${ssh_allowed_cidr} accept
          tcp dport { 80, 443, 8443 } accept
        }
        chain forward { type filter hook forward priority 0; policy drop; }
        chain output  { type filter hook output  priority 0; policy accept; }
      }

runcmd:
  # --- Docker install (official convenience script) ---
  - curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  - sh /tmp/get-docker.sh
  - systemctl enable --now docker

  # --- Firewall ---
  - systemctl enable --now nftables
  - nft -f /etc/nftables.conf

  # --- Block volume: find the unmounted data disk, format once, mount ---
  - |
    set -euxo pipefail
    # The attached volume is the block device with no mountpoint and no
    # partitions that is not the root disk. VERIFY at first apply with lsblk.
    DEV=$(lsblk -dpno NAME,TYPE,MOUNTPOINT | awk '$2=="disk" && $3==""{print $1}' | grep -v -E "$(findmnt -no SOURCE / | sed 's/[0-9]*$//')" | head -n1)
    if [ -z "$${DEV}" ]; then echo "no data disk found" >&2; exit 1; fi
    if ! blkid "$${DEV}"; then mkfs.ext4 -F "$${DEV}"; fi
    mkdir -p /mnt/perchpub-data
    grep -q "/mnt/perchpub-data" /etc/fstab || echo "$${DEV} /mnt/perchpub-data ext4 defaults,nofail 0 2" >> /etc/fstab
    mount -a
    mkdir -p /mnt/perchpub-data/pgdata /mnt/perchpub-data/redis /mnt/perchpub-data/step-ca

  # --- Clone repo + render env + bring the stack up ---
  - git clone ${repo_url} /opt/perchpub || (cd /opt/perchpub && git pull)
  - |
    cat > /opt/perchpub/.env.prod <<'ENVEOF'
    ENVIRONMENT=production
    DOMAIN=${domain}
    FRONTEND_HOST=https://dashboard.${domain}
    BACKEND_CORS_ORIGINS=https://${domain},https://dashboard.${domain}
    PROJECT_NAME=PerchPub
    STACK_NAME=perchpub

    EMAIL=${owner_email}
    FIRST_SUPERUSER=${owner_email}
    FIRST_SUPERUSER_PASSWORD=${first_superuser_password}
    SECRET_KEY=${secret_key}
    ENROLLMENT_HMAC_KEY_HEX=${enrollment_hmac_hex}

    POSTGRES_SERVER=localhost
    POSTGRES_PORT=5432
    POSTGRES_DB=app
    POSTGRES_USER=postgres
    POSTGRES_PASSWORD=${postgres_password}

    DOCKER_IMAGE_BACKEND=perchpub-api
    DOCKER_IMAGE_FRONTEND=perchpub-frontend
    TAG=latest

    GARAGE_BUCKET_NAME=${s3_bucket}
    GARAGE_ENDPOINT=${s3_endpoint}
    GARAGE_USE_TLS=True
    GARAGE_REGION=${s3_region}
    GARAGE_KEY_ID=${s3_key_id}
    GARAGE_SECRET=${s3_secret}

    CA_NAME=PerchPubCA
    STEP_CA_URL=https://step-ca:9000
    STEP_CA_PROVISIONER_NAME=backend-device-enrollment
    STEP_CA_ADMIN_PASSWORD=${step_ca_admin_password}
    STEP_CA_JWK_PATH=/home/step-ca/backend-provisioner.jwk

    CLASSIFICATION_MODEL_OBJECT_NAME=birdiary-v0.1/classify.tflite
    CLASSIFICATION_LABELS_OBJECT_NAME=birdiary-v0.1/labels.txt

    HUEY_CLIENT_NAME=perchpub
    HUEY_REDIS_HOST=redis
    HUEY_REDIS_PORT=6379
    ENVEOF
  - chmod 600 /opt/perchpub/.env.prod
  - |
    cd /opt/perchpub
    docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

> Note on `POSTGRES_SERVER=localhost`: `docker-compose.yml` overrides it to `db` for the `prestart`/`backend`/`worker` services, mirroring the existing `.env.prod` convention. Leave it `localhost` here.

- [ ] **Step 2: shellcheck the embedded shell**

The heavy shell is the volume-mount block. Extract and lint it (escape-stripped to the post-render form). Save the volume block to a temp file with `$${...}` reduced to `${...}` and run:

```bash
cat > /tmp/cloudinit-vol.sh <<'EOF'
set -euxo pipefail
DEV=$(lsblk -dpno NAME,TYPE,MOUNTPOINT | awk '$2=="disk" && $3==""{print $1}' | grep -v -E "$(findmnt -no SOURCE / | sed 's/[0-9]*$//')" | head -n1)
if [ -z "${DEV}" ]; then echo "no data disk found" >&2; exit 1; fi
if ! blkid "${DEV}"; then mkfs.ext4 -F "${DEV}"; fi
mkdir -p /mnt/perchpub-data
grep -q "/mnt/perchpub-data" /etc/fstab || echo "${DEV} /mnt/perchpub-data ext4 defaults,nofail 0 2" >> /etc/fstab
mount -a
mkdir -p /mnt/perchpub-data/pgdata /mnt/perchpub-data/redis /mnt/perchpub-data/step-ca
EOF
shellcheck /tmp/cloudinit-vol.sh && echo "shellcheck OK"
```
Expected: `shellcheck OK` (warnings about `mount -a`/`mkfs` are acceptable; no errors).

- [ ] **Step 3: Validate the template renders (no apply)**

Task 9 (`compute.tf`) wires the actual `templatefile` call and renders it via `terraform console`; for now, sanity-check that every shell `${VAR}` is escaped as `$${VAR}`. Use a negative lookbehind so the already-escaped `$${VAR}` forms do NOT false-positive (a plain `\$\{[A-Z_]+\}` regex would match the `${VAR}` substring inside `$${VAR}`):

```bash
# GNU grep (-P) negative lookbehind: flag ${UPPER} NOT preceded by another '$'.
grep -nP '(?<!\$)\$\{[A-Z_]+\}' deploy/terraform/cloud-init.yaml.tftpl \
  && echo "UNESCAPED shell var(s) above — escape to \$\${VAR}" \
  || echo "no unescaped shell vars (good)"
```
Expected: `no unescaped shell vars (good)` — the only single-`$` `${...}` remaining are TF template vars (lowercase: `${domain}`, `${secret_key}`, `${ssh_allowed_cidr}`, …), which this regex ignores. Any match is a real shell expansion that must become `$${VAR}`.

- [ ] **Step 4: Commit**

```bash
git add deploy/terraform/cloud-init.yaml.tftpl
git commit -m "feat(deploy): cloud-init (docker, volume, firewall, env render, compose up)"
```

---

### Task 9: Compute — keypair, volume, instance, attach, security group (`compute.tf`)

**Files:**
- Create: `deploy/terraform/compute.tf`

**Interfaces:**
- Consumes: `var.*` (Task 5), `random_*` (Task 6), `ovh_cloud_project_user_s3_credential.media` + `ovh_cloud_project_storage.media` (Task 7), `cloud-init.yaml.tftpl` (Task 8).
- Produces: `openstack_compute_instance_v2.app` with `.access_ip_v4` (consumed by Task 11 DNS + Task 12 outputs); the block volume + attachment; the egress security group.

> **Schema/region pin (§14):** confirm `image_name`/`flavor_name` exist in the chosen region (`openstack image list`, `openstack flavor list`), and that `Ext-Net` is the public network name. `terraform validate` checks HCL shape, not OVH-side existence.

- [ ] **Step 1: Create `compute.tf`**

```hcl
resource "openstack_compute_keypair_v2" "deploy" {
  name       = "perchpub-deploy"
  public_key = var.ssh_pubkey
}

# Egress hygiene + intent only — NOT trusted for ingress (§5). Host nftables
# (cloud-init) is the ingress enforcement mechanism.
resource "openstack_networking_secgroup_v2" "egress" {
  name        = "perchpub-egress"
  description = "Egress hygiene/intent only; ingress enforced host-side via nftables."
}

resource "openstack_blockstorage_volume_v3" "data" {
  name = "perchpub-data"
  size = var.volume_size_gb
}

resource "openstack_compute_instance_v2" "app" {
  name            = "perchpub"
  image_name      = var.image_name
  flavor_name     = var.flavor_name
  key_pair        = openstack_compute_keypair_v2.deploy.name
  security_groups = [openstack_networking_secgroup_v2.egress.name]

  network {
    name = "Ext-Net"
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    domain                   = var.domain
    owner_email              = var.owner_email
    repo_url                 = var.repo_url
    ssh_allowed_cidr         = var.ssh_allowed_cidr
    secret_key               = random_password.secret_key.result
    postgres_password        = random_password.postgres_password.result
    first_superuser_password = random_password.first_superuser_password.result
    step_ca_admin_password   = random_password.step_ca_admin_password.result
    enrollment_hmac_hex      = random_id.enrollment_hmac.hex
    s3_endpoint              = "s3.${lower(var.region)}.io.cloud.ovh.net"
    s3_region                = lower(var.region)
    s3_bucket                = var.bucket_name
    s3_key_id                = ovh_cloud_project_user_s3_credential.media.access_key_id
    s3_secret                = ovh_cloud_project_user_s3_credential.media.secret_access_key
  })
}

resource "openstack_compute_volume_attach_v2" "data" {
  instance_id = openstack_compute_instance_v2.app.id
  volume_id   = openstack_blockstorage_volume_v3.data.id
}
```

> Note: `s3_endpoint` is derived as `s3.<region>.io.cloud.ovh.net` (e.g. `s3.gra.io.cloud.ovh.net`). Confirm the exact hostname for the chosen region against OVH docs (§14) — adjust the interpolation if OVH's pattern differs.

- [ ] **Step 2: Validate + fmt; render the cloud-init to confirm templatefile vars line up**

Run:
```bash
cd deploy/terraform && terraform fmt -check && terraform validate
```
Expected: `Success!` — proves every `templatefile` var referenced in `cloud-init.yaml.tftpl` is supplied (TF errors on missing/extra template vars at validate? — if not caught by validate, the render below catches it).

Optionally render with placeholder values to eyeball the `.env.prod` body:
```bash
echo 'templatefile("${path.module}/cloud-init.yaml.tftpl", {domain="perchpub.net", owner_email="a@b.co", repo_url="x", ssh_allowed_cidr="0.0.0.0/0", secret_key="s", postgres_password="p", first_superuser_password="f", step_ca_admin_password="c", enrollment_hmac_hex="ab", s3_endpoint="s3.gra.io.cloud.ovh.net", s3_region="gra", s3_bucket="b", s3_key_id="k", s3_secret="x"})' | terraform console
```
Expected: prints the rendered cloud-config with the `.env.prod` heredoc filled in and no `Error:`.

- [ ] **Step 3: Commit**

```bash
git add deploy/terraform/compute.tf
git commit -m "feat(deploy): instance, block volume, attach, egress secgroup"
```

---

### Task 10: DNS — zone data source + A records (`dns.tf`)

**Files:**
- Create: `deploy/terraform/dns.tf`

**Interfaces:**
- Consumes: `var.domain`, `openstack_compute_instance_v2.app.access_ip_v4` (Task 9).
- Produces: A records `@`, `api`, `dashboard`, `adminer` → the instance IP, in the existing OVH zone.

> The OVH **DNS zone** is created once manually + Namecheap NS repointed (D2, Task 12 README). TF only manages records within it.

- [ ] **Step 1: Create `dns.tf`**

```hcl
data "ovh_domain_zone" "root" {
  name = var.domain
}

locals {
  # "" subdomain == apex (@).
  a_records = {
    apex      = ""
    api       = "api"
    dashboard = "dashboard"
    adminer   = "adminer"
  }
}

resource "ovh_domain_zone_record" "a" {
  for_each = local.a_records

  zone      = data.ovh_domain_zone.root.name
  subdomain = each.value
  fieldtype = "A"
  ttl       = 600
  target    = openstack_compute_instance_v2.app.access_ip_v4
}
```

- [ ] **Step 2: Validate + fmt**

Run: `cd deploy/terraform && terraform fmt -check && terraform validate`
Expected: `Success!`

- [ ] **Step 3: Commit**

```bash
git add deploy/terraform/dns.tf
git commit -m "feat(deploy): OVH DNS A records for api/dashboard/adminer/apex"
```

---

### Task 11: Outputs (`outputs.tf`)

**Files:**
- Create: `deploy/terraform/outputs.tf`

**Interfaces:**
- Consumes: instance IP (Task 9), S3 storage/cred (Task 7), zone (Task 10).
- Produces: human-facing outputs — public IP, S3 endpoint/bucket, and the NS-repoint reminder.

- [ ] **Step 1: Create `outputs.tf`**

```hcl
output "instance_public_ip" {
  description = "Public IP of the PerchPub instance (point DNS / SSH here)."
  value       = openstack_compute_instance_v2.app.access_ip_v4
}

output "s3_endpoint" {
  description = "OVH S3 endpoint the app uses (GARAGE_ENDPOINT)."
  value       = "s3.${lower(var.region)}.io.cloud.ovh.net"
}

output "s3_bucket" {
  description = "Object storage bucket name (GARAGE_BUCKET_NAME)."
  value       = ovh_cloud_project_storage.media.name
}

output "s3_access_key_id" {
  description = "Scoped S3 access key id."
  value       = ovh_cloud_project_user_s3_credential.media.access_key_id
}

output "s3_secret_access_key" {
  description = "Scoped S3 secret access key."
  value       = ovh_cloud_project_user_s3_credential.media.secret_access_key
  sensitive   = true
}

output "ns_repoint_reminder" {
  description = "One-time manual step (D2)."
  value       = "Ensure the OVH DNS zone for ${var.domain} exists and Namecheap NS are repointed to OVH's nameservers (ns##.ovh.net / dns##.ovh.net). TF manages records, not registrar NS."
}
```

- [ ] **Step 2: Validate + fmt**

Run: `cd deploy/terraform && terraform fmt -check && terraform validate`
Expected: `Success!`

- [ ] **Step 3: Commit**

```bash
git add deploy/terraform/outputs.tf
git commit -m "feat(deploy): terraform outputs (IP, S3, NS reminder)"
```

---

### Task 12: Terraform README (bootstrap + apply runbook + smoke test)

**Files:**
- Create: `deploy/terraform/README.md`

**Interfaces:**
- Consumes: everything above. Produces the operator runbook (§11 bootstrap + §13 smoke test).

- [ ] **Step 1: Write `deploy/terraform/README.md`**

Include these sections verbatim in intent (fill with the commands already used in this plan):

1. **Prerequisites:** Terraform `>= 1.6`, an OVH account with a Public Cloud project + billing, an OVH API credential (application key/secret/consumer key), OpenStack `clouds.yaml`/openrc.
2. **One-time manual bootstrap (D2 / §11):**
   - Create OVH API credentials; export `OVH_ENDPOINT=ovh-eu`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY`.
   - Copy the Public Cloud project's `service_name` → `ovh_cloud_project_id` in tfvars.
   - Source the OpenStack openrc / configure `clouds.yaml` (sets `OS_*`).
   - Create the OVH **DNS zone** for `perchpub.net` (Control Panel/API) and **repoint Namecheap NS** to OVH's nameservers; wait for propagation (`dig NS perchpub.net`).
   - `cp terraform.tfvars.example terraform.tfvars` and fill in.
3. **Apply:**
   ```bash
   cd deploy/terraform
   terraform init
   terraform plan
   terraform apply
   ```
4. **Post-apply smoke test (§13):**
   1. `curl -sSf https://api.perchpub.net/docs >/dev/null` and `https://dashboard.perchpub.net` resolve with valid Let's Encrypt certs.
   2. First-superuser login works (seeded by `prestart`): `POST https://api.perchpub.net/api/v1/login/access-token` with `FIRST_SUPERUSER` / generated password (read from the box's `/opt/perchpub/.env.prod` or `terraform output`).
   3. Enroll a station; perform an mTLS upload to `https://api.perchpub.net:8443/api/v1/upload/` with the client cert; confirm a classification task runs (worker) and the object lands in the OVH bucket.
   4. Reboot/replace the instance; confirm Postgres + step-ca state persist from the block volume.
   - **caFiles note (from Task 3):** if the mTLS upload fails the TLS handshake (`tls: unknown certificate authority`), inspect `step-ca` `certs/` and adjust `deploy/traefik/dynamic/dynamic.yml` `caFiles`.
5. **Notes:** state is local + gitignored (D5); `terraform destroy` tears the instance/volume/DNS/bucket down (media in the bucket is deleted — back up first).

- [ ] **Step 2: Spell-check / link sanity (manual read)**

Read the file; confirm every command matches the resource names and variables defined in Tasks 5–11 (e.g. `terraform output instance_public_ip`).

- [ ] **Step 3: Commit**

```bash
git add deploy/terraform/README.md
git commit -m "docs(deploy): terraform bootstrap + apply runbook + smoke test"
```

---

## Phase 5 — Documentation & cleanup

### Task 13: Rewrite deployment docs; remove the standalone Traefik file

**Files:**
- Modify: `README.md` (the "Deploying a server" section, lines 143-152, and the dev "Object storage is external … Hetzner" line ~91)
- Modify: `deployment.md` (replace the manual-host / standalone-Traefik / Hetzner narrative with the Terraform runbook pointer; keep step-ca + secret-generation guidance)
- Modify: `CLAUDE.md` (deployment notes / commands referencing prod)
- Modify: `docker-compose.override.yml` (comment lines 5-9 referencing `docker-compose.traefik.yml`)
- Remove: `docker-compose.traefik.yml`

**Interfaces:**
- Consumes: the new `deploy/terraform/README.md`, `docker-compose.prod.yml`, `GARAGE_REGION`. Produces: docs aligned with the Terraform/OVH model.

- [ ] **Step 1: Rewrite `README.md` "Deploying a server"**

Replace lines 143-152 with a section that points to `deploy/terraform/README.md` and states the new shape: single OVH instance via Terraform, in-stack Traefik with HTTPS (`:443`) + station mTLS (`:8443`), media + model in OVH Object Storage, secrets generated by Terraform. Drop the Hetzner Object Storage mention in the dev section (~line 91) — note the model is fetched from S3 (Garage in dev / OVH in prod). Keep the "migrations apply via prestart" note.

- [ ] **Step 2: Rewrite `deployment.md`**

Replace the "Public Traefik" (standalone rsync/`docker network create traefik-public`) and "Deploy with Docker Compose" / GitHub-Actions-swarm sections with:
   - A short "Provisioned by Terraform → see `deploy/terraform/README.md`" pointer for the infra + first deploy.
   - Keep the "Setting up the CA for mTLS" + "step-ca first boot" + "Generate secret keys" sections (still accurate; note that on a TF deploy the secrets are generated by Terraform and rendered into `/opt/perchpub/.env.prod`, so manual generation applies only to non-TF/manual deploys).
   - Update the prod compose command everywhere to `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d` (note the added `-f docker-compose.prod.yml`).
   - Update the "Production deployments target a single Linux host … fronted by Traefik" framing to "in-stack Traefik (`docker-compose.prod.yml`)" rather than a separately-deployed proxy.

- [ ] **Step 3: Update `CLAUDE.md`**

In the "No Traefik in dev (FU-11)" line and any prod-compose references, change the prod invocation to include `-f docker-compose.prod.yml`, and update the Open-questions/deploy notes to reflect that the prod-side mTLS edge now exists in-stack (closes the gap noted in memory: "station mTLS edge entrypoint missing"). Mention `GARAGE_REGION` in the Settings/Object-storage convention notes (region is now configurable; prod = `gra`).

- [ ] **Step 4: Update `docker-compose.override.yml` comment**

Replace the comment (lines 5-9) referencing `docker-compose.traefik.yml` with a reference to `docker-compose.prod.yml` (the prod overlay that now carries the in-stack Traefik).

- [ ] **Step 5: Remove `docker-compose.traefik.yml`**

Confirm no remaining references, then remove:
```bash
grep -rn "docker-compose.traefik" . --include="*.md" --include="*.yml" --include="*.yaml" --include="*.sh" | grep -v docs/superpowers
git rm docker-compose.traefik.yml
```
Expected: the grep returns no live references (only this plan / specs under `docs/superpowers`). If `scripts/deploy.sh` (legacy Docker Swarm) still references swarm/standalone Traefik, leave it but add a one-line `# LEGACY: superseded by deploy/terraform + docker-compose.prod.yml` comment at its top (out of scope to rewrite).

- [ ] **Step 6: Verify docs build / no broken intra-repo links**

Run:
```bash
grep -rn "docker-compose.traefik.yml" README.md deployment.md CLAUDE.md docker-compose.override.yml && echo "STILL REFERENCED (fix)" || echo "no stale traefik refs"
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null && echo "prod-compose still parses"
```
Expected: `no stale traefik refs`; `prod-compose still parses`.

- [ ] **Step 7: Commit**

```bash
git add README.md deployment.md CLAUDE.md docker-compose.override.yml
git rm docker-compose.traefik.yml
git commit -m "docs: switch deployment narrative to Terraform/OVH + in-stack Traefik; drop standalone traefik compose"
```

---

## Self-Review (performed against the spec)

**1. Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §2 D1 full single-host stack | Tasks 5–12 (TF) + Task 4 (compose-up via cloud-init) |
| §2 D2 DNS (zone data + records; manual NS repoint) | Task 10 + Task 12 (README bootstrap) |
| §2 D3 TF-generated secrets rendered on host | Task 6 + Task 8 |
| §2 D4 station mTLS in-stack Traefik | Tasks 3, 4 |
| §2 D5 local gitignored state | Task 5 (`.gitignore`) |
| §2 D6 clone + build on box | Task 8 (cloud-init `up -d --build`) |
| §2 D7 region knob default GRA | Task 5 (`var.region`) |
| §2 D8 bucket type `standard` | Task 7 |
| §3 architecture | Tasks 3,4,8,9 |
| §4 resource inventory | Tasks 5–11 |
| §5 firewall (nftables 22/80/443/8443; secgroup egress-only) | Task 8 + Task 9 |
| §6 secrets & `.env.prod` render | Task 8 (render) + Task 6 (secrets) + Task 2 (templates) + Spec-correction #1 |
| §7 Traefik + HTTPS + mTLS | Tasks 3, 4 |
| §8 configurable S3 region | Task 1 + Task 2 |
| §9 persistent storage mapping | Task 4 (binds) + Task 8 (mount) |
| §10 file layout `deploy/terraform/` | Tasks 5–12 |
| §11 one-time bootstrap | Task 12 |
| §12 repo changes summary | All tasks; Task 13 (traefik.yml fate + docs) |
| §13 testing & verification | Each task's verify steps + Task 12 smoke runbook |
| §14 risks / plan-time verifications | Task 3 (encoding + caFiles), Task 7 (OVH schema), Task 9 (endpoint/region casing, flavor/image, Ext-Net), Task 4 (traefik-public network) |
| §15 out of scope | Spec-correction #8 |

No gaps. The one spec item *reduced* in scope is the §6 "scrub committed `.env.prod` / git-history" — corrected to "tracked templates only; `.env.prod` was never committed" (Spec-correction #1), with the live working-tree secrets treated as compromised and rotated by TF.

**2. Placeholder scan:** No `TBD`/`add error handling`/`similar to Task N` placeholders. The two genuinely external-schema-dependent areas (OVH S3 resource args in Task 7; OVH S3 endpoint hostname/flavor/image in Task 9) carry concrete reference HCL **plus** an explicit `terraform validate` + provider-schema pin step — this is the verification the spec itself mandates (§14), not a hand-wave. `"changethis"` strings are intentional env placeholders matching the existing `.env.example` convention.

**3. Type/name consistency:** Verified across tasks — env-var names (`GARAGE_REGION`, `EMAIL`, `STEP_CA_ADMIN_PASSWORD`), file paths (`/mnt/perchpub-data`, `/opt/perchpub`, `deploy/traefik/dynamic/dynamic.yml`, `/certs`), the network name `traefik-public`, the header `X-Forwarded-Tls-Client-Cert`, the mtls port `8443`, and the minio region attribute `_base_url.region` all match between the code, the compose overlay, the dynamic config, and the cloud-init render. TF symbol names (`random_password.secret_key`, `ovh_cloud_project_user_s3_credential.media`, `openstack_compute_instance_v2.app.access_ip_v4`, `ovh_cloud_project_storage.media.name`) are consistent between `compute.tf`, `dns.tf`, `outputs.tf`, and the cloud-init templatefile vars.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-terraform-ovh-deployment.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Best here because Phase 1 (app change, full TDD) and Phases 3–4 (compose + IaC, validate-gated) have clean per-task boundaries.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
