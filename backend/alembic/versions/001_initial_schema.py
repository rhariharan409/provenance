"""Initial schema: users, projects, contributions

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-07 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role_enum = sa.Enum('student', 'faculty', 'admin', name='user_role')
    project_status_enum = sa.Enum('pending', 'analyzing', 'ready', 'failed', name='project_status')

    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('github_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.Text(), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('role', user_role_enum, server_default='student', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('github_id', name='uq_users_github_id')
    )
    op.create_index('ix_users_github_id', 'users', ['github_id'])

    op.create_table(
        'projects',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('repo_url', sa.Text(), nullable=False),
        sa.Column('repo_full_name', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', project_status_enum, server_default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_projects_owner_id', 'projects', ['owner_id'])

    op.create_table(
        'contributions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('github_login', sa.Text(), nullable=False),
        sa.Column('commit_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('score', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('confidence', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_contributions_project_id', 'contributions', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_contributions_project_id', table_name='contributions')
    op.drop_table('contributions')
    op.drop_index('ix_projects_owner_id', table_name='projects')
    op.drop_table('projects')
    op.drop_index('ix_users_github_id', table_name='users')
    op.drop_table('users')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='project_status').drop(bind, checkfirst=True)
        sa.Enum(name='user_role').drop(bind, checkfirst=True)
