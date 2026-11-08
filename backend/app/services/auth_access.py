from typing import Any, Optional
import uuid
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.faculty import ProjectFaculty
from app.models.projects import Project
from app.models.review_invitations import ReviewInvitation, InvitationStatus
from app.models.users import User, UserRole


def is_reviewer_on_project(project_or_id: Any, user: User, db: Session) -> bool:
    """Returns True if the user is an accepted reviewer or assigned faculty."""
    if not user or not project_or_id:
        return False

    pid = project_or_id.id if hasattr(project_or_id, "id") else project_or_id

    # 1. Accepted review invitation
    has_inv = (
        db.query(ReviewInvitation)
        .filter(
            ReviewInvitation.project_id == pid,
            (ReviewInvitation.invitee_user_id == user.id) | (ReviewInvitation.invitee_username.ilike(user.username)),
            ReviewInvitation.status == InvitationStatus.accepted,
        )
        .first()
        is not None
    )
    if has_inv:
        return True

    # 2. Project faculty assignment
    has_fac = (
        db.query(ProjectFaculty)
        .filter(
            ProjectFaculty.project_id == pid,
            ProjectFaculty.faculty_user_id == user.id,
        )
        .first()
        is not None
    )
    return has_fac


def check_project_read_access(project: Optional[Project], user: User, db: Session) -> Project:
    """
    Checks if a user has read access to a project:
      - Admin: access to all projects.
      - Owner: access to own projects.
      - Accepted Reviewers & Assigned Faculty: access to projects assigned via review_invitations or project_faculty.
      - Others: returns 404 (prevents existence leakage).
    """
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    if user.role == UserRole.admin or project.owner_id == user.id:
        return project

    if is_reviewer_on_project(project.id, user, db):
        return project

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


def check_project_write_access(project: Optional[Project], user: User) -> Project:
    """
    Checks if a user has write/modification access to a project:
      - Owner and Admin only.
      - Reviewers/Faculty cannot modify, recollect, assign identities, or delete projects.
    """
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    if user.role == UserRole.admin or project.owner_id == user.id:
        return project

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


def is_faculty_or_admin_on_project(project: Project, user: User, db: Session) -> bool:
    """Returns True if the user is an admin, the project owner, or an accepted reviewer/assigned faculty."""
    if user.role == UserRole.admin or project.owner_id == user.id:
        return True
    return is_reviewer_on_project(project.id, user, db)

