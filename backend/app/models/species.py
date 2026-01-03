import enum
import uuid

from sqlmodel import Field, Relationship, SQLModel

from app.models.base import PerchPubBase


class IUCNStatus(str, enum.Enum):
    """IUCN Red List conservation status."""

    LC = "LC"  # Least Concern
    NT = "NT"  # Near Threatened
    VU = "VU"  # Vulnerable
    EN = "EN"  # Endangered
    CR = "CR"  # Critically Endangered
    EX = "EX"  # Extinct
    EW = "EW"  # Extinct in the Wild
    DD = "DD"  # Data Deficient


class SpeciesBase(SQLModel):
    """Base species schema with shared fields."""

    scientific_name: str = Field(
        min_length=1, max_length=255, description="Scientific species name"
    )


class Species(PerchPubBase, SpeciesBase, table=True):
    classification_id: int = Field(
        ge=0, description="Classification ID returned from model"
    )
    # TODO: for now only store classification data for the one model we have
    # TODO: in future, version the models and annotate DB data with model versions here and in the classify_task table
    # model_version: int = Field(ge=0, description="Classification model version")
    observations: list["Observation"] = Relationship(  # noqa: F821 # type: ignore
        back_populates="species"
    )


class SpeciesCreate(SpeciesBase):
    """Schema for creating a new species."""

    pass


class SpeciesPublic(SpeciesBase):
    """Schema for species response."""

    id: uuid.UUID


class SpeciesMultiPublic(SQLModel):
    data: list[SpeciesPublic]
    count: int
