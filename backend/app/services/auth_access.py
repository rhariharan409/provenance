from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.faculty import ProjectFaculty
from app.models.projects import Project
from app.models.users import User, UserRole


def check_project_read_access(project: Optional[Project], user: User, db: Session) -> Project:
    """
    Checks if a user has read access to a project:
      - Admin: access to all projects.
      - Owner: access to own projects.
      - Assigned Faculty: access to projects assigned via project_faculty.
      - Others / Unassigned Faculty: returns 404 (prevents existence leakage).
    """
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    if user.role == UserRole.admin or project.owner_id == user.id:
        return project

    if user.role == UserRole.faculty:
        is_assigned = (
            db.query(ProjectFaculty)
            .filter(
                ProjectFaculty.project_id == project.id,
                ProjectFaculty.faculty_user_id == user.id,
            )
            .first()
            is not None
        )
        if is_assigned:
            return project

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


def check_project_write_access(project: Optional[Project], user: User) -> Project:
    """
    Checks if a user has write/modification access to a project:
      - Owner and Admin only.
      - Faculty cannot modify, recollect, assign identities, or delete projects.
    """
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    if user.role == UserRole.admin or project.owner_id == user.id:
        return project

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")


def is_faculty_or_admin_on_project(project: Project, user: User, db: Session) -> bool:
    """Returns True if the user is an admin, the project owner, or assigned faculty."""
    if user.role == UserRole.admin or project.owner_id == user.id:
        return True
    if user.role == UserRole.faculty:
        return (
            db.query(ProjectFaculty)
            .filter(
                ProjectFaculty.project_id == project.id,
                ProjectFaculty.faculty_user_id == user.id,
            )
            .first()
            is not None
        )
    return False
