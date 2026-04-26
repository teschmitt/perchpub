#!/usr/bin/env bash

# Each stage runs independently — `set -e` is deliberately omitted so an
# early failure (e.g. the mypy baseline) doesn't hide later findings.
set -x

exit_code=0
mypy app || exit_code=$?
ruff check app || exit_code=$?
ruff format app --check || exit_code=$?
exit "$exit_code"
