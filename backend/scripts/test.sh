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

# Tests connect to a dedicated database so the dev `app` DB is never wiped
# by the autouse teardown in tests/conftest.py (FU-16). On first run,
# tests_pre_start.py CREATEs the DB; alembic then applies the schema.
# Override TEST_POSTGRES_DB if you need a parallel test DB.
export POSTGRES_DB="${TEST_POSTGRES_DB:-app_test}"

python app/tests_pre_start.py
alembic upgrade head

coverage run -m pytest -m "not integration" tests/
coverage report
coverage html --title "${@-coverage}"
