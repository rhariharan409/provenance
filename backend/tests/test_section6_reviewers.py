import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import (
    User,
    UserRole,
    Project,
    ProjectStatus,
    ReviewInvitation,
    InvitationStatus,
)
from app.security import create_session_token


def make_client_for_user(user: User, db_session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set("provenance_session", token)
    return client


def test_invite_self_rejected(db_session):
    owner = User(
        github_id=11111,
        username="repo_owner",
        email="owner@example.com",
        role=UserRole.student,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    project = Project(
        owner_id=owner.id,
        name="test-proj",
        repo_full_name="repo_owner/test-proj",
        repo_url="https://github.com/repo_owner/test-proj",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    client = make_client_for_user(owner, db_session)

    # 1. Try inviting self with owner login
    resp = client.post(
        f"/projects/{project.id}/reviewers",
        json={"username": "repo_owner"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "You cannot invite yourself."

    # Case-insensitive self-invite check
    resp_case = client.post(
        f"/projects/{project.id}/reviewers",
        json={"username": "Repo_Owner"},
    )
    assert resp_case.status_code == 400
    assert resp_case.json()["detail"] == "You cannot invite yourself."


def test_reviews_summary_and_invitation_flow(db_session):
    owner = User(
        github_id=22221,
        username="owner2",
        email="owner2@example.com",
        role=UserRole.student,
    )
    reviewer = User(
        github_id=22222,
        username="reviewer1",
        email="rev1@example.com",
        role=UserRole.student,
    )
    db_session.add_all([owner, reviewer])
    db_session.commit()

    project = Project(
        owner_id=owner.id,
        name="rev-proj",
        repo_full_name="owner2/rev-proj",
        repo_url="https://github.com/owner2/rev-proj",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()

    rev_client = make_client_for_user(reviewer, db_session)

    # Initially 0 pending
    res = rev_client.get("/reviews/summary")
    assert res.status_code == 200
    assert res.json() == {"pending_count": 0}

    # Owner invites reviewer1
    owner_client = make_client_for_user(owner, db_session)
    invite_res = owner_client.post(
        f"/projects/{project.id}/reviewers",
        json={"username": "reviewer1"},
    )
    assert invite_res.status_code == 200
    data = invite_res.json()
    invitation_id = data["id"]
    assert data["reviewer"]["status"] == "pending"

    # Now pending count is 1
    res = rev_client.get("/reviews/summary")
    assert res.status_code == 200
    assert res.json() == {"pending_count": 1}

    # Reviewer lists invitations
    invs_res = rev_client.get("/reviews/invitations")
    assert invs_res.status_code == 200
    invs = invs_res.json()
    assert len(invs) == 1
    assert invs[0]["id"] == invitation_id
    assert invs[0]["repo_name"] == "owner2/rev-proj"
    assert invs[0]["invited_by"] == "owner2"

    # Reviewer accepts invitation
    acc_res = rev_client.post(f"/reviews/invitations/{invitation_id}/accept")
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "accepted"

    # Summary count is now 0
    res = rev_client.get("/reviews/summary")
    assert res.status_code == 200
    assert res.json() == {"pending_count": 0}

    # Project is now in reviewed projects list
    proj_res = rev_client.get("/reviews/projects")
    assert proj_res.status_code == 200
    projs = proj_res.json()
    assert len(projs) == 1
    assert projs[0]["id"] == str(project.id)
    assert projs[0]["repo_name"] == "owner2/rev-proj"

    # Reviewer can view project details
    proj_detail = rev_client.get(f"/projects/{project.id}")
    assert proj_detail.status_code == 200

    # Reviewer leaves review
    leave_res = rev_client.post(f"/reviews/projects/{project.id}/leave")
    assert leave_res.status_code == 200
    assert leave_res.json()["ok"] is True

    # Now reviewed projects is empty
    proj_res = rev_client.get("/reviews/projects")
    assert proj_res.status_code == 200
    assert len(proj_res.json()) == 0

    # Project detail is 404 for ex-reviewer
    proj_detail = rev_client.get(f"/projects/{project.id}")
    assert proj_detail.status_code == 404


def test_invitation_decline_flow(db_session):
    owner = User(
        github_id=33331,
        username="owner3",
        email="owner3@example.com",
        role=UserRole.student,
    )
    reviewer = User(
        github_id=33332,
        username="reviewer_decline",
        email="rev_dec@example.com",
        role=UserRole.student,
    )
    db_session.add_all([owner, reviewer])
    db_session.commit()

    project = Project(
        owner_id=owner.id,
        name="decline-proj",
        repo_full_name="owner3/decline-proj",
        repo_url="https://github.com/owner3/decline-proj",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()

    owner_client = make_client_for_user(owner, db_session)
    invite_res = owner_client.post(
        f"/projects/{project.id}/reviewers",
        json={"username": "reviewer_decline"},
    )
    invitation_id = invite_res.json()["id"]

    rev_client = make_client_for_user(reviewer, db_session)
    res = rev_client.get("/reviews/summary")
    assert res.json() == {"pending_count": 1}

    # Decline invitation
    dec_res = rev_client.post(f"/reviews/invitations/{invitation_id}/decline")
    assert dec_res.status_code == 200

    # Summary is now 0
    res = rev_client.get("/reviews/summary")
    assert res.json() == {"pending_count": 0}

    # Non-reviewer gets 404
    proj_detail = rev_client.get(f"/projects/{project.id}")
    assert proj_detail.status_code == 404
