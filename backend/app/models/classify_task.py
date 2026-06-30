import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.models.observation import Observation, ObservationPublic
from app.models.upload import Upload, UploadPublic


class ClassifyTaskStatus(str, enum.Enum):
    Prepared = "Prepared"
    Queued = "Queued"
    Processing = "Processing"
    Success = "Success"
    Failed = "Failed"


class ClassifyTaskBase(SQLModel):
    object_name: str = Field()
    status: ClassifyTaskStatus = Field(default=ClassifyTaskStatus.Prepared)


class ClassifyTaskCreate(ClassifyTaskBase):
    upload_id: uuid.UUID
    file_metadata: dict[str, Any]


class ClassifyTaskUpdate(ClassifyTaskBase):
    pass


class ClassifyTask(ClassifyTaskBase, table=True):
    __tablename__ = "classify_task"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status: ClassifyTaskStatus = Field(default=ClassifyTaskStatus.Prepared, index=True)
    file_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Metadata for the associated image",
    )
    upload_id: uuid.UUID = Field(
        foreign_key="upload.id", nullable=False, ondelete="CASCADE"
    )
    upload: Upload = Relationship(back_populates="classify_tasks")
    observation_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="observation.id",
        nullable=True,
        ondelete="SET NULL",
        index=True,
    )
    observation: Observation = Relationship(back_populates="classify_tasks")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
        nullable=False,
    )


class ClassifyTaskPublic(ClassifyTaskBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    upload: UploadPublic
    observation: ObservationPublic | None


class ClassifyTasksPublic(SQLModel):
    data: list[ClassifyTaskPublic]
    count: int
