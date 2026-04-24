import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select

from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.models.station import (
    Station,
    StationCreate,
    StationPublic,
    StationsPublic,
    StationUpdate,
)

router = APIRouter(prefix="/station", tags=["station"])


@router.get("/", response_model=StationsPublic)
def read_stations(
    session: SessionDep, skip: int = 0, limit: int = 100
) -> StationsPublic:
    """
    Retrieve station.
    """

    count_statement = select(func.count()).select_from(Station)
    count = session.exec(count_statement).one()
    statement = select(Station).offset(skip).limit(limit)
    stations = session.exec(statement).all()

    return StationsPublic(data=stations, count=count)


@router.get("/{id}", response_model=StationPublic)
def read_station(session: SessionDep, id: uuid.UUID) -> StationPublic:
    """
    Get station by ID.
    """
    station = session.get(Station, id)
    if not station:
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


@router.put(
    "/{id}",
    response_model=StationPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def update_station(
    *,
    session: SessionDep,
    id: uuid.UUID,
    item_in: StationUpdate,
) -> StationPublic:
    """
    Update an item.
    """
    station = session.get(Station, id)
    if not station:
        raise HTTPException(status_code=404, detail="Item not found")
    # TODO: check authorization!
    update_dict = item_in.model_dump(exclude_unset=True)
    station.sqlmodel_update(update_dict)
    session.add(station)
    session.commit()
    session.refresh(station)
    return station
