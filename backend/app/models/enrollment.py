import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class EnrollmentToken(SQLModel, table=True):
    __tablename__ = "station_enrollment"

    session_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    expires_at: datetime = Field(nullable=False)
    claimed: bool = Field(default=False, nullable=False)
    token_tag: bytes = Field(nullable=False)
    key_id: str = Field(nullable=False)
    attempts: int = Field(ge=0, default=0)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    station_id: uuid.UUID | None = Field(
        foreign_key="station.id", default=None, ondelete="SET NULL"
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class EnrollmentSession(SQLModel):
    session_id: uuid.UUID
    auth_token: str
    expires_at: datetime


class EnrollmentRequest(SQLModel):
    auth_token: str  # Auth token sent by the station to authenticate against the server


class EnrollmentResponse(SQLModel):
    success: bool
    reason: str = Field(default="")
