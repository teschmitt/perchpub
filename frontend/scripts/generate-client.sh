#!/usr/bin/env bash
# Regenerate the typed API client from the backend's live OpenAPI schema.
#
# Produces src/lib/api/schema.d.ts via openapi-typescript. The browser/app code
# consumes this through openapi-fetch (src/lib/api/client.ts) so endpoint URLs
# are never hand-written. Run from anywhere; paths are resolved relative to this
# script. openapi-typescript is invoked via npx (it is a dev-time codegen CLI,
# not a runtime/build dependency, so it stays out of package.json).
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$FRONTEND_DIR/.." && pwd)"
BACKEND_DIR="$REPO_DIR/backend"
OUT="$FRONTEND_DIR/src/lib/api/schema.d.ts"
TMP_SPEC="$(mktemp)"
trap 'rm -f "$TMP_SPEC"' EXIT

# app.main.app.openapi() needs only the settings env (PROJECT_NAME, POSTGRES_*,
# FIRST_SUPERUSER*) — no DB connection. Source the dev env if present so the
# import succeeds on a host shell.
if [ -f "$REPO_DIR/.env.dev" ]; then
	set -a
	# shellcheck disable=SC1091
	. "$REPO_DIR/.env.dev"
	set +a
fi

# Prefer the backend's uv venv on a host; fall back to bare python (the
# convention inside `docker compose exec backend`).
DUMP='import app.main, json; print(json.dumps(app.main.app.openapi()))'
if command -v uv >/dev/null 2>&1 && [ -d "$BACKEND_DIR/.venv" ]; then
	( cd "$BACKEND_DIR" && uv run python -c "$DUMP" ) >"$TMP_SPEC"
else
	( cd "$BACKEND_DIR" && python -c "$DUMP" ) >"$TMP_SPEC"
fi

npx --yes openapi-typescript@7 "$TMP_SPEC" --output "$OUT"
echo "Wrote $OUT"
