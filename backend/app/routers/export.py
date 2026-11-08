import csv
import io
import logging
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore
from app.models.members import Member
from app.models.projects import Project
from app.models.users import User
from app.services.auth_access import check_project_read_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["export"])

FORMULA_PREFIXES = ("=", "+", "-", "@")


def escape_csv_formula(val: Any) -> str:
    """
    Prevents CSV formula injection by prepending a single quote
    if a string cell starts with =, +, -, or @.
    """
    if val is None:
        return ""
    s = str(val)
    if s.startswith(FORMULA_PREFIXES):
        return f"'{s}"
    return s


@router.get("/{id}/export.csv")
def export_project_csv(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Exports project contribution scores as CSV.
    Accessible to project owner, assigned faculty, and admins.
    Columns:
      member display name, login, share_percent, confidence, flags (semicolon separated),
      counted commits, surviving lines, scoring_version, head_sha.
    Escapes CSV formula injection.
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_read_access(project, current_user, db)

    # Fetch latest complete run
    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed analysis run found for export.",
        )

    scores = (
        db.query(ContributionScore)
        .filter(ContributionScore.run_id == latest_run.id)
        .order_by(ContributionScore.share_percent.desc())
        .all()
    )

    members_map = {
        m.id: m
        for m in db.query(Member).filter(Member.project_id == id).all()
    }

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header row
    headers = [
        "member display name",
        "login",
        "share_percent",
        "confidence",
        "flags",
        "counted commits",
        "surviving lines",
        "scoring_version",
        "head_sha",
    ]
    writer.writerow(headers)

    for score in scores:
        member = members_map.get(score.member_id)
        display_name = member.display_name if member else ""
        login = member.github_login if member else "unlinked"
        share_percent = f"{score.share_percent:.2f}%"
        confidence = score.confidence.value if hasattr(score.confidence, "value") else str(score.confidence)

        # Flags semicolon-separated
        raw_flags = score.flags or []
        flag_codes = [f.get("code", str(f)) if isinstance(f, dict) else str(f) for f in raw_flags]
        flags_str = ";".join(flag_codes)

        # Counted commits & surviving lines
        counted_commits = getattr(member, "commit_count", 0)
        surviving_lines = int(score.signals.get("survival", {}).get("raw", 0)) if isinstance(score.signals, dict) else 0

        row = [
            escape_csv_formula(display_name),
            escape_csv_formula(login),
            escape_csv_formula(share_percent),
            escape_csv_formula(confidence),
            escape_csv_formula(flags_str),
            escape_csv_formula(counted_commits),
            escape_csv_formula(surviving_lines),
            escape_csv_formula(latest_run.scoring_version or "1.0"),
            escape_csv_formula(latest_run.head_sha or ""),
        ]
        writer.writerow(row)

    filename = f"provenance-{project.name}-scores.csv"
    csv_bytes = output.getvalue().encode("utf-8")

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
