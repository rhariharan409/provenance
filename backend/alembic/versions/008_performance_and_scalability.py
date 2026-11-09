"""Performance and scalability schema

Revision ID: 008_performance_and_scalability
Revises: 007_performance_progress
Create Date: 2026-11-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '008_performance_and_scalability'
down_revision: Union[str, None] = '007_performance_progress'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c['name'] for c in inspector.get_columns('projects')}

    if 'history_window_months' not in existing_cols:
        op.add_column('projects', sa.Column('history_window_months', sa.Integer(), nullable=True))
    if 'progress_step' not in existing_cols:
        op.add_column('projects', sa.Column('progress_step', sa.Text(), nullable=True))
    if 'progress_current' not in existing_cols:
        op.add_column('projects', sa.Column('progress_current', sa.Integer(), nullable=True))
    if 'progress_total' not in existing_cols:
        op.add_column('projects', sa.Column('progress_total', sa.Integer(), nullable=True))
    if 'clone_mode' not in existing_cols:
        op.add_column('projects', sa.Column('clone_mode', sa.Text(), nullable=True))
    if 'timings' not in existing_cols:
        op.add_column('projects', sa.Column('timings', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    if 'estimated_commits' not in existing_cols:
        op.add_column('projects', sa.Column('estimated_commits', sa.Integer(), nullable=True))
    if 'partial_analysis' not in existing_cols:
        op.add_column('projects', sa.Column('partial_analysis', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    if 'analyzed_since' not in existing_cols:
        op.add_column('projects', sa.Column('analyzed_since', sa.DateTime(timezone=True), nullable=True))

    existing_tables = set(inspector.get_table_names())
    if 'blame_cache' not in existing_tables:
        op.create_table(
            'blame_cache',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('blob_sha', sa.String(length=40), nullable=False),
            sa.Column('path', sa.Text(), nullable=False),
            sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('project_id', 'blob_sha', 'path', name='uq_blame_cache_project_blob_path')
        )
        op.create_index('ix_blame_cache_project_created', 'blame_cache', ['project_id', 'created_at'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if 'blame_cache' in existing_tables:
        op.drop_index('ix_blame_cache_project_created', table_name='blame_cache')
        op.drop_table('blame_cache')

    existing_cols = {c['name'] for c in inspector.get_columns('projects')}
    if 'analyzed_since' in existing_cols:
        op.drop_column('projects', 'analyzed_since')
    if 'partial_analysis' in existing_cols:
        op.drop_column('projects', 'partial_analysis')
    if 'estimated_commits' in existing_cols:
        op.drop_column('projects', 'estimated_commits')
    if 'timings' in existing_cols:
        op.drop_column('projects', 'timings')
    if 'clone_mode' in existing_cols:
        op.drop_column('projects', 'clone_mode')
    if 'progress_total' in existing_cols:
        op.drop_column('projects', 'progress_total')
    if 'progress_current' in existing_cols:
        op.drop_column('projects', 'progress_current')
    if 'history_window_months' in existing_cols:
        op.drop_column('projects', 'history_window_months')

