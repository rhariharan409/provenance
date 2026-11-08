from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Fingerprint(Base):
    __tablename__ = "fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hash: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    line_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    project = relationship("Project", backref="fingerprints")
    run = relationship("AnalysisRun", backref="fingerprints")

    __table_args__ = (
        Index("ix_fingerprints_hash_project", "hash", "project_id"),
    )


class OriginalityMatch(Base):
    __tablename__ = "originality_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    other_project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shared_fingerprints: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    shared_lines_estimate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    top_files: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship("Project", foreign_keys=[project_id], backref="originality_matches")
    other_project = relationship("Project", foreign_keys=[other_project_id])
    run = relationship("AnalysisRun", backref="originality_matches")

    __table_args__ = (
        UniqueConstraint("run_id", "other_project_id", name="uq_originality_run_other_project"),
    )

