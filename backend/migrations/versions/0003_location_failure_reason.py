"""location failure reason

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reports already unlocated keep NULL ("reason not recorded"); no guessed backfill.
    op.add_column('reports', sa.Column('location_failure', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('reports', 'location_failure')
