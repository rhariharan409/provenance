import enum
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class ProjectStatus(str, enum.Enum):
    pending = "pending"
    analyzing = "analyzing"
    ready = "ready"
    failed = "failed"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", native_enum=True),
        default=ProjectStatus.pending,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    owner = relationship("User", backref="projects")

    __table_args__ = (
        Index("ix_projects_owner_id", "owner_id"),
    )
