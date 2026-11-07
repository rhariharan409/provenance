import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
import httpx

from app.config import OAUTH_STATE_COOKIE_NAME, SESSION_COOKIE_NAME, settings
from app.db import get_db
from app.deps import get_current_user
from app.models.users import User, UserRole
from app.security import create_session_token

router = APIRouter(tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
OAUTH_SCOPES = "read:user user:email"


@router.get("/auth/github/login")
def github_login():
    """
    Generates a secure state parameter, stores it in an httpOnly cookie,
    and redirects user to GitHub OAuth authorization.
    """
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": OAUTH_SCOPES,
        "state": state,
    }
    url = f"{GITHUB_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    response = RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        max_age=600,  # 10 minutes
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/"
    )
    return response


@router.get("/auth/github/callback")
async def github_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    oauth_state: Optional[str] = Cookie(None, alias=OAUTH_STATE_COOKIE_NAME),
    db: Session = Depends(get_db)
):
    """
    Validates OAuth state, exchanges code for access token, fetches profile and email,
    upserts user, and establishes session. Never logs tokens or secrets.
    """
    auth_failed_redirect = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/?error=auth_failed",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )

    if error or not code or not state or not oauth_state or state != oauth_state:
        return auth_failed_redirect

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_REDIRECT_URI,
                }
            )

            if token_response.status_code != 200:
                return auth_failed_redirect

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return auth_failed_redirect

            gh_headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            user_response = await client.get(GITHUB_USER_URL, headers=gh_headers)
            if user_response.status_code != 200:
                return auth_failed_redirect

            gh_user = user_response.json()
            github_id = gh_user.get("id")
            username = gh_user.get("login")
            display_name = gh_user.get("name")
            avatar_url = gh_user.get("avatar_url")
            email = gh_user.get("email")

            if not github_id or not username:
                return auth_failed_redirect

            # If email is private, fetch primary verified email from emails endpoint
            if not email:
                emails_response = await client.get(GITHUB_EMAILS_URL, headers=gh_headers)
                if emails_response.status_code == 200:
                    email_list = emails_response.json()
                    if isinstance(email_list, list):
                        for item in email_list:
                            if item.get("primary") and item.get("verified"):
                                email = item.get("email")
                                break
                            if item.get("primary") and not email:
                                email = item.get("email")

        # Database upsert
        now = datetime.now(timezone.utc)
        is_admin = username.lower() in settings.admin_usernames

        user = db.query(User).filter(User.github_id == github_id).first()
        if user:
            user.username = username
            user.display_name = display_name
            user.avatar_url = avatar_url
            if email:
                user.email = email
            if is_admin:
                user.role = UserRole.admin
            user.last_login_at = now
        else:
            user = User(
                github_id=github_id,
                username=username,
                display_name=display_name,
                avatar_url=avatar_url,
                email=email,
                role=UserRole.admin if is_admin else UserRole.student,
                last_login_at=now,
            )
            db.add(user)

        db.commit()
        db.refresh(user)

        # Issue session token
        session_token = create_session_token(user.id)

        dashboard_redirect = RedirectResponse(
            url=f"{settings.FRONTEND_URL}/dashboard",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
        dashboard_redirect.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            max_age=7 * 24 * 3600,  # 7 days
            httponly=True,
            samesite="lax",
            secure=settings.is_production,
            path="/"
        )
        dashboard_redirect.delete_cookie(key=OAUTH_STATE_COOKIE_NAME, path="/")
        return dashboard_redirect

    except Exception:
        db.rollback()
        return auth_failed_redirect


@router.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "github_id": current_user.github_id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "email": current_user.email,
        "role": current_user.role.value,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
    }


@router.post("/auth/logout")
def logout():
    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return response
