import logging
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone

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
from app.models.review_invitations import ReviewInvitation, InvitationStatus
from app.models.users import User, UserRole
from app.services.auth_access import check_project_read_access, check_project_write_access, is_reviewer_on_project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reviews"])


class InviteReviewerRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)


@router.get("/reviews/summary")
def get_reviews_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns pending review invitations count for the current user for tab badges.
    """
    pending_count = (
        db.query(ReviewInvitation)
        .filter(
            (ReviewInvitation.invitee_user_id == current_user.id)
            | (ReviewInvitation.invitee_username.ilike(current_user.username)),
            ReviewInvitation.status == InvitationStatus.pending,
        )
        .count()
    )
    return {"pending_count": pending_count}


@router.get("/reviews/invitations")
def list_my_review_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Lists pending review invitations for the signed-in user.
    """
    invitations = (
        db.query(ReviewInvitation)
        .filter(
            (ReviewInvitation.invitee_user_id == current_user.id)
            | (ReviewInvitation.invitee_username.ilike(current_user.username)),
            ReviewInvitation.status == InvitationStatus.pending,
        )
        .order_by(ReviewInvitation.created_at.desc())
        .all()
    )

    results = []
    for inv in invitations:
        proj = inv.project
        inviter = inv.inviter
        results.append({
            "id": str(inv.id),
            "project_id": str(inv.project_id),
            "project_name": proj.name if proj else "Unknown",
            "repo_name": proj.repo_full_name if proj else "Unknown",
            "repo_full_name": proj.repo_full_name if proj else "Unknown",
            "invited_by": inviter.username if inviter else "unknown",
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "status": inv.status.value,
        })
    return results


@router.post("/reviews/invitations/{id}/accept")
def accept_review_invitation(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Accepts a pending review invitation.
    """
    inv = (
        db.query(ReviewInvitation)
        .filter(
            ReviewInvitation.id == id,
            (ReviewInvitation.invitee_user_id == current_user.id)
            | (ReviewInvitation.invitee_username.ilike(current_user.username)),
        )
        .first()
    )
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found.",
        )

    inv.status = InvitationStatus.accepted
    inv.invitee_user_id = current_user.id
    inv.responded_at = datetime.now(timezone.utc)

    # Also mirror into project_faculty for backwards compatibility if user is faculty or admin
    existing_fac = (
        db.query(ProjectFaculty)
        .filter(
            ProjectFaculty.project_id == inv.project_id,
            ProjectFaculty.faculty_user_id == current_user.id,
        )
        .first()
    )
    if not existing_fac:
        fac = ProjectFaculty(
            project_id=inv.project_id,
            faculty_user_id=current_user.id,
            assigned_by=inv.inviter_user_id,
        )
        db.add(fac)

    db.commit()
    return {"status": "accepted", "ok": True, "message": "Invitation accepted."}


@router.post("/reviews/invitations/{id}/decline")
def decline_review_invitation(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Declines a pending review invitation.
    """
    inv = (
        db.query(ReviewInvitation)
        .filter(
            ReviewInvitation.id == id,
            (ReviewInvitation.invitee_user_id == current_user.id)
            | (ReviewInvitation.invitee_username.ilike(current_user.username)),
        )
        .first()
    )
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found.",
        )

    inv.status = InvitationStatus.declined
    inv.invitee_user_id = current_user.id
    inv.responded_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok", "message": "Invitation declined."}


@router.get("/reviews/projects")
def list_reviewed_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Returns projects where current user is an accepted reviewer or assigned faculty.
    """
    invitations = (
        db.query(ReviewInvitation)
        .filter(
            (ReviewInvitation.invitee_user_id == current_user.id)
            | (ReviewInvitation.invitee_username.ilike(current_user.username)),
            ReviewInvitation.status == InvitationStatus.accepted,
        )
        .all()
    )
    inv_map = {inv.project_id: inv for inv in invitations}

    fac_assignments = (
        db.query(ProjectFaculty)
        .filter(ProjectFaculty.faculty_user_id == current_user.id)
        .all()
    )
    fac_map = {f.project_id: f for f in fac_assignments}

    all_project_ids = list(set(list(inv_map.keys()) + list(fac_map.keys())))
    projects = (
        db.query(Project)
        .filter(Project.id.in_(all_project_ids))
        .order_by(Project.created_at.desc())
        .all()
    )

    results: List[Dict[str, Any]] = []
    for p in projects:
        inv = inv_map.get(p.id)
        fac = fac_map.get(p.id)
        accepted_at = None
        if inv and inv.responded_at:
            accepted_at = inv.responded_at.isoformat()
        elif inv and inv.created_at:
            accepted_at = inv.created_at.isoformat()
        elif fac and fac.created_at:
            accepted_at = fac.created_at.isoformat()

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
            "repo_name": p.repo_full_name,
            "repo_full_name": p.repo_full_name,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "member_count": member_count,
            "open_disputes_count": open_disputes_count,
            "flags_count": flags_count,
            "accepted_at": accepted_at,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return results


@router.post("/reviews/projects/{id}/leave")
def leave_project_review(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Allows a reviewer to leave a project review.
    """
    invitations = (
        db.query(ReviewInvitation)
        .filter(
            ReviewInvitation.project_id == id,
            (ReviewInvitation.invitee_user_id == current_user.id)
            | (ReviewInvitation.invitee_username.ilike(current_user.username)),
        )
        .all()
    )
    for inv in invitations:
        db.delete(inv)

    fac_assignments = (
        db.query(ProjectFaculty)
        .filter(
            ProjectFaculty.project_id == id,
            ProjectFaculty.faculty_user_id == current_user.id,
        )
        .all()
    )
    for fac in fac_assignments:
        db.delete(fac)

    db.commit()
    return {"status": "ok", "ok": True, "message": "Successfully left project review."}


@router.post("/projects/{id}/reviewers")
def invite_reviewer_to_project(
    id: uuid.UUID,
    payload: InviteReviewerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Invites a reviewer to a project.
    Owner or Admin only.
    Rejects owner's own username and inviting user's username with 'You cannot invite yourself.'
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_write_access(project, current_user)

    clean_username = payload.username.strip().lower()

    # Reject owner's own username and inviting user's username
    owner_username = ""
    if project.owner and project.owner.username:
        owner_username = project.owner.username.strip().lower()
    elif project.owner_id:
        owner_obj = db.query(User).filter(User.id == project.owner_id).first()
        if owner_obj and owner_obj.username:
            owner_username = owner_obj.username.strip().lower()

    if clean_username == current_user.username.strip().lower() or (owner_username and clean_username == owner_username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot invite yourself.",
        )

    target_user = (
        db.query(User)
        .filter(User.username.ilike(clean_username))
        .first()
    )

    # Check if invitation already exists
    existing = (
        db.query(ReviewInvitation)
        .filter(
            ReviewInvitation.project_id == id,
            ReviewInvitation.invitee_username.ilike(clean_username),
        )
        .first()
    )

    if existing:
        if existing.status == InvitationStatus.declined:
            existing.status = InvitationStatus.pending
            existing.responded_at = None
            existing.created_at = datetime.now(timezone.utc)
            db.commit()
            invitation = existing
        else:
            invitation = existing
    else:
        invitation = ReviewInvitation(
            project_id=id,
            inviter_user_id=current_user.id,
            invitee_user_id=target_user.id if target_user else None,
            invitee_username=clean_username,
            status=InvitationStatus.pending,
        )
        db.add(invitation)
        db.commit()

    return {
        "status": "ok",
        "id": str(invitation.id),
        "invitation_status": invitation.status.value,
        "reviewer": {
            "id": str(invitation.id),
            "invitee_username": invitation.invitee_username,
            "status": invitation.status.value,
            "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
        },
    }


@router.get("/projects/{id}/reviewers")
def list_project_reviewers(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Lists reviewers and review invitations for a project.
    Owner, accepted reviewers, or Admin.
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_read_access(project, current_user, db)

    invitations = (
        db.query(ReviewInvitation)
        .filter(ReviewInvitation.project_id == id)
        .order_by(ReviewInvitation.created_at.desc())
        .all()
    )

    results = []
    seen_usernames = set()
    for inv in invitations:
        seen_usernames.add(inv.invitee_username.lower())
        results.append({
            "id": str(inv.id),
            "invitee_username": inv.invitee_username,
            "username": inv.invitee_username,
            "display_name": inv.invitee.display_name if inv.invitee else None,
            "avatar_url": inv.invitee.avatar_url if inv.invitee else None,
            "status": inv.status.value,
            "invited_by": inv.inviter.username if inv.inviter else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "responded_at": inv.responded_at.isoformat() if inv.responded_at else None,
        })

    # Also include any project_faculty not already covered
    fac_assignments = (
        db.query(ProjectFaculty)
        .filter(ProjectFaculty.project_id == id)
        .all()
    )
    for fac in fac_assignments:
        u_name = fac.faculty_user.username if fac.faculty_user else "unknown"
        if u_name.lower() not in seen_usernames:
            seen_usernames.add(u_name.lower())
            results.append({
                "id": str(fac.id),
                "invitee_username": u_name,
                "username": u_name,
                "display_name": fac.faculty_user.display_name if fac.faculty_user else None,
                "avatar_url": fac.faculty_user.avatar_url if fac.faculty_user else None,
                "status": "accepted",
                "invited_by": str(fac.assigned_by) if fac.assigned_by else None,
                "created_at": fac.created_at.isoformat() if fac.created_at else None,
                "responded_at": fac.created_at.isoformat() if fac.created_at else None,
            })

    return results


@router.delete("/projects/{id}/reviewers/{reviewer_id}")
def remove_reviewer_from_project(
    id: uuid.UUID,
    reviewer_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Removes a reviewer invitation or assignment from a project.
    Owner or Admin only.
    """
    project = db.query(Project).filter(Project.id == id).first()
    check_project_write_access(project, current_user)

    inv = (
        db.query(ReviewInvitation)
        .filter(
            ReviewInvitation.project_id == id,
            (ReviewInvitation.id == reviewer_id) | (ReviewInvitation.invitee_user_id == reviewer_id),
        )
        .first()
    )
    if inv:
        db.delete(inv)

    fac = (
        db.query(ProjectFaculty)
        .filter(
            ProjectFaculty.project_id == id,
            (ProjectFaculty.id == reviewer_id) | (ProjectFaculty.faculty_user_id == reviewer_id),
        )
        .first()
    )
    if fac:
        db.delete(fac)

    db.commit()
    return {"status": "ok", "message": "Reviewer removed."}
