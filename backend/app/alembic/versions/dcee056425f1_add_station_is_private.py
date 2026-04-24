"""add station is_private

Revision ID: dcee056425f1
Revises: 75ac186a4eae
Create Date: 2026-04-24 22:48:16.393788

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'dcee056425f1'
down_revision = '75ac186a4eae'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'station',
        sa.Column(
            'is_private',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column('station', 'is_private')
