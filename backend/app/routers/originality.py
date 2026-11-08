import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.originality import OriginalityMatch
from app.models.projects import Project
from app.models.users import User, UserRole
from app.services.auth_access import check_project_read_access, check_project_write_access, is_faculty_or_admin_on_project
from app.services.originality import (
    ORIGINALITY_DISCLAIMER,
    compute_originality_matches,
    run_fingerprinting_for_project,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["originality"])


@router.post("/{id}/originality/run")
def run_originality_check(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Computes code fingerprints for the project head commit and identifies similarities
    across other projects owned by different users.
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
            detail="No completed analysis run found to run originality check.",
        )

    fp_count = run_fingerprinting_for_project(id, latest_run.id, db)
    matches = compute_originality_matches(id, latest_run.id, db)

    return {
        "status": "ok",
        "fingerprints_count": fp_count,
        "matches_count": len(matches),
        "message": "Originality check completed.",
    }


@router.get("/{id}/originality")
def get_originality_matches(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns originality comparison results.
      - Owner, assigned faculty, and admin see full match details.
      - A student sees only matches against projects they own; for other owners' projects,
        only a generic 'similarity found with another project' count is exposed with no names or paths.
    """
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    is_privileged = is_faculty_or_admin_on_project(project, current_user, db)

    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )
    if not latest_run:
        return {
            "status": "ok",
            "matches": [],
            "message": "No completed analysis run found.",
        }

    raw_matches = (
        db.query(OriginalityMatch)
        .filter(OriginalityMatch.run_id == latest_run.id)
        .order_by(OriginalityMatch.shared_lines_estimate.desc())
        .all()
    )

    other_projects_map = {
        p.id: p
        for p in db.query(Project).filter(
            Project.id.in_([m.other_project_id for m in raw_matches])
        ).all()
    }

    if is_privileged:
        # Full view for owner, assigned faculty, admin
        match_items = []
        for m in raw_matches:
            other_p = other_projects_map.get(m.other_project_id)
            match_items.append({
                "id": str(m.id),
                "other_project_id": str(m.other_project_id),
                "other_project_name": other_p.name if other_p else "Unknown project",
                "other_repo_full_name": other_p.repo_full_name if other_p else "Unknown repository",
                "shared_fingerprints": m.shared_fingerprints,
                "shared_lines_estimate": m.shared_lines_estimate,
                "top_files": m.top_files,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })

        return {
            "status": "ok",
            "heading": "Similarity found. Please review." if match_items else "No similarities found.",
            "matches": match_items,
            "disclaimer": ORIGINALITY_DISCLAIMER,
            "threshold_lines": settings.ORIGINALITY_MIN_SHARED_LINES,
        }

    # Student view: only own projects allowed full details
    student_matches = []
    redacted_count = 0

    for m in raw_matches:
        other_p = other_projects_map.get(m.other_project_id)
        if other_p and other_p.owner_id == current_user.id:
            student_matches.append({
                "id": str(m.id),
                "other_project_id": str(m.other_project_id),
                "other_project_name": other_p.name,
                "other_repo_full_name": other_p.repo_full_name,
                "shared_fingerprints": m.shared_fingerprints,
                "shared_lines_estimate": m.shared_lines_estimate,
                "top_files": m.top_files,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })
        else:
            redacted_count += 1

    return {
        "status": "ok",
        "heading": "Similarity found. Please review." if (student_matches or redacted_count > 0) else "No similarities found.",
        "matches": student_matches,
        "external_similarity_flag": redacted_count > 0,
        "external_similarity_count": redacted_count,
        "disclaimer": ORIGINALITY_DISCLAIMER,
        "threshold_lines": settings.ORIGINALITY_MIN_SHARED_LINES,
    }
