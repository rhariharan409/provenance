import csv
import io
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    ContributionScore,
    Dispute,
    DisputeStatus,
    Fingerprint,
    Member,
    MemberSummary,
    OriginalityMatch,
    Passport,
    Project,
    ProjectFaculty,
    ProjectStatus,
    ScoreConfidence,
    SummaryMethod,
    User,
    UserRole,
)
from app.security import create_session_token
from app.services.originality import (
    ORIGINALITY_DISCLAIMER,
    normalize_line,
    winnow,
    compute_originality_matches,
)
from app.services.summary import (
    SUMMARY_DISCLAIMER,
    build_facts_bundle,
    generate_rule_based_summary,
    generate_member_summary,
    validate_llm_response,
)


def make_client_for_user(user: User, db_session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set("provenance_session", token)
    return client


# =========================================================================
# 1. Role Authorization & Access Control
# =========================================================================

def test_faculty_role_authorization_flow(db_session, test_user, admin_user):
    """
    - Unassigned faculty cannot view project (404)
    - Assigned faculty can view project, scores, disputes, export CSV
    - Assigned faculty can resolve disputes
    - Assigned faculty CANNOT delete project or assign aliases
    """
    # Create faculty user
    faculty_user = User(
        github_id=2001,
        username="prof_smith",
        display_name="Professor Smith",
        email="smith@university.edu",
        role=UserRole.faculty,
    )
    db_session.add(faculty_user)

    # Create project owned by test_user
    project = Project(
        owner_id=test_user.id,
        name="Team Project",
        repo_full_name="org/team-project",
        repo_url="https://github.com/org/team-project",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    # Create run, member and dispute
    run = AnalysisRun(
        project_id=project.id,
        head_sha="0123456789abcdef0123456789abcdef01234567",
        status=AnalysisRunStatus.complete,
        weights={"survival": 0.4, "effective_change": 0.25, "ownership": 0.15, "collaboration": 0.2},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    member = Member(
        project_id=project.id,
        user_id=test_user.id,
        github_login="teststudent",
        display_name="Test Student",
    )
    db_session.add(member)
    db_session.commit()
    db_session.refresh(member)

    dispute = Dispute(
        project_id=project.id,
        member_id=member.id,
        run_id=run.id,
        raised_by=test_user.id,
        status=DisputeStatus.open,
        text="My work on auth was not counted properly.",
    )
    db_session.add(dispute)
    db_session.commit()
    db_session.refresh(dispute)

    faculty_client = make_client_for_user(faculty_user, db_session)
    owner_client = make_client_for_user(test_user, db_session)

    # 1. Unassigned faculty gets 404
    resp = faculty_client.get(f"/projects/{project.id}")
    assert resp.status_code == 404

    resp = faculty_client.get(f"/projects/{project.id}/disputes")
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # 2. Owner assigns faculty
    assign_resp = owner_client.post(
        f"/projects/{project.id}/faculty",
        json={"username": "prof_smith"},
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["faculty"]["username"] == "prof_smith"

    # 3. Assigned faculty can now view project, disputes
    resp = faculty_client.get(f"/projects/{project.id}")
    assert resp.status_code == 200
    assert resp.json()["repo_full_name"] == "org/team-project"

    resp = faculty_client.get(f"/projects/{project.id}/disputes")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Check faculty assigned projects endpoint
    fac_proj_resp = faculty_client.get("/faculty/projects")
    assert fac_proj_resp.status_code == 200
    assert len(fac_proj_resp.json()) == 1
    assert fac_proj_resp.json()[0]["id"] == str(project.id)

    # 4. Assigned faculty can resolve dispute
    resolve_resp = faculty_client.post(
        f"/projects/{project.id}/disputes/{dispute.id}/resolve",
        json={"status": "resolved", "resolution_note": "Reviewed commits, confirmed credit."},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "ok"
    db_session.refresh(dispute)
    assert dispute.status == DisputeStatus.resolved

    # 5. Assigned faculty CANNOT delete project
    del_resp = faculty_client.delete(f"/projects/{project.id}")
    assert del_resp.status_code in (403, 404)

    # 6. Assigned faculty CANNOT remove faculty or assign faculty
    add_fac_resp = faculty_client.post(
        f"/projects/{project.id}/faculty",
        json={"username": "another_prof"},
    )
    assert add_fac_resp.status_code in (403, 404)


def test_admin_user_management_and_last_admin_protection(db_session, admin_user, test_user):
    """
    - Admin can view users and change roles
    - Admin cannot demote the last remaining admin
    - Non-admin student cannot access /admin/* endpoints
    """
    admin_client = make_client_for_user(admin_user, db_session)
    student_client = make_client_for_user(test_user, db_session)

    # 1. Student access denied (403)
    resp = student_client.get("/admin/users")
    assert resp.status_code == 403

    resp = student_client.patch(f"/admin/users/{test_user.id}/role", json={"role": "admin"})
    assert resp.status_code == 403

    # 2. Admin can list users
    resp = admin_client.get("/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    # 3. Admin can promote student to faculty
    patch_resp = admin_client.patch(
        f"/admin/users/{test_user.id}/role",
        json={"role": "faculty"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["role"] == "faculty"

    # Revert test_user back to student
    admin_client.patch(f"/admin/users/{test_user.id}/role", json={"role": "student"})

    # 4. Admin CANNOT demote their own admin role
    demote_resp = admin_client.patch(
        f"/admin/users/{admin_user.id}/role",
        json={"role": "student"},
    )
    assert demote_resp.status_code == 400
    assert "cannot demote" in demote_resp.json()["detail"].lower()


# =========================================================================
# 2. CSV Export & Formula Injection Escaping
# =========================================================================

def test_csv_export_format_and_formula_injection_escaping(db_session, test_user):
    """
    - Export CSV generates attachment with correct headers
    - Values starting with =, +, -, @ are escaped with leading '
    """
    project = Project(
        owner_id=test_user.id,
        name="Formula Test Repo",
        repo_full_name="org/formula-test",
        repo_url="https://github.com/org/formula-test",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    # Member with dangerous spreadsheet injection payload in display name & login
    malicious_member = Member(
        project_id=project.id,
        github_login="=HYPERLINK(\"http://evil.com\",\"Click\")",
        display_name="+cmd|' /C calc'!A0",
    )
    normal_member = Member(
        project_id=project.id,
        github_login="-calc",
        display_name="@admin_user",
    )
    db_session.add_all([malicious_member, normal_member])
    db_session.commit()

    # Create run and scores
    run = AnalysisRun(
        project_id=project.id,
        head_sha="0123456789abcdef0123456789abcdef01234567",
        status=AnalysisRunStatus.complete,
        weights={"survival": 0.4, "effective_change": 0.25, "ownership": 0.15, "collaboration": 0.2},
    )
    db_session.add(run)
    db_session.commit()

    score1 = ContributionScore(
        run_id=run.id,
        project_id=project.id,
        member_id=malicious_member.id,
        share_percent=60.0,
        confidence=ScoreConfidence.high,
        flags=[],
        signals={"survival": {"raw": 150}},
        evidence={},
    )
    score2 = ContributionScore(
        run_id=run.id,
        project_id=project.id,
        member_id=normal_member.id,
        share_percent=40.0,
        confidence=ScoreConfidence.medium,
        flags=[],
        signals={"survival": {"raw": 100}},
        evidence={},
    )
    db_session.add_all([score1, score2])
    db_session.commit()

    client = make_client_for_user(test_user, db_session)
    resp = client.get(f"/projects/{project.id}/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment; filename=" in resp.headers["content-disposition"]

    csv_text = resp.text
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # Header check
    expected_header = [
        "member display name",
        "login",
        "share_percent",
        "confidence",
        "flags",
        "counted commits",
        "surviving lines",
        "scoring_version",
        "head_sha",
    ]
    assert rows[0] == expected_header

    # Data rows check for formula injection prefixing
    data_rows = rows[1:]
    assert len(data_rows) == 2

    # Check that any cell starting with =, +, -, @ starts with '
    for row in data_rows:
        display_name = row[0]
        login = row[1]
        if login.startswith(("=", "+", "-", "@")):
            assert False, f"Unescaped login: {login}"
        if display_name.startswith(("=", "+", "-", "@")):
            assert False, f"Unescaped display_name: {display_name}"

    # Specifically verify the leading quote was added
    escaped_names = [r[0] for r in data_rows]
    escaped_logins = [r[1] for r in data_rows]
    assert any(n.startswith("'+") or n.startswith("'@") for n in escaped_names)
    assert any(l.startswith("'=") or l.startswith("'-") for l in escaped_logins)


# =========================================================================
# 3. Evidence-Grounded Summaries & Privacy Protection
# =========================================================================

def test_summary_facts_bundle_privacy_guarantees(db_session, test_user):
    """
    build_facts_bundle must NEVER include emails, teammate names, or file contents.
    """
    project = Project(
        owner_id=test_user.id,
        name="Privacy Repo",
        repo_full_name="org/privacy-repo",
        repo_url="https://github.com/org/privacy-repo",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()

    member = Member(
        project_id=project.id,
        github_login="student_a",
        display_name="Alice Smith",
        user_id=test_user.id,
    )
    db_session.add(member)
    db_session.commit()

    run = AnalysisRun(
        project_id=project.id,
        head_sha="abcdef0123456789abcdef0123456789abcdef01",
        status=AnalysisRunStatus.complete,
        weights={"survival": 0.4, "effective_change": 0.25, "ownership": 0.15, "collaboration": 0.2},
    )
    db_session.add(run)
    db_session.commit()

    score = ContributionScore(
        run_id=run.id,
        project_id=project.id,
        member_id=member.id,
        share_percent=35.0,
        confidence=ScoreConfidence.high,
        flags=[],
        signals={},
        evidence={"top_commits": [], "top_files": []},
    )
    db_session.add(score)
    db_session.commit()

    facts = build_facts_bundle(member, score, run, db_session)

    # Privacy assertions
    facts_str = str(facts)
    assert "@example.com" not in facts_str
    assert "email" not in facts_str
    assert "teammates" not in facts
    assert "source_code" not in facts
    assert facts["login"] == "student_a"


def test_rule_based_summary_generation_and_citations():
    """
    Deterministic rule-based summary must cite commits using [sha] format.
    """
    facts = {
        "counted_commits": 12,
        "active_days": 5,
        "top_files": [{"path": "src/auth.py", "lines": 150}],
        "owned_modules": [{"path": "src/auth.py", "share": 0.85}],
        "top_commits": [
            {
                "sha": "a1b2c3d4e5f60000111122223333444455556666",
                "sha_short": "a1b2c3d",
                "subject": "Implement authentication middleware",
                "additions": 120,
            },
        ],
        "pull_requests_opened": 2,
        "reviews_given": 3,
    }

    text, method, citations = generate_rule_based_summary(facts)
    assert method == SummaryMethod.rule_based
    assert "[a1b2c3d]" in text
    assert len(citations) >= 1
    assert citations[0]["sha"] == "a1b2c3d4e5f60000111122223333444455556666"


def test_llm_hallucinated_citation_fallback():
    """
    If LLM returns a citation not present in the facts bundle,
    validate_llm_response must reject it and return None.
    """
    facts = {
        "top_commits": [
            {
                "sha": "111122223333444455556666777788889999aaaa",
                "sha_short": "1111222",
                "subject": "Add unit tests",
            }
        ],
    }

    # Case 1: Valid citation matching top commits (3 sentences)
    valid_text = "Contributor counted 5 commits in repository history. Key contribution included unit tests [1111222]. Work was integrated cleanly."
    res = validate_llm_response(valid_text, facts)
    assert res is not None

    # Case 2: Hallucinated citation not in facts
    invalid_text = "Contributor counted 5 commits in repository history. Key contribution included fixed production bug [9999888]. Work was integrated cleanly."
    assert validate_llm_response(invalid_text, facts) is None


def test_summary_api_generation_fallback_on_llm_failure(db_session, test_user):
    """
    When Anthropic API fails or is unconfigured, POST /summaries/generate must
    fall back gracefully to rule-based without erroring.
    """
    project = Project(
        owner_id=test_user.id,
        name="Summary Repo",
        repo_full_name="org/summary-repo",
        repo_url="https://github.com/org/summary-repo",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()

    member = Member(
        project_id=project.id,
        github_login="student_c",
        display_name="Charlie",
        user_id=test_user.id,
    )
    db_session.add(member)
    db_session.commit()

    run = AnalysisRun(
        project_id=project.id,
        head_sha="0123456789abcdef0123456789abcdef01234567",
        status=AnalysisRunStatus.complete,
        weights={"survival": 0.4, "effective_change": 0.25, "ownership": 0.15, "collaboration": 0.2},
    )
    db_session.add(run)
    db_session.commit()

    score = ContributionScore(
        run_id=run.id,
        project_id=project.id,
        member_id=member.id,
        share_percent=25.0,
        confidence=ScoreConfidence.high,
        flags=[],
        signals={},
        evidence={"top_commits": [], "top_files": []},
    )
    db_session.add(score)
    db_session.commit()

    client = make_client_for_user(test_user, db_session)

    # Mock LLM error
    with patch("app.services.summary.generate_llm_summary", return_value=None):
        resp = client.post(f"/projects/{project.id}/summaries/generate")
        assert resp.status_code == 200
        summaries_gen = resp.json()
        assert len(summaries_gen) >= 1

    # Fetch summaries
    get_resp = client.get(f"/projects/{project.id}/summaries")
    assert get_resp.status_code == 200
    summaries = get_resp.json()
    assert len(summaries) >= 1
    assert summaries[0]["method"] == "rule_based"


# =========================================================================
# 4. Originality Check & Winnowing Fingerprinting
# =========================================================================

def test_originality_line_normalization():
    """
    normalize_line replaces numbers and strings with placeholders, collapses whitespace and lowercases.
    """
    # Whitespace and case variations
    line1 = "def Calculate_Score( user_id ):"
    line2 = "def calculate_score( user_id ):   "
    assert normalize_line(line1) == normalize_line(line2)

    # String variations
    line3 = 'const message = "Hello, world!";'
    line4 = "const message = 'Goodbye everyone!';"
    assert normalize_line(line3) == normalize_line(line4)

    # Number variations
    line5 = "let count = 42;"
    line6 = "let count = 9999;"
    assert normalize_line(line5) == normalize_line(line6)


def test_winnowing_window_selection():
    """
    winnow with window_size w selects minimum hash within each sliding window.
    """
    kgram_hashes = [(50, 1), (20, 2), (80, 3), (10, 4), (90, 5), (30, 6)]
    # With window w=3:
    # [(50, 1), (20, 2), (80, 3)] -> min is (20, 2)
    # [(20, 2), (80, 3), (10, 4)] -> min is (10, 4)
    # [(80, 3), (10, 4), (90, 5)] -> min is (10, 4)
    # [(10, 4), (90, 5), (30, 6)] -> min is (10, 4)
    fingerprints = winnow(kgram_hashes, window_size=3)
    hashes_only = [f[0] for f in fingerprints]
    assert 20 in hashes_only
    assert 10 in hashes_only


def test_boilerplate_hash_ignored_across_multiple_projects(db_session, test_user, admin_user):
    """
    Hashes appearing in >5 projects are filtered out as template/boilerplate.
    """
    # Create 6 projects
    projects = []
    for i in range(7):
        p = Project(
            owner_id=test_user.id if i % 2 == 0 else admin_user.id,
            name=f"Project {i}",
            repo_full_name=f"org/project-{i}",
            repo_url=f"https://github.com/org/project-{i}",
            status=ProjectStatus.ready,
        )
        db_session.add(p)
        projects.append(p)
    db_session.commit()

    common_hash = 123456789012345678
    unique_hash = 987654321098765432

    runs = []
    for p in projects:
        r = AnalysisRun(
            project_id=p.id,
            head_sha="0123456789abcdef0123456789abcdef01234567",
            status=AnalysisRunStatus.complete,
            weights={"survival": 0.4, "effective_change": 0.25, "ownership": 0.15, "collaboration": 0.2},
        )
        db_session.add(r)
        runs.append(r)
    db_session.commit()

    # Add common_hash to 6 projects (>5)
    for idx, p in enumerate(projects[:6]):
        db_session.add(Fingerprint(
            project_id=p.id,
            run_id=runs[idx].id,
            hash=common_hash,
            file_path="src/index.js",
            line_start=1,
        ))

    # Add unique_hash only to project 0 and project 1
    db_session.add(Fingerprint(
        project_id=projects[0].id,
        run_id=runs[0].id,
        hash=unique_hash,
        file_path="src/custom.js",
        line_start=10,
    ))
    db_session.add(Fingerprint(
        project_id=projects[1].id,
        run_id=runs[1].id,
        hash=unique_hash,
        file_path="src/custom.js",
        line_start=10,
    ))
    db_session.commit()

    # Compute matches for project 0 with min_shared_lines patched to 1
    with patch.object(settings, "ORIGINALITY_MIN_SHARED_LINES", 1):
        matches = compute_originality_matches(
            projects[0].id,
            runs[0].id,
            db_session,
        )

    # common_hash should be ignored because it appears in 6 projects (>5).
    # unique_hash should match with project 1.
    assert len(matches) == 1
    assert matches[0].other_project_id == projects[1].id
    assert matches[0].shared_fingerprints == 1


def test_banned_words_absence():
    """
    Strict wording constraint: The terms 'plagiarism', 'copied', or 'cheating'
    must NEVER appear in originality disclaimers or summary disclaimers.
    """
    banned_words = ["plagiarism", "copied", "cheating"]
    for word in banned_words:
        assert word not in ORIGINALITY_DISCLAIMER.lower()
        assert word not in SUMMARY_DISCLAIMER.lower()


# =========================================================================
# 5. Account Deletion & Data Export
# =========================================================================

def test_data_export_endpoint(db_session, test_user):
    """
    GET /me/export returns machine-readable JSON snapshot.
    """
    client = make_client_for_user(test_user, db_session)
    resp = client.get("/me/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["username"] == test_user.username
    assert "projects_owned" in data
    assert "passports" in data
    assert "disputes_raised" in data


def test_delete_account_validation_and_cascade(db_session):
    """
    - DELETE /me requires exact confirmation 'DELETE'
    - Deletes user, owned projects, removes on-disk clone dir, clears session cookie
    """
    user = User(
        github_id=3001,
        username="delete_me_student",
        display_name="To Delete",
        email="delete@example.com",
        role=UserRole.student,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    project = Project(
        owner_id=user.id,
        name="Project To Delete",
        repo_full_name="org/project-delete",
        repo_url="https://github.com/org/project-delete",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    # Create dummy clone directory on disk
    storage_path = Path(settings.REPO_STORAGE_PATH)
    storage_path.mkdir(parents=True, exist_ok=True)
    repo_dir = storage_path / f"{project.id}.git"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "HEAD").write_text("ref: refs/heads/main\n")

    client = make_client_for_user(user, db_session)

    # 1. Invalid confirm returns 400
    bad_resp = client.request("DELETE", "/me", json={"confirm": "NO"})
    assert bad_resp.status_code == 400

    # 2. Correct confirm deletes account and cascades
    del_resp = client.request("DELETE", "/me", json={"confirm": "DELETE"})
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "ok"

    # 3. Verify on-disk repository is deleted
    assert not repo_dir.exists()

    # 4. Verify user and owned project deleted from DB
    deleted_user = db_session.query(User).filter(User.id == user.id).first()
    assert deleted_user is None

    deleted_project = db_session.query(Project).filter(Project.id == project.id).first()
    assert deleted_project is None
