import logging
from pathlib import Path
import shutil
from typing import Any, Dict
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE_NAME, settings
from app.db import get_db
from app.deps import get_current_user
from app.models.disputes import Dispute
from app.models.faculty import ProjectFaculty
from app.models.members import Member
from app.models.passports import Passport
from app.models.projects import Project
from app.models.users import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account"])


class DeleteAccountRequest(BaseModel):
    confirm: str


@router.delete("/me")
def delete_my_account(
    payload: DeleteAccountRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Deletes the current user account and associated personal data in one transaction:
      - Revokes and deletes user's passports.
      - Deletes disputes raised by user.
      - Sets members.user_id to NULL for member rows linked to this user.
      - Deletes faculty assignments for this user.
      - Deletes projects owned by this user (including local bare clone directories).
      - Deletes the user record.
      - Clears session cookie.
      - Rejects if user is the last remaining administrator.
    """
    if payload.confirm != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation text mismatch. You must provide confirm='DELETE'.",
        )

    # Protect last remaining admin
    if current_user.role == UserRole.admin:
        admin_count = db.query(User).filter(User.role == UserRole.admin).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last remaining administrator account.",
            )

    user_id = current_user.id

    try:
        # 1. Delete passports owned by user
        db.query(Passport).filter(Passport.owner_user_id == user_id).delete()

        # 2. Delete disputes raised by user
        db.query(Dispute).filter(Dispute.raised_by == user_id).delete()

        # 3. Unlink member rows (set user_id = NULL)
        db.query(Member).filter(Member.user_id == user_id).update({Member.user_id: None})

        # 4. Delete faculty assignments
        db.query(ProjectFaculty).filter(ProjectFaculty.faculty_user_id == user_id).delete()

        # 5. Delete projects owned by user and their clone directories
        owned_projects = db.query(Project).filter(Project.owner_id == user_id).all()
        for proj in owned_projects:
            repo_path = Path(settings.REPO_STORAGE_PATH) / f"{proj.id}.git"
            if repo_path.exists():
                try:
                    shutil.rmtree(repo_path, ignore_errors=True)
                except Exception as exc:
                    logger.warning("Failed to delete repo folder %s: %s", repo_path, exc)
            db.delete(proj)

        # 6. Delete user
        db.delete(current_user)
        db.commit()

    except Exception as exc:
        db.rollback()
        logger.error("Failed to delete account for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account.",
        )

    # Clear session cookie
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        domain=None,
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )

    return {"status": "ok", "message": "Account and all associated personal data deleted."}


@router.get("/me/export")
def export_my_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Exports a machine-readable JSON snapshot of the user's stored account data:
    user profile (no secrets), owned projects, passports, and disputes raised.
    """
    user_data = {
        "id": str(current_user.id),
        "github_id": current_user.github_id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "email": current_user.email,
        "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
    }

    # Owned projects
    owned_projects = (
        db.query(Project)
        .filter(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    projects_list = [
        {
            "id": str(p.id),
            "name": p.name,
            "repo_full_name": p.repo_full_name,
            "repo_url": p.repo_url,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in owned_projects
    ]

    # Passports owned
    passports = (
        db.query(Passport)
        .filter(Passport.owner_user_id == current_user.id)
        .order_by(Passport.created_at.desc())
        .all()
    )
    passports_list = [
        {
            "code": p.code,
            "project_id": str(p.project_id),
            "member_id": str(p.member_id),
            "seal": p.seal,
            "seal_version": p.seal_version,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "revoked_at": p.revoked_at.isoformat() if p.revoked_at else None,
            "view_count": p.view_count,
            "snapshot": p.snapshot,
        }
        for p in passports
    ]

    # Disputes raised
    disputes = (
        db.query(Dispute)
        .filter(Dispute.raised_by == current_user.id)
        .order_by(Dispute.created_at.desc())
        .all()
    )
    disputes_list = [
        {
            "id": str(d.id),
            "project_id": str(d.project_id),
            "member_id": str(d.member_id),
            "text": d.text,
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            "resolution_note": d.resolution_note,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
        }
        for d in disputes
    ]

    return {
        "user": user_data,
        "projects_owned": projects_list,
        "passports": passports_list,
        "disputes_raised": disputes_list,
    }
