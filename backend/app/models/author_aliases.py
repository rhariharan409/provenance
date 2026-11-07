import enum
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class AliasSource(str, enum.Enum):
    noreply = "noreply"
    api_match = "api_match"
    name_match = "name_match"
    manual = "manual"


class AuthorAlias(Base):
    __tablename__ = "author_aliases"

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
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    source: Mapped[AliasSource] = mapped_column(
        Enum(AliasSource, name="alias_source", native_enum=True),
        nullable=False
    )
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    commit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    project = relationship("Project", backref="author_aliases")
    member = relationship("Member", backref="aliases")
    assigned_by_user = relationship("User", backref="assigned_aliases")

    __table_args__ = (
        Index(
            "uq_author_aliases_project_lower_email_name",
            "project_id",
            func.lower(email),
            func.lower(name),
            unique=True
        ),
    )
