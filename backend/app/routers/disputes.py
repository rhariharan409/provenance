from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.disputes import Dispute, DisputeStatus
from app.models.faculty import ProjectFaculty
from app.models.members import Member
from app.models.projects import Project
from app.models.users import User, UserRole
from app.services.auth_access import is_reviewer_on_project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["disputes"])


def _strip_control_characters(text: str) -> str:
    """Removes non-printable control characters except newline and tab."""
    return "".join(ch for ch in text if ch in "\n\t" or (ord(ch) >= 32 and ord(ch) != 127))


class CreateDisputeRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ResolveDisputeRequest(BaseModel):
    status: DisputeStatus
    resolution_note: Optional[str] = None


@router.post("/{id}/members/{member_id}/disputes", status_code=status.HTTP_201_CREATED)
def create_dispute(
    id: uuid.UUID,
    member_id: uuid.UUID,
    payload: CreateDisputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Raises a dispute regarding a member's contribution score.
    Allowed for:
      - Member's linked user
      - Project owner
      - System admin
    """
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    member = db.query(Member).filter(Member.id == member_id, Member.project_id == id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    # Authorization check
    is_admin = current_user.role == UserRole.admin
    is_owner = project.owner_id == current_user.id
    is_linked_user = member.user_id == current_user.id

    if not (is_admin or is_owner or is_linked_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # Validate text content
    clean_text = _strip_control_characters(payload.text).strip()
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dispute text cannot be empty.",
        )

    if len(clean_text) > settings.MAX_DISPUTE_TEXT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dispute text exceeds maximum allowed length of {settings.MAX_DISPUTE_TEXT} characters.",
        )

    # Check open disputes limit
    open_count = (
        db.query(Dispute)
        .filter(Dispute.raised_by == current_user.id, Dispute.status == DisputeStatus.open)
        .count()
    )
    if open_count >= settings.MAX_OPEN_DISPUTES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum open disputes limit ({settings.MAX_OPEN_DISPUTES_PER_USER}) reached.",
        )

    # Check completed latest analysis run
    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project.id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No completed analysis run found to dispute.",
        )

    dispute = Dispute(
        project_id=project.id,
        member_id=member.id,
        run_id=latest_run.id,
        raised_by=current_user.id,
        text=clean_text,
        status=DisputeStatus.open,
    )
    db.add(dispute)
    db.commit()
    db.refresh(dispute)

    return {
        "id": str(dispute.id),
        "project_id": str(dispute.project_id),
        "member_id": str(dispute.member_id),
        "status": dispute.status.value,
        "text": dispute.text,
        "created_at": dispute.created_at.isoformat(),
    }


@router.get("/{id}/disputes")
def list_disputes(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists disputes for a project:
      - Owner / admin see all disputes.
      - Other users see only disputes they raised.
    """
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    is_admin = current_user.role == UserRole.admin
    is_owner = project.owner_id == current_user.id
    is_reviewer = is_reviewer_on_project(project, current_user, db)

    query = db.query(Dispute).filter(Dispute.project_id == id)
    if not (is_admin or is_owner or is_reviewer):
        # Regular users only see disputes they raised
        query = query.filter(Dispute.raised_by == current_user.id)

    disputes = query.order_by(Dispute.created_at.desc()).all()

    members_map = {m.id: m for m in db.query(Member).filter(Member.project_id == id).all()}

    results = []
    for d in disputes:
        m = members_map.get(d.member_id)
        m_label = (m.display_name or m.github_login) if m else "Unknown member"
        results.append({
            "id": str(d.id),
            "project_id": str(d.project_id),
            "member_id": str(d.member_id),
            "member_name": m_label,
            "raised_by": str(d.raised_by),
            "raised_by_username": d.raiser.username if d.raiser else "unknown",
            "text": d.text,
            "status": d.status.value,
            "resolution_note": d.resolution_note,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
        })

    return results


@router.post("/{id}/disputes/{dispute_id}/resolve")
def resolve_dispute(
    id: uuid.UUID,
    dispute_id: uuid.UUID,
    payload: ResolveDisputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resolves or rejects a dispute.
    Allowed for owner or admin.
    The person who raised it cannot resolve it unless they are an admin.
    """
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    is_admin = current_user.role == UserRole.admin
    is_owner = project.owner_id == current_user.id
    is_reviewer = is_reviewer_on_project(project, current_user, db)

    if not (is_admin or is_owner or is_reviewer):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    dispute = db.query(Dispute).filter(Dispute.id == dispute_id, Dispute.project_id == id).first()
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found.")

    # Rule: Never the person who raised it if they are the same as the disputed member unless they are admin
    if not is_admin and dispute.raised_by == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot resolve a dispute you raised.",
        )

    dispute.status = payload.status
    dispute.resolution_note = payload.resolution_note.strip() if payload.resolution_note else None
    dispute.resolved_by = current_user.id
    dispute.resolved_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "ok",
        "dispute_id": str(dispute.id),
        "resolution_status": dispute.status.value,
        "message": "Dispute updated. Re-running repository analysis may be needed to adjust contribution scores.",
    }
