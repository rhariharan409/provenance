import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import jwt
from app.config import settings

ALGORITHM = "HS256"
SESSION_DURATION = timedelta(days=7)


def create_session_token(
    user_id: Union[str, uuid.UUID],
    expires_delta: Optional[timedelta] = None
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta is not None else SESSION_DURATION)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.SESSION_SECRET, algorithm=ALGORITHM)


def verify_session_token(token: str) -> str:
    """
    Decodes and validates a session JWT token.
    Returns the user_id (sub) string if valid.
    Raises jwt.PyJWTError if expired, tampered, or invalid.
    """
    payload = jwt.decode(
        token,
        settings.SESSION_SECRET,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp"]}
    )
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise jwt.InvalidTokenError("Token missing subject")
    return user_id
