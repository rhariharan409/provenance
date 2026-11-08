"""Performance, progress, and history window schema

Revision ID: 007_performance_and_progress_schema
Revises: 006_review_invitations_schema
Create Date: 2026-11-08 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '007_performance_progress'
down_revision: Union[str, None] = '006_review_invitations_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('history_window', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('history_since', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('progress_step', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('progress_percent', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('timing_stats', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'timing_stats')
    op.drop_column('projects', 'progress_percent')
    op.drop_column('projects', 'progress_step')
    op.drop_column('projects', 'history_since')
    op.drop_column('projects', 'history_window')
