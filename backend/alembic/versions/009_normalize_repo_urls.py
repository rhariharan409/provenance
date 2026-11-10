"""Normalize repo URLs and repo_full_name

Revision ID: 009_normalize_repo_urls
Revises: 008_performance_and_scalability
Create Date: 2026-11-09 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '009_normalize_repo_urls'
down_revision: Union[str, None] = '008_performance_and_scalability'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if projects table exists
    inspector = sa.inspect(conn)
    if 'projects' not in inspector.get_table_names():
        return

    is_pg = conn.dialect.name == 'postgresql'
    uuid_type = postgresql.UUID(as_uuid=True) if is_pg else sa.Uuid(as_uuid=True)

    projects_table = sa.Table(
        'projects',
        sa.MetaData(),
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('owner_id', uuid_type),
        sa.Column('repo_full_name', sa.Text()),
        sa.Column('repo_url', sa.Text()),
        sa.Column('name', sa.Text()),
    )

    rows = conn.execute(
        sa.select(
            projects_table.c.id,
            projects_table.c.owner_id,
            projects_table.c.repo_full_name,
            projects_table.c.repo_url,
            projects_table.c.name,
        )
    ).fetchall()

    # Track (str(owner_id), lower(repo_full_name))
    existing_owner_repos = set()
    for row in rows:
        owner_str = str(row.owner_id) if row.owner_id else ""
        rf_name = (row.repo_full_name or "").strip().lower()
        if owner_str and rf_name:
            existing_owner_repos.add((owner_str, rf_name))

    for row in rows:
        p_id = row.id
        owner_str = str(row.owner_id) if row.owner_id else ""
        current_full_name = row.repo_full_name or ""
        current_url = row.repo_url or ""
        current_name = row.name or ""

        new_full_name = current_full_name
        if new_full_name.lower().endswith(".git"):
            new_full_name = new_full_name[:-4].rstrip("/")

        new_url = current_url
        if new_url.lower().endswith(".git"):
            new_url = new_url[:-4].rstrip("/")

        new_name = current_name
        if new_name.lower().endswith(".git"):
            new_name = new_name[:-4].rstrip("/")

        if new_full_name != current_full_name or new_url != current_url:
            current_key = (owner_str, current_full_name.lower())
            target_key = (owner_str, new_full_name.lower())

            # Skip row if stripping would create a duplicate (owner_id, lower(repo_full_name))
            if new_full_name != current_full_name and target_key in existing_owner_repos and target_key != current_key:
                # If only repo_url can be updated safely:
                if new_url != current_url:
                    conn.execute(
                        projects_table.update()
                        .where(projects_table.c.id == p_id)
                        .values(repo_url=new_url)
                    )
                continue

            conn.execute(
                projects_table.update()
                .where(projects_table.c.id == p_id)
                .values(
                    repo_full_name=new_full_name,
                    repo_url=new_url,
                    name=new_name,
                )
            )
            existing_owner_repos.discard(current_key)
            existing_owner_repos.add(target_key)


def downgrade() -> None:
    pass

