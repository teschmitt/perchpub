import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select

from app.api.deps import SessionDep, get_current_active_superuser
from app.models.observation import (
    Observation,
    ObservationCreate,
    ObservationPublic,
    ObservationsPublic,
    ObservationUpdate,
)

router = APIRouter(prefix="/observation", tags=["observation"])


@router.get("/", response_model=ObservationsPublic)
def read_observations(
    session: SessionDep, skip: int = 0, limit: int = 100
) -> ObservationsPublic:
    """
    Retrieve observation.
    """

    count_statement = select(func.count()).select_from(Observation)
    count = session.exec(count_statement).one()
    statement = select(Observation).offset(skip).limit(limit)
    observations = session.exec(statement).all()

    return ObservationsPublic(data=observations, count=count)


@router.get("/{id}", response_model=ObservationPublic)
def read_observation(session: SessionDep, id: uuid.UUID) -> ObservationPublic:
    """
    Get observation by ID.
    """
    observation = session.get(Observation, id)
    if not observation:
        raise HTTPException(status_code=404, detail="Observation not found")
    return observation


@router.post(
    "/",
    response_model=ObservationPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def create_observation(
    *, session: SessionDep, observation_in: ObservationCreate
) -> ObservationPublic:
    """
    Create new observation.
    """
    # TODO: add owner field

    observation = Observation.model_validate(observation_in)
    session.add(observation)
    session.commit()
    session.refresh(observation)
    return observation


@router.put(
    "/{id}",
    response_model=ObservationPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def update_observation(
    *,
    session: SessionDep,
    id: uuid.UUID,
    obs_in: ObservationUpdate,
) -> ObservationPublic:
    """
    Update an item.
    """
    observation = session.get(Observation, id)
    if not observation:
        raise HTTPException(status_code=404, detail="Item not found")
    # TODO: check authorization!
    update_dict = obs_in.model_dump(exclude_unset=True)
    observation.sqlmodel_update(update_dict)
    session.add(observation)
    session.commit()
    session.refresh(observation)
    return observation
