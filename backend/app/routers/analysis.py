from datetime import datetime
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore
from app.models.members import Member
from app.models.projects import Project
from app.models.users import User, UserRole
from app.services.analysis.flags import get_flag_message
from app.services.analysis.runner import run_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["analysis"])


def _check_project_access(
    project: Optional[Project],
    user: User,
    db: Optional[Session] = None,
    write: bool = False,
) -> Project:
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if user.role == UserRole.admin or project.owner_id == user.id:
        return project
    if not write and db is not None:
        from app.services.auth_access import is_reviewer_on_project
        if is_reviewer_on_project(project.id, user, db):
            return project
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


class AnalysisStatusResponse(BaseModel):
    analysis_status: str
    analysis_error: Optional[str] = None
    progress_step: Optional[str] = None
    progress_percent: Optional[int] = None


class MemberScoreItem(BaseModel):
    member_id: str
    display_name: Optional[str] = None
    github_login: Optional[str] = None
    share_percent: float
    confidence: str
    flags: List[str]
    signals: Dict[str, Any]


class ProjectScoresResponse(BaseModel):
    run_id: str
    project_id: str
    scoring_version: str
    head_sha: str
    finished_at: Optional[str] = None
    weights: Dict[str, float]
    stats: Dict[str, Any]
    project_flags: List[Dict[str, str]]
    members: List[MemberScoreItem]
    history_window: Optional[str] = None
    history_since: Optional[str] = None
    timing_stats: Optional[Dict[str, Any]] = None


class MemberEvidenceResponse(BaseModel):
    member_id: str
    display_name: Optional[str] = None
    github_login: Optional[str] = None
    share_percent: float
    confidence: str
    top_commits: List[Dict[str, Any]]
    top_files: List[Dict[str, Any]]
    owned_modules: List[Dict[str, Any]]
    summary_sentence: str
    signals: Dict[str, Any]


@router.post("/{id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis(
    id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == id).first()
    _check_project_access(project, current_user, write=True)

    if project.analysis_status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is already in progress for this repository.",
        )

    project.analysis_status = "running"
    project.analysis_error = None
    db.commit()

    background_tasks.add_task(run_analysis, project.id)
    return {
        "message": "Analysis started",
        "project_id": str(project.id),
        "status": "running",
    }


@router.get("/{id}/analysis/status", response_model=AnalysisStatusResponse)
def get_analysis_status(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == id).first()
    _check_project_access(project, current_user, db=db, write=False)
    return AnalysisStatusResponse(
        analysis_status=project.analysis_status or "pending",
        analysis_error=project.analysis_error,
        progress_step=project.progress_step,
        progress_percent=project.progress_percent,
    )


@router.get("/{id}/scores", response_model=ProjectScoresResponse)
def get_project_scores(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == id).first()
    _check_project_access(project, current_user, db=db, write=False)

    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project.id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )

    if not latest_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed analysis run found for this repository.",
        )

    score_rows = (
        db.query(ContributionScore)
        .filter(ContributionScore.run_id == latest_run.id)
        .all()
    )

    members_map = {
        m.id: m for m in db.query(Member).filter(Member.project_id == project.id).all()
    }

    # Sort score rows by share_percent descending
    score_rows.sort(key=lambda x: x.share_percent, reverse=True)

    member_items: List[MemberScoreItem] = []
    for s in score_rows:
        m = members_map.get(s.member_id)
        member_items.append(
            MemberScoreItem(
                member_id=str(s.member_id),
                display_name=m.display_name if m else None,
                github_login=m.github_login if m else None,
                share_percent=float(s.share_percent),
                confidence=s.confidence.value,
                flags=s.flags or [],
                signals=s.signals or {},
            )
        )

    stats = latest_run.stats or {}
    raw_p_flags = stats.get("project_flags", [])
    p_flags_formatted = [
        {"code": code, "message": get_flag_message(code)} for code in raw_p_flags
    ]

    finished_str = latest_run.finished_at.isoformat() if latest_run.finished_at else None

    return ProjectScoresResponse(
        run_id=str(latest_run.id),
        project_id=str(project.id),
        scoring_version=latest_run.scoring_version,
        head_sha=latest_run.head_sha,
        finished_at=finished_str,
        weights={k: float(v) for k, v in (latest_run.weights or {}).items()},
        stats=stats,
        project_flags=p_flags_formatted,
        members=member_items,
        history_window=project.history_window,
        history_since=project.history_since.isoformat() if project.history_since else None,
        timing_stats=project.timing_stats,
    )


@router.get("/{id}/scores/{member_id}/evidence", response_model=MemberEvidenceResponse)
def get_member_evidence(
    id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == id).first()
    _check_project_access(project, current_user, db=db, write=False)

    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project.id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )

    if not latest_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed analysis run found.",
        )

    score = (
        db.query(ContributionScore)
        .filter(
            ContributionScore.run_id == latest_run.id,
            ContributionScore.member_id == member_id,
        )
        .first()
    )

    if not score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Score record for member not found.",
        )

    member = db.query(Member).filter(Member.id == member_id).first()
    evidence = score.evidence or {}

    # Build GitHub commit URLs for top commits
    owner = project.github_owner or ""
    repo = project.github_repo or ""
    top_commits_raw = evidence.get("top_commits", [])
    top_commits_enriched = []
    for c in top_commits_raw:
        sha = c.get("sha", "")
        commit_url = f"https://github.com/{owner}/{repo}/commit/{sha}" if owner and repo and sha else ""
        top_commits_enriched.append({
            "sha": sha,
            "subject": c.get("subject", ""),
            "effective_lines": c.get("effective_lines", 0.0),
            "commit_url": commit_url,
        })

    top_files = evidence.get("top_files", [])
    owned_modules = evidence.get("owned_modules", [])

    # Compose plain sentence summarizing the score from numbers
    member_name = (member.display_name if member else None) or (member.github_login if member else None) or "This contributor"
    owned_count = len(owned_modules)
    surv_lines = int(score.signals.get("survival", {}).get("raw", 0))
    eff_lines = int(score.signals.get("effective_change", {}).get("raw", 0))

    summary_sentence = (
        f"{member_name} accounts for {score.share_percent}% of total contributions, "
        f"with {surv_lines} surviving lines, {eff_lines} effective lines changed, and leads {owned_count} module(s)."
    )

    return MemberEvidenceResponse(
        member_id=str(member_id),
        display_name=member.display_name if member else None,
        github_login=member.github_login if member else None,
        share_percent=float(score.share_percent),
        confidence=score.confidence.value,
        top_commits=top_commits_enriched,
        top_files=top_files,
        owned_modules=owned_modules,
        summary_sentence=summary_sentence,
        signals=score.signals or {},
    )

