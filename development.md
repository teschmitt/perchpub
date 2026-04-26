# PerchPub - Development

This file complements [README.md](./README.md) (which has the bird's-eye view) and [backend/README.md](./backend/README.md) (backend specifics). It covers the day-to-day local-dev workflow: starting the stack, swapping a service for a host process, env-file conventions, and the pre-commit hook.

## Starting the stack

Every `docker compose` invocation in dev needs `--env-file .env.dev` — the backend's `Settings` does not auto-load anything. Easiest is to alias it:

```bash
alias dc='docker compose --env-file .env.dev'
dc watch         # start with file-sync; rebuilds on pyproject changes
dc up -d         # start without watch (faster, no live reload)
dc logs -f backend
```

Per-service direct URLs:

| Service | URL |
| --- | --- |
| Backend API + OpenAPI | <http://localhost:8000> / <http://localhost:8000/docs> / <http://localhost:8000/redoc> |
| Frontend | <http://localhost:5173> |
| Adminer (DB) | <http://localhost:8080> |
| Mailcatcher (SMTP UI) | <http://localhost:1080> |
| step-ca | <https://localhost:9000> |

There's no Traefik in dev (FU-11) — services are reached directly on the ports above. The prod stack is fronted by a separately-deployed Traefik per [deployment.md](./deployment.md).

The first start can take a minute while the backend waits for the database and `prestart` runs migrations + seeds the first superuser.

## Mailcatcher

Mailcatcher catches every email the backend sends in dev (instead of relaying to a real SMTP). The backend is preconfigured to reach it at `mailcatcher:1025`; the captured messages render at <http://localhost:1080>.

Useful for verifying password-recovery flows, signup confirmation copy, etc., without touching a real mailbox.

## Swapping a Docker service for a host process

Each service is also mapped to its conventional host port, so you can stop the Docker version and run the same thing on the host:

```bash
# frontend on host
dc stop frontend
cd frontend && npm run dev

# backend on host (host needs the env exported manually)
dc stop backend
cd backend && uv sync
set -a && . ../.env.dev && set +a
fastapi dev app/main.py
```

The other services keep working because the host process listens on the same port the Docker service was bound to.

## Env-file conventions

Per-environment env files only — there is no `.env` (FU-15 dropped it):

- `.env.dev` — local development, gitignored. The dev `--env-file .env.dev` flag covers both compose-parse-time `${VAR}` substitution and per-service `env_file:` injection.
- `.env.prod` — production, gitignored. Used as `--env-file .env.prod -f docker-compose.yml` (no override file).
- `.env.example` — tracked, holds dummy values; copy to `.env.dev` when bootstrapping a new dev box.

After editing an env value, recreate the relevant containers — env files are read at container creation, not on each request:

```bash
dc up -d --force-recreate backend worker
```

`docker compose watch` will not pick up env-file changes; use `--force-recreate` (or `dc down && dc up -d`).

## Compose file layout

- `docker-compose.yml` — base, shared with prod.
- `docker-compose.override.yml` — dev-only overrides (port mappings, `develop: watch`, mailcatcher, the playwright service). Loaded automatically when present.

Prod runs `--env-file .env.prod -f docker-compose.yml` to skip the override file.

## Pre-commit hooks

Linting and formatting run before each commit via [prek](https://prek.j178.dev/) (a faster pre-commit reimplementation). The config is `.pre-commit-config.yaml` at the project root.

Install the hook (once per clone):

```bash
uv run prek install -f
```

Run all hooks against every file (useful before opening a PR):

```bash
uv run prek run --all-files
```

The hooks cover: large-file check, TOML/YAML validation, trailing-whitespace + end-of-file fixes, ruff (lint) + ruff-format (formatter), and biome for the frontend.

## Staying-in-sync gotchas

- **`develop: watch` flushes on `down/up`.** A `dc down && dc up -d` cycle rebuilds containers from the image; any source the watch had been syncing reverts to image-baked state. If you see ghost test failures after a `down/up`, run `dc build backend && dc up -d` to bake current source.
- **Tests run against `app_test`, not `app`.** The conftest forces `POSTGRES_DB=app_test` before any `app.*` import; running pytest never touches the dev database. (FU-16 hardening.)
- **The classifier-load test reuses the LRU cache.** Tests that mock `app.tasks._get_classifier` should call `_get_classifier.cache_clear()` first.
