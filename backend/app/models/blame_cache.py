import uuid
from datetime import datetime
from typing import Any, Dict
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class BlameCache(Base):
    __tablename__ = "blame_cache"

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
    blob_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    project = relationship("Project", backref="blame_cache_entries")

    __table_args__ = (
        UniqueConstraint("project_id", "blob_sha", "path", name="uq_blame_cache_project_blob_path"),
        Index("ix_blame_cache_project_created", "project_id", "created_at"),
    )

