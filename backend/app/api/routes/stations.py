import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, or_, select

from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    audit_provenance,
)
from app.core.quotas import enforce_station_quota
from app.models.enrollment import EnrollmentAudit, EnrollmentAuditEvent
from app.models.station import (
    Station,
    StationCreate,
    StationPublic,
    StationsPublic,
    StationUpdate,
    active_station_filter,
)
from app.models.user import User

router = APIRouter(prefix="/station", tags=["station"])


def _visibility_filter(current_user: User | None) -> ColumnElement[bool] | None:
    """Return a SQL predicate limiting stations to what `current_user` may see.

    Superusers see every station. Anonymous callers see public stations only.
    Authenticated non-superusers see public stations plus their own.
    """
    if current_user is not None and current_user.is_superuser:
        return None
    public_only = col(Station.is_private).is_(False)
    if current_user is None:
        return public_only
    return or_(public_only, Station.owner_id == current_user.id)


def _load_station_for_mutation(
    session: Session, station_id: uuid.UUID, current_user: User
) -> Station:
    """Load a station the caller is allowed to mutate, or raise.

    Owner-or-superuser may proceed. A non-owner gets 403 on a public station and
    404 on a private one — the same existence-leak avoidance as `read_station`.
    Shared by `update_station` and `revoke_station` so their authorization can
    never drift apart.
    """
    station = session.get(Station, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    if station.owner_id != current_user.id and not current_user.is_superuser:
        if station.is_private:
            raise HTTPException(status_code=404, detail="Station not found")
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return station


@router.get("/", response_model=StationsPublic)
def read_stations(
    session: SessionDep,
    current_user: OptionalCurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> StationsPublic:
    """
    Retrieve station.
    """
    visibility = _visibility_filter(current_user)

    # A revoked station drops out of the active list for everyone, owner and
    # superuser included (D1) — it is not an active station.
    active = active_station_filter()
    count_statement = select(func.count()).select_from(Station).where(active)
    statement = select(Station).where(active)
    if visibility is not None:
        count_statement = count_statement.where(visibility)
        statement = statement.where(visibility)
    count = session.exec(count_statement).one()
    statement = statement.order_by(
        col(Station.created_at).desc(), col(Station.id).desc()
    )
    stations = session.exec(statement.offset(skip).limit(limit)).all()

    return StationsPublic(data=stations, count=count)


@router.get("/{id}", response_model=StationPublic)
def read_station(
    session: SessionDep, current_user: OptionalCurrentUser, id: uuid.UUID
) -> Station:
    """
    Get station by ID.
    """
    station = session.get(Station, id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    if station.is_private:
        is_owner = current_user is not None and station.owner_id == current_user.id
        is_superuser = current_user is not None and current_user.is_superuser
        if not (is_owner or is_superuser):
            raise HTTPException(status_code=404, detail="Station not found")
    return station


@router.post("/", response_model=StationPublic)
def create_station(
    *, session: SessionDep, current_user: CurrentUser, station_in: StationCreate
) -> Station:
    """
    Create new station.
    """
    # The owned-station ceiling applies here too, so it cannot be bypassed by
    # creating stations directly instead of through enrollment (D2).
    enforce_station_quota(
        session, current_user.id, is_superuser=current_user.is_superuser
    )

    station = Station.model_validate(station_in, update={"owner_id": current_user.id})
    session.add(station)
    session.commit()
    session.refresh(station)
    return station


@router.put("/{id}", response_model=StationPublic)
def update_station(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    item_in: StationUpdate,
) -> Station:
    """
    Update a station. Owners may edit their own row; superusers may edit any.
    Non-owners get 403 on a public station, 404 on a private one (matching
    `read_station`'s existence-leak avoidance).
    """
    station = _load_station_for_mutation(session, id, current_user)
    update_dict = item_in.model_dump(exclude_unset=True)
    station.sqlmodel_update(update_dict)
    session.add(station)
    session.commit()
    session.refresh(station)
    return station


@router.post("/{id}/revoke", response_model=StationPublic)
def revoke_station(
    *,
    session: SessionDep,
    request: Request,
    current_user: CurrentUser,
    id: uuid.UUID,
) -> Station:
    """Revoke a station so its certificate no longer authenticates mTLS uploads.

    Owner-or-superuser; a non-owner gets 403 on a public station and 404 on a
    private one, mirroring `update_station`'s existence-leak avoidance.
    Non-destructive — observations and uploads are retained — and idempotent:
    re-revoking keeps the original `revoked_at` and writes no second audit row.
    Recovery is re-enrolling a fresh device key (a new SPKI), not un-revoking.
    """
    station = _load_station_for_mutation(session, id, current_user)
    if station.revoked_at is None:
        station.revoked_at = datetime.now(timezone.utc)
        session.add(station)
        session.add(
            EnrollmentAudit(
                event=EnrollmentAuditEvent.station_revoked,
                actor_user_id=current_user.id,
                station_id=station.id,
                spki_sha256=station.spki_sha256,
                **audit_provenance(request),
            )
        )
        session.commit()
        session.refresh(station)
    return station
