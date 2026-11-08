"""Analysis and scoring schema

Revision ID: 003_analysis_and_scoring_schema
Revises: 002_repo_collection_schema
Create Date: 2026-11-08 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003_analysis_and_scoring_schema'
down_revision: Union[str, None] = '002_repo_collection_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add analysis columns to projects table
    op.add_column('projects', sa.Column('analysis_status', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('analysis_error', sa.Text(), nullable=True))

    # 2. Create analysis_runs table
    analysis_run_status = sa.Enum('running', 'complete', 'failed', name='analysis_run_status')

    op.create_table(
        'analysis_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('status', analysis_run_status, nullable=False),
        sa.Column('scoring_version', sa.Text(), server_default='1.0', nullable=False),
        sa.Column('head_sha', sa.String(length=40), nullable=False),
        sa.Column('weights', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_analysis_runs_project_id', 'analysis_runs', ['project_id'])
    op.create_index('ix_analysis_runs_project_status', 'analysis_runs', ['project_id', 'status'])

    # 3. Create contribution_scores table
    score_confidence = sa.Enum('high', 'medium', 'low', name='score_confidence')

    op.create_table(
        'contribution_scores',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('share_percent', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('confidence', score_confidence, nullable=False),
        sa.Column('signals', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'member_id', name='uq_contribution_scores_run_member')
    )
    op.create_index('ix_contribution_scores_project_id', 'contribution_scores', ['project_id'])
    op.create_index('ix_contribution_scores_member_id', 'contribution_scores', ['member_id'])


def downgrade() -> None:
    op.drop_index('ix_contribution_scores_member_id', table_name='contribution_scores')
    op.drop_index('ix_contribution_scores_project_id', table_name='contribution_scores')
    op.drop_table('contribution_scores')

    sa.Enum('high', 'medium', 'low', name='score_confidence').drop(op.get_bind(), checkfirst=True)

    op.drop_index('ix_analysis_runs_project_status', table_name='analysis_runs')
    op.drop_index('ix_analysis_runs_project_id', table_name='analysis_runs')
    op.drop_table('analysis_runs')

    sa.Enum('running', 'complete', 'failed', name='analysis_run_status').drop(op.get_bind(), checkfirst=True)

    op.drop_column('projects', 'analysis_error')
    op.drop_column('projects', 'analysis_status')
