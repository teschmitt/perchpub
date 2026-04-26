import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, func, or_, select

from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
)
from app.models.station import (
    Station,
    StationCreate,
    StationPublic,
    StationsPublic,
    StationUpdate,
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

    count_statement = select(func.count()).select_from(Station)
    statement = select(Station)
    if visibility is not None:
        count_statement = count_statement.where(visibility)
        statement = statement.where(visibility)
    count = session.exec(count_statement).one()
    stations = session.exec(statement.offset(skip).limit(limit)).all()

    return StationsPublic(data=stations, count=count)


@router.get("/{id}", response_model=StationPublic)
def read_station(
    session: SessionDep, current_user: OptionalCurrentUser, id: uuid.UUID
) -> StationPublic:
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
) -> StationPublic:
    """
    Create new station.
    """
    # TODO: add owner field

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
) -> StationPublic:
    """
    Update a station. Owners may edit their own row; superusers may edit any.
    Non-owners get 403 on a public station, 404 on a private one (matching
    `read_station`'s existence-leak avoidance).
    """
    station = session.get(Station, id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    if station.owner_id != current_user.id and not current_user.is_superuser:
        if station.is_private:
            raise HTTPException(status_code=404, detail="Station not found")
        raise HTTPException(status_code=403, detail="Not enough permissions")
    update_dict = item_in.model_dump(exclude_unset=True)
    station.sqlmodel_update(update_dict)
    session.add(station)
    session.commit()
    session.refresh(station)
    return station
