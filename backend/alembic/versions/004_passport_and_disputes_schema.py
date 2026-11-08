"""Passport and disputes schema

Revision ID: 004_passport_and_disputes_schema
Revises: 003_analysis_and_scoring_schema
Create Date: 2026-11-08 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '004_passport_and_disputes_schema'
down_revision: Union[str, None] = '003_analysis_and_scoring_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create passports table
    op.create_table(
        'passports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('owner_user_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('seal', sa.String(length=64), nullable=False),
        sa.Column('seal_version', sa.Text(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('view_count', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_passports_code')
    )
    op.create_index('ix_passports_code', 'passports', ['code'])
    op.create_index('ix_passports_project_id', 'passports', ['project_id'])
    op.create_index('ix_passports_member_id', 'passports', ['member_id'])
    op.create_index('ix_passports_owner_user_id', 'passports', ['owner_user_id'])
    op.create_index('ix_passports_run_id', 'passports', ['run_id'])
    op.create_index(
        'uq_passports_member_run_active',
        'passports',
        ['member_id', 'run_id'],
        unique=True,
        postgresql_where=sa.text('revoked_at IS NULL')
    )

    # 2. Create disputes table
    dispute_status = sa.Enum('open', 'resolved', 'rejected', name='dispute_status')

    op.create_table(
        'disputes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('raised_by', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('status', dispute_status, server_default='open', nullable=False),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('resolved_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['raised_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_disputes_project_id', 'disputes', ['project_id'])
    op.create_index('ix_disputes_member_id', 'disputes', ['member_id'])
    op.create_index('ix_disputes_raised_by', 'disputes', ['raised_by'])
    op.create_index('ix_disputes_run_id', 'disputes', ['run_id'])


def downgrade() -> None:
    op.drop_index('ix_disputes_run_id', table_name='disputes')
    op.drop_index('ix_disputes_raised_by', table_name='disputes')
    op.drop_index('ix_disputes_member_id', table_name='disputes')
    op.drop_index('ix_disputes_project_id', table_name='disputes')
    op.drop_table('disputes')

    # Drop enum type in postgres
    sa.Enum(name='dispute_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index('uq_passports_member_run_active', table_name='passports', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index('ix_passports_run_id', table_name='passports')
    op.drop_index('ix_passports_owner_user_id', table_name='passports')
    op.drop_index('ix_passports_member_id', table_name='passports')
    op.drop_index('ix_passports_project_id', table_name='passports')
    op.drop_index('ix_passports_code', table_name='passports')
    op.drop_table('passports')
