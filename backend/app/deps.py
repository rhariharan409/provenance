import uuid
from typing import Optional
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session
import jwt
from app.config import SESSION_COOKIE_NAME
from app.db import get_db
from app.models.users import User
from app.security import verify_session_token


def get_current_user(
    session_cookie: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db)
) -> User:
    if not session_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    try:
        user_id_str = verify_session_token(session_cookie)
        user_uuid = uuid.UUID(user_id_str)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user
