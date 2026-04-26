import uuid
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from app.models.base import PerchPubBase
from app.models.station import Station

if TYPE_CHECKING:
    from app.models.classify_task import ClassifyTask


class UploadBase(SQLModel):
    station_id: uuid.UUID
    object_name: str


class UploadCreate(UploadBase):
    pass


class UploadUpdate(UploadBase):
    pass


class Upload(PerchPubBase, UploadBase, table=True):
    station_id: uuid.UUID = Field(
        foreign_key="station.id", nullable=False, ondelete="CASCADE"
    )
    station: Station | None = Relationship(back_populates="uploads")
    classify_tasks: list["ClassifyTask"] = Relationship(
        back_populates="upload", cascade_delete=True
    )


class UploadPublic(PerchPubBase, UploadBase):
    station_id: uuid.UUID


class UploadsPublic(SQLModel):
    data: list[UploadPublic]
    count: int
