"""add is_private to station_enrollment

Revision ID: 26a9f726c495
Revises: 0782ae4207fd
Create Date: 2026-07-03 12:38:52.266284

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '26a9f726c495'
down_revision = '0782ae4207fd'
branch_labels = None
depends_on = None


def upgrade():
    # server_default=false backfills any existing (short-lived) enrollment rows,
    # so the NOT NULL add is safe on a populated table — mirroring dcee056425f1
    # (station.is_private). The model default is app-side (Field(default=False)).
    op.add_column(
        'station_enrollment',
        sa.Column(
            'is_private',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column('station_enrollment', 'is_private')
