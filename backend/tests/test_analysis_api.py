from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest

from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore, ScoreConfidence
from app.models.members import Member
from app.models.projects import Project, ProjectStatus


@pytest.fixture
def test_project(db_session, test_user):
    project = Project(
        owner_id=test_user.id,
        repo_url="https://github.com/teststudent/sample-app.git",
        repo_full_name="teststudent/sample-app",
        name="sample-app",
        status=ProjectStatus.ready,
        analysis_status="pending",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def other_project(db_session, other_user):
    project = Project(
        owner_id=other_user.id,
        repo_url="https://github.com/otheruser/secret-app.git",
        repo_full_name="otheruser/secret-app",
        name="secret-app",
        status=ProjectStatus.ready,
        analysis_status="pending",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def test_analysis_api_unauthenticated(client, test_project):
    pid = str(test_project.id)
    mid = str(uuid.uuid4())

    assert client.post(f"/projects/{pid}/analyze").status_code == 401
    assert client.get(f"/projects/{pid}/scores").status_code == 401
    assert client.get(f"/projects/{pid}/scores/{mid}/evidence").status_code == 401
    assert client.get(f"/projects/{pid}/analysis/status").status_code == 401


def test_analysis_api_access_control_returns_404(
    authenticated_client, other_client, other_project
):
    pid = str(other_project.id)
    mid = str(uuid.uuid4())

    # Main user attempts to access other user's project -> 404 (not 403, preventing existence leakage)
    assert authenticated_client.post(f"/projects/{pid}/analyze").status_code == 404
    assert authenticated_client.get(f"/projects/{pid}/scores").status_code == 404
    assert authenticated_client.get(f"/projects/{pid}/scores/{mid}/evidence").status_code == 404
    assert authenticated_client.get(f"/projects/{pid}/analysis/status").status_code == 404


def test_trigger_analysis_conflict_when_already_running(
    authenticated_client, test_project, db_session
):
    test_project.analysis_status = "running"
    db_session.commit()

    resp = authenticated_client.post(f"/projects/{test_project.id}/analyze")
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"].lower()


def test_trigger_analysis_accepted(authenticated_client, test_project):
    resp = authenticated_client.post(f"/projects/{test_project.id}/analyze")
    assert resp.status_code == 202
    data = resp.json()
    assert data["message"] == "Analysis started"
    assert data["status"] == "running"
    assert data["project_id"] == str(test_project.id)


def test_get_analysis_status(authenticated_client, test_project, db_session):
    test_project.analysis_status = "complete"
    test_project.analysis_error = None
    db_session.commit()

    resp = authenticated_client.get(f"/projects/{test_project.id}/analysis/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_status"] == "complete"
    assert data["analysis_error"] is None


def test_get_scores_and_evidence(authenticated_client, test_project, db_session):
    # 1. Create a Member
    member = Member(
        project_id=test_project.id,
        display_name="Alice Dev",
        github_login="alicedev",
    )
    db_session.add(member)
    db_session.flush()

    # 2. Create AnalysisRun (complete)
    run = AnalysisRun(
        project_id=test_project.id,
        status=AnalysisRunStatus.complete,
        scoring_version="1.0",
        head_sha="0123456789abcdef0123456789abcdef01234567",
        finished_at=datetime.now(timezone.utc),
        weights={
            "survival": 0.40,
            "effective_change": 0.25,
            "ownership": 0.15,
            "collaboration": 0.20,
        },
        stats={
            "files_total": 20,
            "files_analyzed": 18,
            "files_ignored": 2,
            "lines_surviving": 500,
            "commits_counted": 15,
            "project_flags": ["low_data"],
        },
    )
    db_session.add(run)
    db_session.flush()

    # 3. Create ContributionScore with Evidence
    evidence_data = {
        "top_commits": [
            {"sha": "abc12345", "subject": "Add core feature", "effective_lines": 120.0}
        ],
        "top_files": [
            {"path": "src/core.py", "surviving_lines": 95}
        ],
        "owned_modules": [
            {"module": "src/core", "share": 0.85, "surviving_lines": 95}
        ],
    }
    signals_data = {
        "survival": {"raw": 200.0, "normalized": 0.60, "weight": 0.40},
        "effective_change": {"raw": 150.0, "normalized": 0.55, "weight": 0.25},
        "ownership": {"raw": 0.80, "normalized": 0.80, "weight": 0.15},
        "collaboration": {"raw": 2.0, "normalized": 0.50, "weight": 0.20},
    }

    score = ContributionScore(
        run_id=run.id,
        project_id=test_project.id,
        member_id=member.id,
        share_percent=Decimal("62.50"),
        confidence=ScoreConfidence.high,
        signals=signals_data,
        flags=["late_dump"],
        evidence=evidence_data,
    )
    db_session.add(score)
    db_session.commit()

    # 4. Test GET /projects/{id}/scores
    resp = authenticated_client.get(f"/projects/{test_project.id}/scores")
    assert resp.status_code == 200
    scores_data = resp.json()
    assert scores_data["run_id"] == str(run.id)
    assert scores_data["head_sha"] == run.head_sha
    assert len(scores_data["members"]) == 1
    m_score = scores_data["members"][0]
    assert m_score["member_id"] == str(member.id)
    assert m_score["display_name"] == "Alice Dev"
    assert m_score["share_percent"] == 62.5
    assert m_score["confidence"] == "high"
    assert m_score["flags"] == ["late_dump"]
    assert "survival" in m_score["signals"]
    assert len(scores_data["project_flags"]) == 1
    assert scores_data["project_flags"][0]["code"] == "low_data"

    # 5. Test GET /projects/{id}/scores/{member_id}/evidence
    ev_resp = authenticated_client.get(f"/projects/{test_project.id}/scores/{member.id}/evidence")
    assert ev_resp.status_code == 200
    ev_data = ev_resp.json()
    assert ev_data["member_id"] == str(member.id)
    assert ev_data["display_name"] == "Alice Dev"
    assert ev_data["share_percent"] == 62.5
    assert ev_data["confidence"] == "high"
    assert len(ev_data["top_commits"]) == 1
    assert ev_data["top_commits"][0]["sha"] == "abc12345"
    assert len(ev_data["top_files"]) == 1
    assert ev_data["top_files"][0]["path"] == "src/core.py"
    assert len(ev_data["owned_modules"]) == 1
    assert "summary_sentence" in ev_data
    assert "Alice Dev" in ev_data["summary_sentence"]
