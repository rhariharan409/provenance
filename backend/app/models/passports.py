from datetime import datetime
from typing import Any, Dict, Optional
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Passport(Base):
    __tablename__ = "passports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    seal: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    seal_version: Mapped[str] = mapped_column(
        Text,
        default="1",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    view_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    project = relationship("Project", backref="passports")
    member = relationship("Member", backref="passports")
    owner_user = relationship("User", foreign_keys=[owner_user_id], backref="owned_passports")
    run = relationship("AnalysisRun", backref="passports")

    __table_args__ = (
        Index(
            "uq_passports_member_run_active",
            "member_id",
            "run_id",
            unique=True,
            postgresql_where=(revoked_at.is_(None)),
            sqlite_where=(revoked_at.is_(None)),
        ),
    )
