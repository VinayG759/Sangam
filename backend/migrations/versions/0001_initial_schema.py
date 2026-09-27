"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-09-27 09:51:16.452700
"""

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('analysis_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_runs_country_code'), 'analysis_runs', ['country_code'], unique=False)
    op.create_table('regions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_variants', sa.ARRAY(sa.String()), nullable=False),
    sa.Column('parent_id', sa.String(length=64), nullable=True),
    sa.Column('external_code', sa.String(length=32), nullable=True),
    sa.Column('population', sa.Integer(), nullable=True),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lon', sa.Float(), nullable=True),
    sa.Column('source_name', sa.Text(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['regions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_regions_country_code'), 'regions', ['country_code'], unique=False)
    op.create_index(op.f('ix_regions_parent_id'), 'regions', ['parent_id'], unique=False)
    op.create_table('clusters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.String(length=64), nullable=False),
    sa.Column('sector', sa.String(length=50), nullable=False),
    sa.Column('report_count', sa.Integer(), nullable=False),
    sa.Column('distinct_reporters', sa.Integer(), nullable=False),
    sa.Column('per_1000', sa.Float(), nullable=True),
    sa.Column('baseline_ratio', sa.Float(), nullable=True),
    sa.Column('avg_urgency', sa.Float(), nullable=True),
    sa.Column('is_emerging', sa.Boolean(), nullable=False),
    sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clusters_run_id'), 'clusters', ['run_id'], unique=False)
    op.create_table('indicators',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.String(length=64), nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('unit', sa.String(length=50), nullable=True),
    sa.Column('period', sa.String(length=20), nullable=False),
    sa.Column('source_name', sa.Text(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('region_id', 'key', 'period')
    )
    op.create_index(op.f('ix_indicators_key'), 'indicators', ['key'], unique=False)
    op.create_index(op.f('ix_indicators_region_id'), 'indicators', ['region_id'], unique=False)
    op.create_table('projects',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('region_id', sa.String(length=64), nullable=False),
    sa.Column('sector', sa.String(length=50), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('sanctioned_date', sa.Date(), nullable=True),
    sa.Column('completion_date', sa.Date(), nullable=True),
    sa.Column('source_name', sa.Text(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_region_id'), 'projects', ['region_id'], unique=False)
    op.create_index(op.f('ix_projects_sector'), 'projects', ['sector'], unique=False)
    op.create_table('reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tracking_id', sa.String(length=16), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('channel', sa.String(length=20), nullable=False),
    sa.Column('reporter_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('text_original', sa.Text(), nullable=True),
    sa.Column('text_en', sa.Text(), nullable=True),
    sa.Column('sector', sa.String(length=50), nullable=True),
    sa.Column('urgency', sa.Integer(), nullable=True),
    sa.Column('location_text', sa.Text(), nullable=True),
    sa.Column('region_id', sa.String(length=64), nullable=True),
    sa.Column('location_method', sa.String(length=10), nullable=True),
    sa.Column('location_confidence', sa.Float(), nullable=True),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lon', sa.Float(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
    sa.Column('has_media', sa.Boolean(), nullable=False),
    sa.Column('flagged_coordinated', sa.Boolean(), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reports_country_code'), 'reports', ['country_code'], unique=False)
    op.create_index(op.f('ix_reports_created_at'), 'reports', ['created_at'], unique=False)
    op.create_index(op.f('ix_reports_region_id'), 'reports', ['region_id'], unique=False)
    op.create_index(op.f('ix_reports_reporter_hash'), 'reports', ['reporter_hash'], unique=False)
    op.create_index(op.f('ix_reports_sector'), 'reports', ['sector'], unique=False)
    op.create_index(op.f('ix_reports_status'), 'reports', ['status'], unique=False)
    op.create_index(op.f('ix_reports_tracking_id'), 'reports', ['tracking_id'], unique=True)
    op.create_table('conversations',
    sa.Column('reporter_hash', sa.String(length=64), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('awaiting', sa.String(length=20), nullable=False),
    sa.Column('candidate_region_id', sa.String(length=64), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_region_id'], ['regions.id'], ),
    sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('reporter_hash')
    )
    op.create_table('priorities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('cluster_id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.String(length=64), nullable=False),
    sa.Column('sector', sa.String(length=50), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('verdict', sa.String(length=30), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('components', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('estimated_cost', sa.Float(), nullable=True),
    sa.Column('beneficiaries', sa.Integer(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('summary_source', sa.String(length=10), nullable=False),
    sa.Column('displayable', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['cluster_id'], ['clusters.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_priorities_run_id'), 'priorities', ['run_id'], unique=False)
    op.create_index(op.f('ix_priorities_verdict'), 'priorities', ['verdict'], unique=False)
    op.create_table('report_media',
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('report_id')
    )


def downgrade() -> None:
    op.drop_table('report_media')
    op.drop_index(op.f('ix_priorities_verdict'), table_name='priorities')
    op.drop_index(op.f('ix_priorities_run_id'), table_name='priorities')
    op.drop_table('priorities')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_reports_tracking_id'), table_name='reports')
    op.drop_index(op.f('ix_reports_status'), table_name='reports')
    op.drop_index(op.f('ix_reports_sector'), table_name='reports')
    op.drop_index(op.f('ix_reports_reporter_hash'), table_name='reports')
    op.drop_index(op.f('ix_reports_region_id'), table_name='reports')
    op.drop_index(op.f('ix_reports_created_at'), table_name='reports')
    op.drop_index(op.f('ix_reports_country_code'), table_name='reports')
    op.drop_table('reports')
    op.drop_index(op.f('ix_projects_sector'), table_name='projects')
    op.drop_index(op.f('ix_projects_region_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_indicators_region_id'), table_name='indicators')
    op.drop_index(op.f('ix_indicators_key'), table_name='indicators')
    op.drop_table('indicators')
    op.drop_index(op.f('ix_clusters_run_id'), table_name='clusters')
    op.drop_table('clusters')
    op.drop_index(op.f('ix_regions_parent_id'), table_name='regions')
    op.drop_index(op.f('ix_regions_country_code'), table_name='regions')
    op.drop_table('regions')
    op.drop_index(op.f('ix_analysis_runs_country_code'), table_name='analysis_runs')
    op.drop_table('analysis_runs')
