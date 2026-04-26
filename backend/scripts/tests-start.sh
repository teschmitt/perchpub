#! /usr/bin/env bash
set -e
set -x

# `test.sh` now owns DB readiness, test-DB creation, and alembic upgrade
# (FU-16). Kept as a wrapper for callers that already invoke this name.
bash scripts/test.sh "$@"
