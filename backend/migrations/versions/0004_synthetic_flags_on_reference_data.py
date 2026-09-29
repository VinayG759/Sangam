"""synthetic flags on reference data

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Demo statistics and projects are marked, like demo reports, so every screen can label them.
    op.add_column('indicators', sa.Column('is_synthetic', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('projects', sa.Column('is_synthetic', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column('projects', 'is_synthetic')
    op.drop_column('indicators', 'is_synthetic')
