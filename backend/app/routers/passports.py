from datetime import datetime, timezone
import io
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
import segno
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore
from app.models.disputes import Dispute, DisputeStatus
from app.models.members import Member
from app.models.passports import Passport
from app.models.projects import Project
from app.models.users import User, UserRole
from app.services.passport import (
    build_snapshot,
    compute_seal,
    generate_passport_code,
    verify_seal,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["passports"])

# Simple in-memory rate limiter per IP: 60 requests per minute
_IP_REQUESTS: Dict[str, List[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 60


def _check_rate_limit(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _RATE_LIMIT_LOCK:
        timestamps = _IP_REQUESTS.get(client_ip, [])
        valid_timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW_SECONDS]
        if len(valid_timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            _IP_REQUESTS[client_ip] = valid_timestamps
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
            )
        valid_timestamps.append(now)
        _IP_REQUESTS[client_ip] = valid_timestamps


def _check_project_access(project: Optional[Project], user: User) -> Project:
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if user.role != UserRole.admin and project.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _compute_dispute_summary(db: Session, member_id: uuid.UUID, run_id: uuid.UUID) -> Dict[str, int]:
    disputes = db.query(Dispute).filter(
        Dispute.member_id == member_id,
        Dispute.run_id == run_id
    ).all()
    return {
        "open": sum(1 for d in disputes if d.status == DisputeStatus.open),
        "resolved": sum(1 for d in disputes if d.status == DisputeStatus.resolved),
        "rejected": sum(1 for d in disputes if d.status == DisputeStatus.rejected),
        "total": len(disputes),
    }


# ---------------------------------------------------------------------------
# Authenticated Passport Endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{id}/members/{member_id}/passport", status_code=status.HTTP_201_CREATED)
def publish_passport(
    id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Publishes a Contribution Passport for a member row.
    Allowed ONLY if members.user_id == current_user (admins may NOT publish for others).
    Idempotent: returns existing active passport for the same run if one exists.
    """
    # 1. Verify signing secret is configured
    if not settings.PASSPORT_SIGNING_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Passport signing is not configured on this server.",
        )

    # 2. Check project
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # 3. Check member
    member = db.query(Member).filter(Member.id == member_id, Member.project_id == id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    # Rule: Allowed ONLY if members.user_id == current user (admins may NOT publish for others)
    if not member.user_id or member.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only publish a passport for your own contributions.",
        )

    # 4. Require complete latest analysis run
    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.project_id == project.id, AnalysisRun.status == AnalysisRunStatus.complete)
        .order_by(AnalysisRun.started_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No completed analysis run found for this repository.",
        )

    # 5. Idempotent check: return active passport if already exists
    existing_passport = (
        db.query(Passport)
        .filter(
            Passport.member_id == member.id,
            Passport.run_id == latest_run.id,
            Passport.revoked_at.is_(None),
        )
        .first()
    )
    if existing_passport:
        return {
            "code": existing_passport.code,
            "url": f"{settings.PUBLIC_BASE_URL}/p/{existing_passport.code}",
            "already_published": True,
        }

    # 6. Fetch member's score and evidence
    score = (
        db.query(ContributionScore)
        .filter(ContributionScore.run_id == latest_run.id, ContributionScore.member_id == member.id)
        .first()
    )
    if not score:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No contribution score found for this member in the latest run.",
        )

    # 7. Fetch other members' scores
    other_scores_rows = (
        db.query(ContributionScore)
        .filter(ContributionScore.run_id == latest_run.id, ContributionScore.member_id != member.id)
        .all()
    )
    other_members_map = {
        m.id: m for m in db.query(Member).filter(Member.project_id == project.id).all()
    }

    other_members_scores: List[Dict[str, Any]] = []
    for s in other_scores_rows:
        other_m = other_members_map.get(s.member_id)
        other_members_scores.append({
            "github_login": other_m.github_login if other_m else None,
            "display_name": other_m.display_name if other_m else None,
            "share_percent": float(s.share_percent),
        })

    # 8. Check which other members have an active passport for this run
    active_passports = (
        db.query(Passport)
        .filter(Passport.run_id == latest_run.id, Passport.revoked_at.is_(None))
        .all()
    )
    active_member_ids = {p.member_id for p in active_passports}
    members_with_active_passports = {
        other_members_map[mid].github_login.lower()
        for mid in active_member_ids
        if mid in other_members_map and other_members_map[mid].github_login
    }

    # Evidence details
    ev = score.evidence or {}
    top_commits = ev.get("top_commits", [])
    top_files = ev.get("top_files", [])
    owned_modules = ev.get("owned_modules", [])

    # Stats calculation
    counted_commits = sum(a.commit_count for a in member.aliases if not a.is_bot)
    surviving_lines = int(score.signals.get("survival", {}).get("raw", 0))

    stats_dict = {
        "counted_commits": counted_commits,
        "surviving_lines": surviving_lines,
    }

    # Build snapshot
    snapshot = build_snapshot(
        repo_full_name=project.repo_full_name,
        repo_url=project.repo_url,
        head_sha=latest_run.head_sha,
        finished_at=latest_run.finished_at,
        member_login=member.github_login,
        member_display_name=member.display_name,
        share_percent=score.share_percent,
        confidence=score.confidence.value,
        flags=score.flags or [],
        signals=score.signals or {},
        stats=stats_dict,
        top_commits=top_commits,
        top_files=top_files,
        owned_modules=owned_modules,
        other_members_scores=other_members_scores,
        members_with_active_passports=members_with_active_passports,
        scoring_version=latest_run.scoring_version or "1.0",
        weights=latest_run.weights or {},
        history_since=project.history_since,
        project_flags=(latest_run.stats or {}).get("project_flags", []),
    )

    # Compute HMAC-SHA256 seal
    seal = compute_seal(snapshot, settings.PASSPORT_SIGNING_SECRET)
    code = generate_passport_code()

    passport = Passport(
        code=code,
        project_id=project.id,
        member_id=member.id,
        owner_user_id=current_user.id,
        run_id=latest_run.id,
        snapshot=snapshot,
        seal=seal,
        seal_version="1",
        created_at=datetime.now(timezone.utc),
    )
    db.add(passport)
    db.commit()

    return {
        "code": passport.code,
        "url": f"{settings.PUBLIC_BASE_URL}/p/{passport.code}",
        "already_published": False,
    }


@router.get("/passports/mine")
def get_my_passports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns current user's published passports with status, view count, and dispute summary.
    """
    passports = (
        db.query(Passport)
        .filter(Passport.owner_user_id == current_user.id)
        .order_by(Passport.created_at.desc())
        .all()
    )

    results = []
    for p in passports:
        dispute_summary = _compute_dispute_summary(db, p.member_id, p.run_id)
        score_data = p.snapshot.get("score", {}) if isinstance(p.snapshot, dict) else {}
        project_data = p.snapshot.get("project", {}) if isinstance(p.snapshot, dict) else {}

        results.append({
            "id": str(p.id),
            "code": p.code,
            "project_id": str(p.project_id),
            "member_id": str(p.member_id),
            "project_name": project_data.get("repo_full_name") or (p.project.name if p.project else "Unknown"),
            "share_percent": score_data.get("share_percent", 0.0),
            "status": "revoked" if p.revoked_at else "active",
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "view_count": p.view_count,
            "dispute_summary": dispute_summary,
            "url": f"{settings.PUBLIC_BASE_URL}/p/{p.code}",
        })

    return results


@router.delete("/passports/{code}")
def revoke_passport(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Revokes a passport. Allowed for passport owner or admin.
    Returns 404 for unknown codes or unauthorized users to prevent existence leakage.
    """
    passport = db.query(Passport).filter(Passport.code == code).first()
    if not passport:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passport not found.")

    if current_user.role != UserRole.admin and passport.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passport not found.")

    if not passport.revoked_at:
        passport.revoked_at = datetime.now(timezone.utc)
        db.commit()

    return {"status": "ok", "revoked": True, "message": "Passport revoked."}


# ---------------------------------------------------------------------------
# Public Passport Endpoints (No Authentication)
# ---------------------------------------------------------------------------

@router.get("/public/passports/{code}")
def get_public_passport(
    code: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Public passport document endpoint.
    No login. Returns 404 for unknown or revoked passports with identical bodies.
    """
    _check_rate_limit(request)

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"

    passport = db.query(Passport).filter(Passport.code == code).first()
    if not passport or passport.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passport not found.")

    # Increment view count
    passport.view_count += 1
    db.commit()

    dispute_summary = _compute_dispute_summary(db, passport.member_id, passport.run_id)

    return {
        "code": passport.code,
        "seal": passport.seal,
        "seal_version": passport.seal_version,
        "created_at": passport.created_at.isoformat() if passport.created_at else None,
        "snapshot": passport.snapshot,
        "dispute_summary": dispute_summary,
        "revoked": False,
    }


@router.get("/public/passports/{code}/verify")
def verify_public_passport(
    code: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Public verification endpoint: recomputes seal from stored snapshot.
    Never exposes the signing secret or expected seal.
    """
    _check_rate_limit(request)

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"

    passport = db.query(Passport).filter(Passport.code == code).first()
    if not passport or passport.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passport not found.")

    is_valid = verify_seal(passport.snapshot, passport.seal, settings.PASSPORT_SIGNING_SECRET)

    return {
        "valid": is_valid,
        "seal_version": passport.seal_version,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/public/passports/{code}/qr.svg")
def get_public_passport_qr(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public QR code endpoint returning SVG.
    """
    _check_rate_limit(request)

    passport = db.query(Passport).filter(Passport.code == code).first()
    if not passport or passport.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passport not found.")

    passport_url = f"{settings.PUBLIC_BASE_URL}/p/{passport.code}"
    qr = segno.make(passport_url, error="m")
    buff = io.BytesIO()
    qr.save(buff, kind="svg", border=2, dark="#1B1B19", light=None)
    svg_bytes = buff.getvalue()

    headers = {
        "Content-Type": "image/svg+xml",
        "Cache-Control": "public, max-age=3600",
        "X-Robots-Tag": "noindex, nofollow",
        "Referrer-Policy": "no-referrer",
    }
    return Response(content=svg_bytes, media_type="image/svg+xml", headers=headers)
