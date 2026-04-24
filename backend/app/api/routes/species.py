import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select

from app.api.deps import SessionDep, get_current_active_superuser
from app.models.species import Species, SpeciesCreate, SpeciesMultiPublic, SpeciesPublic

router = APIRouter(prefix="/species", tags=["species"])


@router.get("/", response_model=SpeciesMultiPublic)
def read__multiple_species(
    session: SessionDep, skip: int = 0, limit: int = 100
) -> SpeciesMultiPublic:
    """
    Retrieve species.
    """

    count_statement = select(func.count()).select_from(Species)
    count = session.exec(count_statement).one()
    statement = select(Species).offset(skip).limit(limit)
    items = session.exec(statement).all()

    return SpeciesMultiPublic(data=items, count=count)


@router.get("/{id}", response_model=SpeciesPublic)
def read_species(session: SessionDep, id: uuid.UUID) -> SpeciesPublic:
    """
    Get species by ID.
    """
    species = session.get(Species, id)
    if not species:
        raise HTTPException(status_code=404, detail="Species not found")
    return species


@router.post(
    "/",
    response_model=SpeciesPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def create_species(*, session: SessionDep, species_in: SpeciesCreate) -> SpeciesPublic:
    """
    Create new species.
    """
    species = Species.model_validate(species_in)
    session.add(species)
    session.commit()
    session.refresh(species)
    return species
