"""Per-user enrollment/station quota enforcement (design D2).

The ceilings are DB-backed and always enforced (unlike the fail-open rate
limiter). Each check takes a per-owner advisory transaction lock first, so
concurrent check-then-insert requests for one owner serialize and cannot both
pass a ceiling (TOCTOU). The active-session ceiling gates ``/enrollment/create``;
the owned-station ceiling gates the points a *new* station is created
(enrollment confirm for a new device, direct ``POST /station/``) — refreshing an
existing station is exempt, since certificate refresh has no other path.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.models.enrollment import EnrollmentToken
from app.models.station import Station, active_station_filter


def _lock_owner(session: Session, owner_id: uuid.UUID) -> None:
    """Take a per-owner advisory lock for the current transaction.

    Held until the request commits/rolls back, so a concurrent request for the
    same owner blocks here instead of racing past the ceiling between the count
    and the insert. ``hashtext`` maps the owner UUID to the lock's ``bigint``
    key; a hash collision only makes two owners occasionally serialize (a
    throughput non-event on this low-QPS path).
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:owner))"),
        {"owner": str(owner_id)},
    )


def enforce_active_session_quota(
    session: Session, owner_id: uuid.UUID, *, is_superuser: bool
) -> None:
    """Raise ``403`` if the owner is at the active-session ceiling (D2)."""
    if is_superuser:
        return
    _lock_owner(session, owner_id)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    active = session.exec(
        select(func.count())
        .select_from(EnrollmentToken)
        .where(
            EnrollmentToken.owner_id == owner_id,
            col(EnrollmentToken.claimed).is_(False),
            col(EnrollmentToken.expires_at) > now_naive,
        )
    ).one()
    if active >= settings.MAX_ACTIVE_ENROLLMENT_SESSIONS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="active enrollment session limit reached",
        )


def enforce_station_quota(
    session: Session, owner_id: uuid.UUID, *, is_superuser: bool
) -> None:
    """Raise ``403`` if the owner is at the owned-station ceiling (D2).

    Call only where a *new* station would be created; a revoked station frees a
    slot. Refreshing an existing station must not reach this check.
    """
    if is_superuser:
        return
    _lock_owner(session, owner_id)
    owned = session.exec(
        select(func.count())
        .select_from(Station)
        .where(
            Station.owner_id == owner_id,
            active_station_filter(),
        )
    ).one()
    if owned >= settings.MAX_STATIONS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="station limit reached",
        )
