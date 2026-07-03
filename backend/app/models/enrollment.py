import enum
import uuid
from datetime import datetime, timezone

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
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    station_id: uuid.UUID | None = Field(
        foreign_key="station.id", default=None, ondelete="SET NULL"
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    # Privacy is chosen at setup and applied to the Station born at confirm time.
    is_private: bool = Field(default=False, nullable=False)


class EnrollmentSessionCreate(SQLModel):
    """Body the operator POSTs to /enrollment/create."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    is_private: bool = False


class EnrollmentSession(SQLModel):
    session_id: uuid.UUID
    auth_token: str
    expires_at: datetime
    # Lowercase-hex SHA-256(SPKI) of the device-CA root — the QR's out-of-band
    # integrity commitment the station verifies /confirm's chain against.
    ca_pin: str


class EnrollmentRequest(SQLModel):
    """Body the station POSTs to /enrollment/confirm."""

    auth_token: str
    csr_pem: str


class EnrollmentResponse(SQLModel):
    success: bool
    reason: str = Field(default="")
    certificate_pem: str | None = None
    ca_chain_pem: str | None = None
    station_id: uuid.UUID | None = None


class EnrollmentAuditEvent(str, enum.Enum):
    """The enrollment lifecycle events worth attributing (design D3)."""

    session_created = "session_created"
    confirm_succeeded = "confirm_succeeded"
    station_revoked = "station_revoked"


class EnrollmentAudit(SQLModel, table=True):
    """Append-only audit trail for enrollment lifecycle events (design D3).

    A queryable table (not logs — no log aggregation is deployed and a rogue
    enrollment must be attributable by query). Deliberately FK-free: an audit
    row must survive deletion of the user/station/session it references, so a
    leaked-token incident stays reconstructable after the fact. Retention is
    bounded by a periodic purge (``ENROLLMENT_AUDIT_RETENTION_DAYS``). Failed
    confirms are not recorded per-attempt (the ≤3 cap + rate limits bound them
    and they would dominate the table); the lifecycle events carry attribution.
    """

    __tablename__ = "enrollment_audit"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event: EnrollmentAuditEvent = Field(nullable=False)
    session_id: uuid.UUID | None = Field(default=None)
    # The session owner for confirm, the revoker for revoke.
    actor_user_id: uuid.UUID | None = Field(default=None)
    source: str | None = Field(default=None)
    user_agent: str | None = Field(default=None)
    spki_sha256: str | None = Field(default=None)
    station_id: uuid.UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
