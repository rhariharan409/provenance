import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Contribution(Base):
    __tablename__ = "contributions"

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
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    commit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    project = relationship("Project", backref="contributions")
    user = relationship("User", backref="contributions")

    __table_args__ = (
        Index("ix_contributions_project_id", "project_id"),
    )
