#!/usr/bin/env bash

# Integration-test driver. Brings up docker-compose.yml +
# docker-compose.test.yml (separate compose project from any running dev
# stack via COMPOSE_PROJECT_NAME=perchpub-test in .env.test), runs the
# tests marked `integration`, then tears down with `down -v` via trap.
#
# Run from backend/ to match scripts/test.sh's invocation style.

set -e
set -x

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not on PATH; skipping integration suite"
    exit 0
fi

# Source ../.env.test so the host-side pytest process sees the same
# hostnames / credentials the compose stack publishes on localhost ports.
if [ -f ../.env.test ]; then
    set -a
    # shellcheck disable=SC1091
    . ../.env.test
    set +a
fi

COMPOSE=(docker compose --env-file ../.env.test
    -f ../docker-compose.yml
    -f ../docker-compose.test.yml)

cleanup() {
    "${COMPOSE[@]}" down -v --remove-orphans
}
trap cleanup EXIT

# Pre-clean any leftover state from a previously-crashed run.
"${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true
"${COMPOSE[@]}" up -d --wait

uv run pytest -m integration tests/integration/
