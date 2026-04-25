"""Observation Pydantic schemas."""

import uuid
from datetime import datetime

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.models.base import PerchPubBase
from app.models.species import Species, SpeciesPublic
from app.models.station import Station, StationPublic


class ObservationBase(SQLModel):
    """Base observation schema with shared fields."""

    confidence_score: float | None = Field(description="AI confidence score (0-1)")
    classification_result: list | None = Field(
        description="Complete results from classification task", sa_column=Column(JSON)
    )


class ObservationCreate(ObservationBase):
    """Schema for creating a new observation."""

    station_id: uuid.UUID
    species_id: uuid.UUID | None = None
    object_name: str = Field(description="S3 object name")
    observed_at: datetime = Field(description="When the bird was observed")
    latitude: float = Field(ge=-90, le=90, description="Latitude")
    longitude: float = Field(ge=-180, le=180, description="Longitude")

    # TODO: augment with environmental data


class ObservationUpdate(ObservationBase):
    """Schema for creating a new observation."""

    species_id: uuid.UUID
    manually_classified: bool = Field(
        default=False, description="Whether the observation was manually classified"
    )


# Database model, database table inferred from class name
class Observation(PerchPubBase, ObservationBase, table=True):
    station_id: uuid.UUID = Field(
        foreign_key="station.id",
        nullable=False,
        ondelete="CASCADE",
        description="ID of the station the species was observed at",
    )
    species_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="species.id",
        nullable=True,
        ondelete="SET NULL",
        description="Top classifier label resolved to a Species row, or NULL when no row matches",
    )
    object_name: str = Field(description="S3 object name")
    exif_data: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="EXIF metadata from image",
    )
    observed_at: datetime = Field(description="When the bird was observed")
    manually_classified: bool = Field(
        default=False, description="Whether the observation was manually classified"
    )
    latitude: float = Field(ge=-90, le=90, description="Latitude")
    longitude: float = Field(ge=-180, le=180, description="Longitude")

    # TODO: augment with environmental data

    station: Station = Relationship(back_populates="observations")
    species: Species | None = Relationship(back_populates="observations")
    classify_tasks: list["ClassifyTask"] = Relationship(  # noqa: F821 # type: ignore
        back_populates="observation"
    )


class ObservationPublic(ObservationBase):
    """Schema for observation response."""

    id: uuid.UUID
    species: SpeciesPublic | None
    station: StationPublic
    observed_at: datetime
    object_name: str = Field(description="S3 object name")
    # TODO: show all classify tasks associated with this observation


class ObservationsPublic(SQLModel):
    data: list[ObservationPublic]
    count: int
