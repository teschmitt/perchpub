#!/usr/bin/env bash

set -e
set -x

# Source ../.env.dev for host runs (file is absent in the dev container and CI,
# where env vars are injected by docker-compose / the workflow respectively).
if [ -f ../.env.dev ]; then
    set -a
    # shellcheck disable=SC1091
    . ../.env.dev
    set +a
fi

coverage run -m pytest tests/
coverage report
coverage html --title "${@-coverage}"
