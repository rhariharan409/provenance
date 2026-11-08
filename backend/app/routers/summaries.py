import logging
from typing import Any, Dict, List
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore
from app.models.members import Member
from app.models.projects import Project
from app.models.summaries import MemberSummary
from app.models.users import User, UserRole
from app.services.auth_access import (
    check_project_read_access,
    check_project_write_access,
    is_faculty_or_admin_on_project,
    is_reviewer_on_project,
)
from app.services.summary import generate_member_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["summaries"])


@router.post("/{id}/summaries/generate")
def generate_project_summaries(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Generates evidence-backed summaries for each member of the latest complete run.
    Owner or Admin only.
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_write_access(project, current_user)

    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run analysis first.",
        )

    scores = (
        db.query(ContributionScore)
        .filter(ContributionScore.run_id == latest_run.id)
        .all()
    )
    members_map = {
        m.id: m
        for m in db.query(Member).filter(Member.project_id == id).all()
    }

    results: List[Dict[str, Any]] = []

    for score in scores:
        member = members_map.get(score.member_id)
        if not member:
            continue

        text, method, citations = generate_member_summary(member, score, latest_run, db=db)

        # Upsert summary
        existing = (
            db.query(MemberSummary)
            .filter(
                MemberSummary.run_id == latest_run.id,
                MemberSummary.member_id == member.id,
            )
            .first()
        )
        if existing:
            existing.text = text
            existing.method = method
            existing.citations = citations
            db.commit()
            summary_obj = existing
        else:
            summary_obj = MemberSummary(
                run_id=latest_run.id,
                member_id=member.id,
                text=text,
                method=method,
                citations=citations,
            )
            db.add(summary_obj)
            db.commit()
            db.refresh(summary_obj)

        results.append({
            "id": str(summary_obj.id),
            "member_id": str(member.id),
            "member_name": member.display_name or member.github_login or "Member",
            "text": summary_obj.text,
            "method": summary_obj.method.value if hasattr(summary_obj.method, "value") else str(summary_obj.method),
            "citations": summary_obj.citations,
            "created_at": summary_obj.created_at.isoformat() if summary_obj.created_at else None,
        })

    return results


@router.get("/{id}/summaries")
def get_project_summaries(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Returns summaries for the latest run:
      - Owner, assigned faculty, and admin see all members' summaries.
      - A member sees only their own summary.
      - Others get 404.
    """
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    is_privileged = is_faculty_or_admin_on_project(project, current_user, db)

    # If not owner/faculty/admin, verify user is a member of this project
    user_member_id: Optional[uuid.UUID] = None
    if not is_privileged:
        user_member = (
            db.query(Member)
            .filter(Member.project_id == id, Member.user_id == current_user.id)
            .first()
        )
        if not user_member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        user_member_id = user_member.id

    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )
    if not latest_run:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"summaries": [], "needs_analysis": True},
            headers={"X-Needs-Analysis": "true"},
        )

    members_map = {
        m.id: m
        for m in db.query(Member).filter(Member.project_id == id).all()
    }

    query = db.query(MemberSummary).filter(MemberSummary.run_id == latest_run.id)
    if not is_privileged and user_member_id:
        query = query.filter(MemberSummary.member_id == user_member_id)

    summaries = query.all()

    return [
        {
            "id": str(s.id),
            "member_id": str(s.member_id),
            "member_name": members_map[s.member_id].display_name or members_map[s.member_id].github_login if s.member_id in members_map else "Member",
            "text": s.text,
            "method": s.method.value if hasattr(s.method, "value") else str(s.method),
            "citations": s.citations,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in summaries
    ]

