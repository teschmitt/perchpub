import os
import subprocess
import sys
from pathlib import Path


def test_conftest_overrides_postgres_db_when_invoked_directly() -> None:
    """FU-16 tightening: even if pytest is launched without scripts/test.sh,
    importing tests.conftest must redirect POSTGRES_DB to the test DB before
    any app import, so a direct invocation cannot wipe the dev DB.

    Spawns a Python subprocess with POSTGRES_DB=app (the dev value), imports
    conftest, and asserts the env var has been forced to app_test. Subprocess
    isolation is required because the outer pytest already has the test DB
    set; we need a fresh process to verify the import-time override.
    """
    backend_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["POSTGRES_DB"] = "app"
    env.pop("TEST_POSTGRES_DB", None)
    code = (
        "import os, sys; "
        "sys.path.insert(0, 'tests'); "
        "import conftest; "
        "print(os.environ['POSTGRES_DB'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(backend_root),
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip() == "app_test"
    ), f"expected app_test, got {result.stdout!r}; stderr: {result.stderr}"
