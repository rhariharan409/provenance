import enum
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import Enum, ForeignKey, Index, Numeric, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class ScoreConfidence(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ContributionScore(Base):
    __tablename__ = "contribution_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    share_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    confidence: Mapped[ScoreConfidence] = mapped_column(
        Enum(ScoreConfidence, name="score_confidence", native_enum=True),
        nullable=False
    )
    signals: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    flags: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    run = relationship("AnalysisRun", backref="scores")
    project = relationship("Project", backref="scores")
    member = relationship("Member", backref="scores")

    __table_args__ = (
        UniqueConstraint("run_id", "member_id", name="uq_contribution_scores_run_member"),
        Index("ix_contribution_scores_project_id", "project_id"),
        Index("ix_contribution_scores_member_id", "member_id"),
    )
