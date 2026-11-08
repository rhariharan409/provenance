"""Section 5: faculty, summaries, originality schema

Revision ID: 005_section5_schema
Revises: 004_passport_and_disputes_schema
Create Date: 2026-11-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '005_section5_schema'
down_revision: Union[str, None] = '004_passport_and_disputes_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create project_faculty table
    op.create_table(
        'project_faculty',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('faculty_user_id', sa.Uuid(), nullable=False),
        sa.Column('assigned_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['faculty_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'faculty_user_id', name='uq_project_faculty'),
    )
    op.create_index('ix_project_faculty_project_id', 'project_faculty', ['project_id'])
    op.create_index('ix_project_faculty_faculty_user_id', 'project_faculty', ['faculty_user_id'])

    # 2. Create member_summaries table
    summary_method = sa.Enum('llm', 'rule_based', name='summary_method')

    op.create_table(
        'member_summaries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('method', summary_method, nullable=False),
        sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'member_id', name='uq_member_summary_run_member'),
    )
    op.create_index('ix_member_summaries_run_id', 'member_summaries', ['run_id'])
    op.create_index('ix_member_summaries_member_id', 'member_summaries', ['member_id'])

    # 3. Create fingerprints table
    op.create_table(
        'fingerprints',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('hash', sa.BigInteger(), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('line_start', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fingerprints_hash', 'fingerprints', ['hash'])
    op.create_index('ix_fingerprints_project_id', 'fingerprints', ['project_id'])
    op.create_index('ix_fingerprints_run_id', 'fingerprints', ['run_id'])
    op.create_index('ix_fingerprints_hash_project', 'fingerprints', ['hash', 'project_id'])

    # 4. Create originality_matches table
    op.create_table(
        'originality_matches',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('other_project_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('shared_fingerprints', sa.Integer(), nullable=False),
        sa.Column('shared_lines_estimate', sa.Integer(), nullable=False),
        sa.Column('top_files', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['other_project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'other_project_id', name='uq_originality_run_other_project'),
    )
    op.create_index('ix_originality_matches_project_id', 'originality_matches', ['project_id'])
    op.create_index('ix_originality_matches_other_project_id', 'originality_matches', ['other_project_id'])
    op.create_index('ix_originality_matches_run_id', 'originality_matches', ['run_id'])


def downgrade() -> None:
    op.drop_table('originality_matches')
    op.drop_table('fingerprints')
    op.drop_table('member_summaries')
    sa.Enum(name='summary_method').drop(op.get_bind(), checkfirst=True)
    op.drop_table('project_faculty')
