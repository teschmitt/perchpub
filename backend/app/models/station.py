"""Station Pydantic schemas."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from app.models.base import PerchPubBase
from app.models.user import User

if TYPE_CHECKING:
    from app.models.observation import Observation
    from app.models.upload import Upload


class StationBase(SQLModel):
    """Base station schema with shared fields."""

    latitude: float = Field(ge=-90, le=90, description="Latitude")
    longitude: float = Field(ge=-180, le=180, description="Longitude")
    is_private: bool = Field(
        default=False,
        description="Hide the station from unauthenticated viewers and other users",
    )


class StationCreate(StationBase):
    """Schema for creating a new station."""

    pass


class Station(PerchPubBase, StationBase, table=True):
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    spki_sha256: str | None = Field(default=None, unique=True, index=True)
    # Set when an owner/superuser revokes the station (D1). A revoked station's
    # leaf no longer authenticates in get_current_station and the station drops
    # from the active list; revocation is non-destructive (uploads/observations
    # are retained). Recovery is a fresh device key -> new SPKI -> new Station.
    revoked_at: datetime | None = Field(default=None)
    owner: User | None = Relationship(back_populates="stations")
    uploads: list["Upload"] = Relationship(
        back_populates="station", cascade_delete=True
    )
    observations: list["Observation"] = Relationship(
        back_populates="station", cascade_delete=True
    )


class StationUpdate(StationBase):
    """Schema for updating a station (all fields optional)."""

    pass


class StationOwnerPublic(SQLModel):
    """Lean owner projection surfaced on station responses."""

    id: uuid.UUID
    full_name: str | None = None


class StationPublic(StationBase):
    """Schema for station response."""

    id: uuid.UUID
    owner: StationOwnerPublic | None
    revoked_at: datetime | None = None


class StationsPublic(SQLModel):
    data: list[StationPublic]
    count: int
