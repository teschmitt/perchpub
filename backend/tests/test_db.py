from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine


def test_db_session_timezone_is_utc() -> None:
    """The engine pins the Postgres session TimeZone to UTC.

    Aware-UTC datetimes are written to TIMESTAMP WITHOUT TIME ZONE columns and
    compared against naive-UTC (enrollment expiry, the per-user quotas, the
    audit purge). Pinning the session TimeZone keeps that correct on a server
    whose default TimeZone is not UTC (e.g. a regional managed Postgres), where
    the stored wall-clock would otherwise skew against the naive-UTC boundary.
    """
    with Session(engine) as session:
        tz = session.execute(text("SELECT current_setting('TimeZone')")).scalar()
    assert tz == "UTC"
