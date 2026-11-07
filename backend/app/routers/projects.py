from datetime import datetime, timezone
import os
import shutil
from typing import List, Optional
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models.author_aliases import AliasSource, AuthorAlias
from app.models.commits import Commit
from app.models.contributions import Contribution
from app.models.members import Member
from app.models.projects import Project, ProjectStatus
from app.models.pull_requests import PullRequest, Review
from app.models.users import User, UserRole
from app.services.collector import run_collection, validate_and_parse_github_url
from app.services.github_client import GitHubClient, RepoAccessError

router = APIRouter(prefix="/projects", tags=["projects"])


# Request / Response Schemas
class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repo_url: str = Field(..., description="GitHub repository URL")


class AssignAliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: uuid.UUID


class MergeMembersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_member_id: uuid.UUID
    target_member_id: uuid.UUID


def check_project_access(project: Optional[Project], user: User) -> Project:
    """
    Enforces authorization: users see only their own projects (admins: all).
    Returns 404 if project does not exist or user is unauthorized.
    """
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if user.role != UserRole.admin and project.owner_id != user.id:
        # Return 404 rather than 403 to prevent existence leakage
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: CreateProjectRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Validates URL, checks user limits and access, creates project, and triggers collection.
    """
    try:
        owner, repo, canonical_url = validate_and_parse_github_url(payload.repo_url)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))

    # Enforce MAX_PROJECTS_PER_USER
    user_project_count = db.query(func.count(Project.id)).filter(
        Project.owner_id == current_user.id
    ).scalar() or 0
    if user_project_count >= settings.MAX_PROJECTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project limit reached ({settings.MAX_PROJECTS_PER_USER} projects max)."
        )

    # Enforce max 2 concurrent runs per user
    user_analyzing_count = db.query(func.count(Project.id)).filter(
        Project.owner_id == current_user.id,
        Project.status == ProjectStatus.analyzing
    ).scalar() or 0
    if user_analyzing_count >= 2:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent repository collections in progress."
        )

    # Pre-flight repo access resolution
    client = GitHubClient()
    auth_res = client.resolve_auth(owner, repo)

    try:
        meta, _ = client.verify_and_get_metadata(
            owner=owner,
            repo=repo,
            submitting_username=current_user.username,
            token=auth_res.token
        )
    except RepoAccessError as rae:
        if rae.code == "app_not_installed":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "code": "app_not_installed",
                    "message": rae.message,
                    "install_url": rae.install_url
                }
            )
        raise HTTPException(status_code=rae.status_code, detail=rae.message)

    repo_full_name = f"{owner}/{repo}"

    # Check if this owner already added this repo
    existing = db.query(Project).filter(
        Project.owner_id == current_user.id,
        func.lower(Project.repo_full_name) == repo_full_name.lower()
    ).first()

    if existing:
        if existing.status == ProjectStatus.analyzing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Repository is already being analyzed."
            )
        project = existing
        project.status = ProjectStatus.pending
        project.error_message = None
    else:
        project = Project(
            owner_id=current_user.id,
            repo_url=canonical_url,
            repo_full_name=repo_full_name,
            name=repo,
            description=meta.get("description"),
            github_owner=owner,
            github_repo=repo,
            default_branch=meta.get("default_branch") or "main",
            is_private=bool(meta.get("private", False)),
            status=ProjectStatus.pending
        )
        db.add(project)

    db.commit()
    db.refresh(project)

    # Launch collection task
    background_tasks.add_task(run_collection, project.id)

    return {
        "id": str(project.id),
        "name": project.name,
        "repo_full_name": project.repo_full_name,
        "repo_url": project.repo_url,
        "description": project.description,
        "status": project.status.value,
        "is_private": project.is_private,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


@router.get("")
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns current user's projects (admins see all).
    """
    query = db.query(Project)
    if current_user.role != UserRole.admin:
        query = query.filter(Project.owner_id == current_user.id)

    projects = query.order_by(Project.created_at.desc()).all()

    result = []
    for p in projects:
        result.append({
            "id": str(p.id),
            "name": p.name,
            "repo_full_name": p.repo_full_name,
            "repo_url": p.repo_url,
            "description": p.description,
            "status": p.status.value,
            "is_private": p.is_private,
            "commit_total": p.commit_total,
            "last_collected_at": p.last_collected_at.isoformat() if p.last_collected_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return result


@router.get("/{id}")
def get_project_detail(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    members_count = db.query(func.count(Member.id)).filter(Member.project_id == id).scalar() or 0
    prs_count = db.query(func.count(PullRequest.id)).filter(PullRequest.project_id == id).scalar() or 0

    return {
        "id": str(project.id),
        "name": project.name,
        "repo_full_name": project.repo_full_name,
        "repo_url": project.repo_url,
        "description": project.description,
        "status": project.status.value,
        "is_private": project.is_private,
        "default_branch": project.default_branch,
        "commit_total": project.commit_total,
        "warnings": project.warnings,
        "error_message": project.error_message,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "last_collected_at": project.last_collected_at.isoformat() if project.last_collected_at else None,
        "members_count": members_count,
        "prs_count": prs_count,
    }


@router.post("/{id}/recollect")
def recollect_project(
    id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    if project.status == ProjectStatus.analyzing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository is already being analyzed."
        )

    project.status = ProjectStatus.pending
    project.error_message = None
    db.commit()

    background_tasks.add_task(run_collection, project.id)
    return {"status": "ok", "project_status": project.status.value}


@router.delete("/{id}")
def delete_project(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    # Delete on-disk bare clone
    if project.clone_path and os.path.exists(project.clone_path):
        shutil.rmtree(project.clone_path, ignore_errors=True)

    db.delete(project)
    db.commit()
    return {"status": "ok"}


@router.get("/{id}/members")
def get_project_members(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    members = db.query(Member).filter(Member.project_id == id).all()

    # Pre-fetch PRs and reviews count for efficiency
    all_prs = db.query(PullRequest.author_login).filter(PullRequest.project_id == id).all()
    pr_counts = {}
    for (author,) in all_prs:
        if author:
            pr_counts[author.lower()] = pr_counts.get(author.lower(), 0) + 1

    all_reviews = (
        db.query(Review.reviewer_login)
        .join(PullRequest, PullRequest.id == Review.pull_request_id)
        .filter(PullRequest.project_id == id)
        .all()
    )
    rev_counts = {}
    for (reviewer,) in all_reviews:
        if reviewer:
            rev_counts[reviewer.lower()] = rev_counts.get(reviewer.lower(), 0) + 1

    result = []
    for m in members:
        aliases_list = []
        alias_ids = [a.id for a in m.aliases]

        # Calculate additions, deletions, first/last commit
        stats = (
            db.query(
                func.sum(Commit.additions),
                func.sum(Commit.deletions),
                func.min(Commit.authored_at),
                func.max(Commit.authored_at),
            )
            .filter(Commit.project_id == id, Commit.alias_id.in_(alias_ids))
            .first()
        ) if alias_ids else (0, 0, None, None)

        adds = stats[0] or 0
        dels = stats[1] or 0
        first_dt = stats[2]
        last_dt = stats[3]

        login_clean = (m.github_login or "").lower()
        prs_opened = pr_counts.get(login_clean, 0)
        reviews_given = rev_counts.get(login_clean, 0)

        total_commits = 0
        for a in m.aliases:
            if not a.is_bot:
                total_commits += a.commit_count
            aliases_list.append({
                "id": str(a.id),
                "name": a.name,
                "email": a.email,
                "source": a.source.value,
                "is_bot": a.is_bot,
                "commit_count": a.commit_count,
            })

        result.append({
            "id": str(m.id),
            "login": m.github_login,
            "display_name": m.display_name,
            "commit_count": total_commits,
            "additions": adds,
            "deletions": dels,
            "pull_requests_opened": prs_opened,
            "reviews_given": reviews_given,
            "first_commit_at": first_dt.isoformat() if first_dt else None,
            "last_commit_at": last_dt.isoformat() if last_dt else None,
            "aliases": aliases_list,
        })

    # Sort by commit_count desc
    result.sort(key=lambda x: x["commit_count"], reverse=True)
    return result


@router.get("/{id}/aliases")
def get_project_aliases(
    id: uuid.UUID,
    linked: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    query = db.query(AuthorAlias).filter(AuthorAlias.project_id == id)
    if linked is False:
        query = query.filter(AuthorAlias.member_id.is_(None))
    elif linked is True:
        query = query.filter(AuthorAlias.member_id.isnot(None))

    aliases = query.order_by(AuthorAlias.commit_count.desc()).all()
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "email": a.email,
            "member_id": str(a.member_id) if a.member_id else None,
            "source": a.source.value,
            "is_bot": a.is_bot,
            "commit_count": a.commit_count,
        }
        for a in aliases
    ]


@router.post("/{id}/aliases/{alias_id}/assign")
def assign_alias(
    id: uuid.UUID,
    alias_id: uuid.UUID,
    payload: AssignAliasRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    alias = db.query(AuthorAlias).filter(
        AuthorAlias.id == alias_id,
        AuthorAlias.project_id == id
    ).first()
    if not alias:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alias not found.")

    member = db.query(Member).filter(
        Member.id == payload.member_id,
        Member.project_id == id
    ).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    old_member_id = alias.member_id
    alias.member_id = member.id
    alias.source = AliasSource.manual
    alias.assigned_by = current_user.id
    alias.assigned_at = datetime.now(timezone.utc)
    db.commit()

    # Recompute contributions for affected member(s)
    affected_member_ids = {member.id}
    if old_member_id:
        affected_member_ids.add(old_member_id)

    for m_id in affected_member_ids:
        m = db.query(Member).filter(Member.id == m_id).first()
        if m:
            c_count = sum(a.commit_count for a in m.aliases if not a.is_bot)
            contrib = None
            if m.user_id:
                contrib = db.query(Contribution).filter(
                    Contribution.project_id == id,
                    Contribution.user_id == m.user_id
                ).first()
            if not contrib and m.github_login:
                contrib = db.query(Contribution).filter(
                    Contribution.project_id == id,
                    Contribution.github_login == m.github_login
                ).first()
            if contrib:
                contrib.commit_count = c_count
            else:
                db.add(Contribution(
                    project_id=id,
                    user_id=m.user_id,
                    github_login=m.github_login or "unknown",
                    commit_count=c_count
                ))
    db.commit()

    return {"status": "ok", "alias_id": str(alias.id), "member_id": str(member.id)}


@router.post("/{id}/members/merge")
def merge_members(
    id: uuid.UUID,
    payload: MergeMembersRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    if payload.source_member_id == payload.target_member_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and target member cannot be the same."
        )

    source_member = db.query(Member).filter(
        Member.id == payload.source_member_id,
        Member.project_id == id
    ).first()
    target_member = db.query(Member).filter(
        Member.id == payload.target_member_id,
        Member.project_id == id
    ).first()

    if not source_member or not target_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both members not found."
        )

    # Move all aliases pointing to source_member to target_member
    db.query(AuthorAlias).filter(
        AuthorAlias.project_id == id,
        AuthorAlias.member_id == source_member.id
    ).update({
        AuthorAlias.member_id: target_member.id,
        AuthorAlias.source: AliasSource.manual,
        AuthorAlias.assigned_by: current_user.id,
        AuthorAlias.assigned_at: datetime.now(timezone.utc)
    }, synchronize_session="fetch")
    db.flush()

    # Delete source member contribution row
    db.query(Contribution).filter(
        Contribution.project_id == id,
        Contribution.github_login == source_member.github_login
    ).delete()

    db.delete(source_member)
    db.commit()

    # Recompute target member contributions
    c_count = sum(a.commit_count for a in target_member.aliases if not a.is_bot)
    contrib = None
    if target_member.user_id:
        contrib = db.query(Contribution).filter(
            Contribution.project_id == id,
            Contribution.user_id == target_member.user_id
        ).first()
    if not contrib and target_member.github_login:
        contrib = db.query(Contribution).filter(
            Contribution.project_id == id,
            Contribution.github_login == target_member.github_login
        ).first()

    if contrib:
        contrib.commit_count = c_count
    else:
        db.add(Contribution(
            project_id=id,
            user_id=target_member.user_id,
            github_login=target_member.github_login or "unknown",
            commit_count=c_count
        ))
    db.commit()

    return {"status": "ok"}


@router.get("/{id}/commits")
def get_project_commits(
    id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    check_project_access(project, current_user)

    commits = (
        db.query(Commit)
        .filter(Commit.project_id == id)
        .order_by(Commit.authored_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(c.id),
            "sha": c.sha,
            "author_name": c.author_name,
            "author_email": c.author_email,
            "authored_at": c.authored_at.isoformat() if c.authored_at else None,
            "subject": c.subject,
            "additions": c.additions,
            "deletions": c.deletions,
            "files_changed": c.files_changed,
        }
        for c in commits
    ]
