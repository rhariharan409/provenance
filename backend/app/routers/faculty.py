import logging
from typing import Any, Dict, List
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore
from app.models.disputes import Dispute, DisputeStatus
from app.models.faculty import ProjectFaculty
from app.models.members import Member
from app.models.projects import Project
from app.models.users import User, UserRole
from app.services.auth_access import check_project_read_access, check_project_write_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["faculty"])


class AssignFacultyRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)


@router.post("/projects/{id}/faculty")
def assign_faculty_to_project(
    id: uuid.UUID,
    payload: AssignFacultyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Assigns an existing faculty user to a project.
    Owner or Admin only.
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_write_access(project, current_user)

    clean_username = payload.username.strip().lower()
    target_user = (
        db.query(User)
        .filter(User.username.ilike(clean_username))
        .first()
    )
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{payload.username}' not found.",
        )

    if target_user.role != UserRole.faculty and target_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User '{target_user.username}' is not a faculty member.",
        )

    # Check if already assigned
    existing = (
        db.query(ProjectFaculty)
        .filter(
            ProjectFaculty.project_id == id,
            ProjectFaculty.faculty_user_id == target_user.id,
        )
        .first()
    )
    if not existing:
        assignment = ProjectFaculty(
            project_id=id,
            faculty_user_id=target_user.id,
            assigned_by=current_user.id,
        )
        db.add(assignment)
        db.commit()

    return {
        "status": "ok",
        "faculty": {
            "id": str(target_user.id),
            "username": target_user.username,
            "display_name": target_user.display_name,
        },
    }


@router.delete("/projects/{id}/faculty/{user_id}")
def remove_faculty_from_project(
    id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Removes a faculty assignment from a project.
    Owner or Admin only.
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_write_access(project, current_user)

    assignment = (
        db.query(ProjectFaculty)
        .filter(
            ProjectFaculty.project_id == id,
            ProjectFaculty.faculty_user_id == user_id,
        )
        .first()
    )
    if assignment:
        db.delete(assignment)
        db.commit()

    return {"status": "ok", "message": "Faculty assignment removed."}


@router.get("/projects/{id}/faculty")
def list_project_faculty(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Lists faculty assigned to a project.
    Owner, assigned faculty, or Admin.
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_read_access(project, current_user, db)

    assignments = (
        db.query(ProjectFaculty)
        .filter(ProjectFaculty.project_id == id)
        .all()
    )

    return [
        {
            "id": str(a.id),
            "faculty_user_id": str(a.faculty_user_id),
            "user_id": str(a.faculty_user_id),
            "username": a.faculty_user.username if a.faculty_user else "unknown",
            "display_name": a.faculty_user.display_name if a.faculty_user else None,
            "assigned_by": str(a.assigned_by) if a.assigned_by else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "assigned_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in assignments
    ]


@router.get("/faculty/projects")
def list_faculty_assigned_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Returns assigned projects for faculty/admin with:
    member count, status, open disputes count, flags count.
    """
    if current_user.role not in (UserRole.faculty, UserRole.admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty access required.",
        )

    if current_user.role == UserRole.admin:
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
    else:
        assignments = (
            db.query(ProjectFaculty)
            .filter(ProjectFaculty.faculty_user_id == current_user.id)
            .all()
        )
        proj_ids = [a.project_id for a in assignments]
        projects = (
            db.query(Project)
            .filter(Project.id.in_(proj_ids))
            .order_by(Project.created_at.desc())
            .all()
        )

    results: List[Dict[str, Any]] = []
    for p in projects:
        member_count = db.query(Member).filter(Member.project_id == p.id).count()
        open_disputes_count = (
            db.query(Dispute)
            .filter(Dispute.project_id == p.id, Dispute.status == DisputeStatus.open)
            .count()
        )
        flags_count = 0
        latest_run = (
            db.query(AnalysisRun)
            .filter(AnalysisRun.project_id == p.id, AnalysisRun.status == AnalysisRunStatus.complete)
            .order_by(AnalysisRun.started_at.desc())
            .first()
        )
        if latest_run:
            scores = db.query(ContributionScore).filter(ContributionScore.run_id == latest_run.id).all()
            for s in scores:
                flags_count += len(s.flags or [])

        results.append({
            "id": str(p.id),
            "name": p.name,
            "repo_full_name": p.repo_full_name,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "member_count": member_count,
            "open_disputes_count": open_disputes_count,
            "flags_count": flags_count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "assigned_at": p.created_at.isoformat() if p.created_at else None,
        })

    return results
