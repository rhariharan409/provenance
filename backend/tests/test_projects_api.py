import uuid
import pytest
from app.config import settings
from app.models.author_aliases import AliasSource, AuthorAlias
from app.models.members import Member
from app.models.projects import Project, ProjectStatus


def test_projects_api_unauthenticated(client):
    # GET /projects without token returns 401
    resp = client.get("/projects")
    assert resp.status_code == 401

    # POST /projects without token returns 401
    resp = client.post("/projects", json={"repo_url": "https://github.com/owner/repo"})
    assert resp.status_code == 401


def test_user_cannot_see_other_users_project_returns_404(
    authenticated_client, other_client, admin_client, other_user, db_session
):
    # Create project owned by other_user
    other_proj = Project(
        owner_id=other_user.id,
        repo_url="https://github.com/other/secret-repo.git",
        repo_full_name="other/secret-repo",
        name="secret-repo",
        status=ProjectStatus.ready,
    )
    db_session.add(other_proj)
    db_session.commit()
    db_session.refresh(other_proj)

    # 1. Other user can view it
    res = other_client.get(f"/projects/{other_proj.id}")
    assert res.status_code == 200

    # 2. Main test_user receives 404 (not 403, preventing existence leakage)
    res = authenticated_client.get(f"/projects/{other_proj.id}")
    assert res.status_code == 404

    res = authenticated_client.get(f"/projects/{other_proj.id}/members")
    assert res.status_code == 404

    res = authenticated_client.delete(f"/projects/{other_proj.id}")
    assert res.status_code == 404

    # 3. Admin can view it
    res = admin_client.get(f"/projects/{other_proj.id}")
    assert res.status_code == 200


def test_owner_can_assign_alias_and_merge_members(
    authenticated_client, test_user, db_session
):
    project = Project(
        owner_id=test_user.id,
        repo_url="https://github.com/teststudent/sample-app.git",
        repo_full_name="teststudent/sample-app",
        name="sample-app",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()

    # Create two members
    m1 = Member(project_id=project.id, github_login="m1_login", display_name="Member One")
    m2 = Member(project_id=project.id, github_login="m2_login", display_name="Member Two")
    db_session.add_all([m1, m2])
    db_session.commit()

    # Create unlinked alias
    alias = AuthorAlias(
        project_id=project.id,
        name="Legacy Name",
        email="legacy@example.com",
        source=AliasSource.noreply,
        commit_count=7,
        member_id=None,
    )
    db_session.add(alias)
    db_session.commit()

    # 1. Assign alias to m1
    assign_res = authenticated_client.post(
        f"/projects/{project.id}/aliases/{alias.id}/assign",
        json={"member_id": str(m1.id)},
    )
    assert assign_res.status_code == 200
    db_session.refresh(alias)
    assert alias.member_id == m1.id
    assert alias.source == AliasSource.manual
    assert alias.assigned_by == test_user.id

    # 2. Merge m1 into m2
    merge_res = authenticated_client.post(
        f"/projects/{project.id}/members/merge",
        json={
            "source_member_id": str(m1.id),
            "target_member_id": str(m2.id),
        },
    )
    assert merge_res.status_code == 200

    # m1 should be deleted, alias moved to m2
    m1_db = db_session.query(Member).filter(Member.id == m1.id).first()
    assert m1_db is None

    db_session.refresh(alias)
    assert alias.member_id == m2.id


def test_project_limit_enforced(authenticated_client, test_user, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAX_PROJECTS_PER_USER", 2)

    # Add 2 projects
    p1 = Project(owner_id=test_user.id, repo_url="https://github.com/teststudent/p1.git", repo_full_name="teststudent/p1", name="p1")
    p2 = Project(owner_id=test_user.id, repo_url="https://github.com/teststudent/p2.git", repo_full_name="teststudent/p2", name="p2")
    db_session.add_all([p1, p2])
    db_session.commit()

    # Attempt to add a 3rd project
    res = authenticated_client.post(
        "/projects",
        json={"repo_url": "https://github.com/teststudent/p3"}
    )
    assert res.status_code == 400
    assert "limit reached" in res.json()["detail"].lower()


def test_invalid_url_rejected_422(authenticated_client):
    res = authenticated_client.post(
        "/projects",
        json={"repo_url": "https://gitlab.com/notgithub/repo"}
    )
    assert res.status_code == 422

