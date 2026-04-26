import logging
import os
import re

from sqlalchemy import Engine, create_engine, text
from sqlmodel import Session, select
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

max_tries = 60 * 5  # 5 minutes
wait_seconds = 1

# Postgres identifier: letters/underscore start, then alnum/underscore.
# Restrict TEST_POSTGRES_DB to this shape because CREATE DATABASE doesn't
# accept bind params for the database name — we have to inline it.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _build_admin_engine() -> Engine:
    """Engine bound to the `postgres` system DB, AUTOCOMMIT.

    Used only to bootstrap the test DB before it exists. We can't reuse
    `app.core.db.engine` here: the test runner overrides POSTGRES_DB to
    `app_test`, so `engine` would be bound to a database that does not
    yet exist on first run.
    """
    user = os.environ["POSTGRES_USER"]
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ["POSTGRES_SERVER"]
    port = os.environ.get("POSTGRES_PORT", "5432")
    url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/postgres"
    return create_engine(url, isolation_level="AUTOCOMMIT")


@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
def init(db_engine: Engine) -> None:
    try:
        with Session(db_engine) as session:
            session.exec(select(1))
    except Exception as e:
        logger.error(e)
        raise e


def _ensure_test_db(admin_engine: Engine) -> None:
    target = os.environ.get("TEST_POSTGRES_DB", "app_test")
    if not _IDENT_RE.match(target):
        raise ValueError(f"unsafe TEST_POSTGRES_DB={target!r}")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": target},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target}"'))
            logger.info("Created test database %s", target)


def main() -> None:
    logger.info("Initializing test pre-start")
    admin = _build_admin_engine()
    init(admin)
    _ensure_test_db(admin)
    logger.info("Test pre-start finished")


if __name__ == "__main__":
    main()
