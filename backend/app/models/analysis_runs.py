import enum
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class AnalysisRunStatus(str, enum.Enum):
    running = "running"
    complete = "complete"
    failed = "failed"


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

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
    status: Mapped[AnalysisRunStatus] = mapped_column(
        Enum(AnalysisRunStatus, name="analysis_run_status", native_enum=True),
        default=AnalysisRunStatus.running,
        nullable=False
    )
    scoring_version: Mapped[str] = mapped_column(Text, default="1.0", nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    weights: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    project = relationship("Project", backref="analysis_runs")

    __table_args__ = (
        Index("ix_analysis_runs_project_id", "project_id"),
        Index("ix_analysis_runs_project_status", "project_id", "status"),
    )
