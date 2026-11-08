from datetime import datetime, timezone
import enum
from typing import Any, Dict, List
import uuid
from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SummaryMethod(str, enum.Enum):
    llm = "llm"
    rule_based = "rule_based"


class MemberSummary(Base):
    __tablename__ = "member_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    method: Mapped[SummaryMethod] = mapped_column(
        Enum(SummaryMethod, name="summary_method"),
        nullable=False,
        default=SummaryMethod.rule_based,
    )
    citations: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    run = relationship("AnalysisRun", backref="summaries")
    member = relationship("Member", backref="summaries")

    __table_args__ = (
        UniqueConstraint("run_id", "member_id", name="uq_member_summary_run_member"),
    )

