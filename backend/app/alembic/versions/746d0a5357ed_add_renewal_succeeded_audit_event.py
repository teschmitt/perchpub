"""add renewal_succeeded audit event

Revision ID: 746d0a5357ed
Revises: b6aecd3d1905
Create Date: 2026-07-22 10:42:41.870611

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '746d0a5357ed'
down_revision = 'b6aecd3d1905'
branch_labels = None
depends_on = None


def upgrade():
    # Unattended cert renewal (/enrollment/renew) audits as its own lifecycle
    # event. ADD VALUE is transactional on Postgres >= 12 as long as the new
    # value is not used in the same transaction (we don't).
    op.execute(
        "ALTER TYPE enrollmentauditevent ADD VALUE IF NOT EXISTS 'renewal_succeeded'"
    )


def downgrade():
    # Postgres cannot drop a single enum value: delete the rows using it, then
    # rebuild the type without it (rename -> create -> re-point -> drop).
    op.execute("DELETE FROM enrollment_audit WHERE event = 'renewal_succeeded'")
    op.execute("ALTER TYPE enrollmentauditevent RENAME TO enrollmentauditevent_old")
    op.execute(
        "CREATE TYPE enrollmentauditevent AS ENUM "
        "('session_created', 'confirm_succeeded', 'station_revoked')"
    )
    op.execute(
        "ALTER TABLE enrollment_audit ALTER COLUMN event "
        "TYPE enrollmentauditevent USING event::text::enrollmentauditevent"
    )
    op.execute("DROP TYPE enrollmentauditevent_old")
