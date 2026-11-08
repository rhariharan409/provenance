"""Section 6: review invitations schema

Revision ID: 006_review_invitations_schema
Revises: 005_section5_schema
Create Date: 2026-11-08 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '006_review_invitations_schema'
down_revision: Union[str, None] = '005_section5_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'invitation_status') THEN CREATE TYPE invitation_status AS ENUM ('pending', 'accepted', 'declined'); END IF; END $$;")

    invitation_status = postgresql.ENUM('pending', 'accepted', 'declined', name='invitation_status', create_type=False)

    op.create_table(
        'review_invitations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('inviter_user_id', sa.Uuid(), nullable=False),
        sa.Column('invitee_user_id', sa.Uuid(), nullable=True),
        sa.Column('invitee_username', sa.String(length=100), nullable=False),
        sa.Column('status', invitation_status, nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['inviter_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invitee_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_review_invitations_project_id', 'review_invitations', ['project_id'])
    op.create_index('ix_review_invitations_inviter_user_id', 'review_invitations', ['inviter_user_id'])
    op.create_index('ix_review_invitations_invitee_user_id', 'review_invitations', ['invitee_user_id'])
    op.create_index('ix_review_invitations_invitee_username', 'review_invitations', ['invitee_username'])
    op.create_index('ix_review_invitations_status', 'review_invitations', ['status'])


def downgrade() -> None:
    op.drop_table('review_invitations')
    op.execute("DROP TYPE IF EXISTS invitation_status;")
