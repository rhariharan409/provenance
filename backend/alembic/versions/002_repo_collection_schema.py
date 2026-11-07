"""Repo collection and identity merging schema

Revision ID: 002_repo_collection_schema
Revises: 001_initial_schema
Create Date: 2026-11-07 19:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002_repo_collection_schema'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to projects table
    op.add_column('projects', sa.Column('github_owner', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('github_repo', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('default_branch', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('is_private', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('projects', sa.Column('github_installation_id', sa.BigInteger(), nullable=True))
    op.add_column('projects', sa.Column('clone_path', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('warnings', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('commit_total', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('projects', sa.Column('last_collected_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        'uq_projects_owner_lower_repo',
        'projects',
        ['owner_id', sa.text('lower(repo_full_name)')],
        unique=True
    )

    # 2. Create members table
    op.create_table(
        'members',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('github_login', sa.Text(), nullable=True),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_members_project_id', 'members', ['project_id'])
    op.create_index(
        'uq_members_project_lower_login',
        'members',
        ['project_id', sa.text('lower(github_login)')],
        unique=True,
        postgresql_where=sa.text('github_login IS NOT NULL')
    )

    # 3. Create author_aliases table
    alias_source_enum = sa.Enum('noreply', 'api_match', 'name_match', 'manual', name='alias_source')

    op.create_table(
        'author_aliases',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=True),
        sa.Column('source', alias_source_enum, nullable=False),
        sa.Column('is_bot', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('commit_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('assigned_by', sa.Uuid(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_author_aliases_project_id', 'author_aliases', ['project_id'])
    op.create_index('ix_author_aliases_member_id', 'author_aliases', ['member_id'])
    op.create_index(
        'uq_author_aliases_project_lower_email_name',
        'author_aliases',
        ['project_id', sa.text('lower(email)'), sa.text('lower(name)')],
        unique=True
    )

    # 4. Create commits table
    op.create_table(
        'commits',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('sha', sa.String(length=40), nullable=False),
        sa.Column('author_name', sa.Text(), nullable=False),
        sa.Column('author_email', sa.Text(), nullable=False),
        sa.Column('authored_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('additions', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('deletions', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('files_changed', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('parent_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('alias_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['alias_id'], ['author_aliases.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_commits_project_id', 'commits', ['project_id'])
    op.create_index('uq_commits_project_sha', 'commits', ['project_id', 'sha'], unique=True)
    op.create_index('ix_commits_project_authored_at', 'commits', ['project_id', 'authored_at'])

    # 5. Create pull_requests table
    op.create_table(
        'pull_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('author_login', sa.Text(), nullable=True),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('merged', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('merged_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pull_requests_project_id', 'pull_requests', ['project_id'])
    op.create_index('uq_pull_requests_project_number', 'pull_requests', ['project_id', 'number'], unique=True)

    # 6. Create reviews table
    op.create_table(
        'reviews',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('pull_request_id', sa.Uuid(), nullable=False),
        sa.Column('reviewer_login', sa.Text(), nullable=False),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['pull_request_id'], ['pull_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reviews_pull_request_id', 'reviews', ['pull_request_id'])


def downgrade() -> None:
    op.drop_table('reviews')
    op.drop_table('pull_requests')
    op.drop_table('commits')
    op.drop_table('author_aliases')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='alias_source').drop(bind, checkfirst=True)

    op.drop_table('members')

    op.drop_index('uq_projects_owner_lower_repo', table_name='projects')
    op.drop_column('projects', 'last_collected_at')
    op.drop_column('projects', 'commit_total')
    op.drop_column('projects', 'warnings')
    op.drop_column('projects', 'error_message')
    op.drop_column('projects', 'clone_path')
    op.drop_column('projects', 'github_installation_id')
    op.drop_column('projects', 'is_private')
    op.drop_column('projects', 'default_branch')
    op.drop_column('projects', 'github_repo')
    op.drop_column('projects', 'github_owner')

