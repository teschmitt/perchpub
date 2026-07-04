import os

# FU-16 hardening: force tests onto the dedicated test DB before any app
# import builds `Settings()`. `scripts/test.sh` already exports this, but a
# direct `pytest ...` invocation inherits whatever POSTGRES_DB the dev env
# carries — that bypass would let the autouse teardown wipe the dev DB.
os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "app_test")

from collections.abc import Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, delete  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from tests.utils.user import authentication_token_from_email  # noqa: E402
from tests.utils.utils import get_superuser_token_headers  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        init_db(session)
        yield session
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.execute(delete(table))
        session.commit()


@pytest.fixture(autouse=True)
def _fail_open_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the enrollment rate limiter by default (fail-open).

    The confirm limiter keys per source, and every ``TestClient`` request
    reports the same source (``"testclient"``), so on a live-Redis in-stack run
    (``scripts/tests-start.sh``) the shared bucket would ``429`` unrelated
    confirm tests once >``ENROLLMENT_CONFIRM_RATE_PER_MIN`` land in one window.
    Default to a backend that always raises, so ``_within_fixed_window`` fails
    open (allows) regardless of whether Redis is reachable; the rate-limit tests
    opt back in with their own counting fake.

    Also close the fail-open circuit breaker, whose module-level state would
    otherwise carry a prior test's opened circuit (skipping the backend) into
    tests that install their own counting fake.
    """
    from app.core import ratelimit
    from tests.utils.fake_redis import FailOpenRedis

    monkeypatch.setattr(ratelimit, "redis_client", FailOpenRedis())
    ratelimit._reset_circuit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
