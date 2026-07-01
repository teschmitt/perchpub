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

# Host-side scratch dir for files extracted from the step-ca container
# (the JWK and root cert sign_device_csr needs at runtime). Wiped by the
# trap on exit.
STEP_CA_TMPDIR=$(mktemp -d -t perchpub-step-ca.XXXXXX)
export STEP_CA_JWK_PATH="$STEP_CA_TMPDIR/backend-provisioner.jwk"
export STEP_CA_ROOT_CERT_PATH="$STEP_CA_TMPDIR/root_ca.crt"

cleanup() {
    rm -rf "$STEP_CA_TMPDIR"
    "${COMPOSE[@]}" down -v --remove-orphans
}
trap cleanup EXIT

# Pre-clean any leftover state from a previously-crashed run.
"${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true

# Rebuild the backend image the stack runs. The base + test overlay carry NO
# build context (only the dev override does), so `up` alone silently reuses a
# possibly-stale ${DOCKER_IMAGE_BACKEND}:latest — i.e. tests old code. Build
# from ./backend so the integration suite always exercises current code.
docker build -t "${DOCKER_IMAGE_BACKEND:-perchpub-api}:${TAG:-latest}" ../backend

"${COMPOSE[@]}" up -d --wait

# Pull the step-ca provisioner JWK + root cert out of the container so
# the host-side test process can sign CSRs and verify TLS without having
# to mount the step-ca volume.
"${COMPOSE[@]}" cp step-ca:/home/step/backend-provisioner.jwk "$STEP_CA_JWK_PATH"
"${COMPOSE[@]}" cp step-ca:/home/step/certs/root_ca.crt "$STEP_CA_ROOT_CERT_PATH"

uv run pytest -m integration tests/integration/
