import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    author_name: Mapped[str] = mapped_column(Text, nullable=False)
    author_email: Mapped[str] = mapped_column(Text, nullable=False)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alias_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("author_aliases.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    project = relationship("Project", backref="commits")
    alias = relationship("AuthorAlias", backref="commits")

    __table_args__ = (
        Index("uq_commits_project_sha", "project_id", "sha", unique=True),
        Index("ix_commits_project_authored_at", "project_id", "authored_at"),
    )
