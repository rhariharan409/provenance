import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.users import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class UpdateRoleRequest(BaseModel):
    role: UserRole


@router.get("/users")
def list_admin_users(
    query: Optional[str] = Query(None, description="Search by username or display name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Lists users in the system. Admin only.
    Never returns email to non-admins.
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    db_query = db.query(User)
    if query and query.strip():
        term = f"%{query.strip()}%"
        db_query = db_query.filter(
            or_(
                User.username.ilike(term),
                User.display_name.ilike(term),
            )
        )

    users = db_query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    return [
        {
            "id": str(u.id),
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "email": u.email,
        }
        for u in users
    ]


@router.patch("/users/{user_id}/role")
def update_user_role(
    user_id: uuid.UUID,
    payload: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Updates a user's role. Admin only.
    Rules:
      - Cannot demote the last remaining admin.
      - Cannot change own role to a lower one.
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    new_role = payload.role

    # Rule: cannot change own role to a lower one
    if target_user.id == current_user.id and new_role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote your own administrator account.",
        )

    # Rule: cannot demote the last remaining admin
    if target_user.role == UserRole.admin and new_role != UserRole.admin:
        admin_count = db.query(User).filter(User.role == UserRole.admin).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last remaining administrator.",
            )

    target_user.role = new_role
    db.commit()
    db.refresh(target_user)

    return {
        "id": str(target_user.id),
        "username": target_user.username,
        "display_name": target_user.display_name,
        "role": target_user.role.value if hasattr(target_user.role, "value") else str(target_user.role),
        "created_at": target_user.created_at.isoformat() if target_user.created_at else None,
    }
