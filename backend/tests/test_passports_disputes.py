from datetime import datetime, timezone
import uuid
import pytest
from app.config import settings
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore, ScoreConfidence
from app.models.disputes import Dispute, DisputeStatus
from app.models.members import Member
from app.models.passports import Passport
from app.models.projects import Project, ProjectStatus
from app.models.users import User, UserRole
from app.routers.passports import _IP_REQUESTS
from app.services.passport import (
    build_snapshot,
    canonical_json,
    compute_seal,
    generate_passport_code,
    verify_seal,
)


# ---------------------------------------------------------------------------
# Unit tests: pure functions
# ---------------------------------------------------------------------------

def test_canonical_json_stability():
    """canonical_json produces identical bytes regardless of dict key order."""
    d1 = {
        "z": 100,
        "a": {"k2": "val2", "k1": "val1"},
        "m": [
            {"b": 2, "a": 1},
            {"d": 4, "c": 3},
        ],
    }
    d2 = {
        "a": {"k1": "val1", "k2": "val2"},
        "m": [
            {"a": 1, "b": 2},
            {"c": 3, "d": 4},
        ],
        "z": 100,
    }
    b1 = canonical_json(d1)
    b2 = canonical_json(d2)
    assert b1 == b2
    assert isinstance(b1, bytes)
    # Check delimiters: no whitespace after separators
    assert b'":' in b1
    assert b': ' not in b1
    assert b', ' not in b1


def test_seal_changes_on_single_character_mutation():
    """HMAC-SHA256 seal completely changes if any single character in snapshot changes."""
    secret = "super-secret-signing-key-12345"
    snapshot = {
        "project": {"repo_full_name": "org/repo", "head_sha": "abc1234"},
        "member": {"login": "dev1", "display_name": "Developer One"},
        "score": {"share_percent": 42.5, "confidence": "high"},
    }
    seal_orig = compute_seal(snapshot, secret)
    assert len(seal_orig) == 64

    # Mutate string by 1 char
    snapshot_mutated_str = {
        "project": {"repo_full_name": "org/repo", "head_sha": "abc1235"},
        "member": {"login": "dev1", "display_name": "Developer One"},
        "score": {"share_percent": 42.5, "confidence": "high"},
    }
    seal_mutated_str = compute_seal(snapshot_mutated_str, secret)
    assert seal_orig != seal_mutated_str

    # Mutate number
    snapshot_mutated_num = {
        "project": {"repo_full_name": "org/repo", "head_sha": "abc1234"},
        "member": {"login": "dev1", "display_name": "Developer One"},
        "score": {"share_percent": 42.6, "confidence": "high"},
    }
    seal_mutated_num = compute_seal(snapshot_mutated_num, secret)
    assert seal_orig != seal_mutated_num


def test_verify_seal_behavior():
    """verify_seal returns True for untouched snapshot and False on tampering or wrong secret."""
    secret = "valid-secret-key-32-chars-minimum"
    snapshot = {"score": {"share_percent": 50.0}, "notes": "test"}
    seal = compute_seal(snapshot, secret)

    # Valid check
    assert verify_seal(snapshot, seal, secret) is True

    # Tampered snapshot
    tampered = {"score": {"share_percent": 50.1}, "notes": "test"}
    assert verify_seal(tampered, seal, secret) is False

    # Wrong secret
    assert verify_seal(snapshot, seal, "wrong-secret-key") is False

    # Wrong seal
    assert verify_seal(snapshot, "0" * 64, secret) is False


def test_passport_code_generator():
    """Passport codes are 32 chars urlsafe, non-empty, and unique."""
    c1 = generate_passport_code()
    c2 = generate_passport_code()
    assert len(c1) == 32
    assert len(c2) == 32
    assert c1 != c2


# ---------------------------------------------------------------------------
# Integration tests: API endpoints, DB, Auth & Security
# ---------------------------------------------------------------------------

@pytest.fixture
def passport_test_env(db_session, test_user, other_user, admin_user):
    """Sets up a complete project with 2 members, a run, and contribution scores."""
    settings.PASSPORT_SIGNING_SECRET = "test-passport-signing-secret-32-bytes"
    settings.PUBLIC_BASE_URL = "http://localhost:3000"

    proj = Project(
        name="test-passport-repo",
        repo_url="https://github.com/testorg/test-passport-repo",
        repo_full_name="testorg/test-passport-repo",
        owner_id=test_user.id,
        status=ProjectStatus.ready,
    )
    db_session.add(proj)
    db_session.flush()

    member_a = Member(
        project_id=proj.id,
        user_id=test_user.id,
        github_login="teststudent",
        display_name="Test Student",
    )
    member_b = Member(
        project_id=proj.id,
        user_id=other_user.id,
        github_login="otheruser",
        display_name="Other User",
    )
    db_session.add_all([member_a, member_b])
    db_session.flush()

    run = AnalysisRun(
        project_id=proj.id,
        head_sha="0123456789abcdef0123456789abcdef01234567",
        status=AnalysisRunStatus.complete,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        scoring_version="1.0",
        weights={"survival": 0.4, "effective_change": 0.25, "ownership": 0.15, "collaboration": 0.2},
    )
    db_session.add(run)
    db_session.flush()

    score_a = ContributionScore(
        project_id=proj.id,
        run_id=run.id,
        member_id=member_a.id,
        share_percent=60.0,
        confidence=ScoreConfidence.high,
        signals={"survival": {"raw": 100, "normalized": 0.6, "weight": 0.4}},
        evidence={
            "top_commits": [{"sha": "abc1234567", "subject": "Initial commit", "effective_lines": 50}],
            "top_files": [{"path": "main.py", "surviving_lines": 50}],
            "owned_modules": [{"path": "core", "share": 0.8}],
        },
    )
    score_b = ContributionScore(
        project_id=proj.id,
        run_id=run.id,
        member_id=member_b.id,
        share_percent=40.0,
        confidence=ScoreConfidence.medium,
        signals={"survival": {"raw": 60, "normalized": 0.4, "weight": 0.4}},
        evidence={"top_commits": [], "top_files": [], "owned_modules": []},
    )
    db_session.add_all([score_a, score_b])
    db_session.commit()

    return {
        "project": proj,
        "member_a": member_a,
        "member_b": member_b,
        "run": run,
        "score_a": score_a,
        "score_b": score_b,
    }


def test_publish_passport_permissions_and_idempotence(
    authenticated_client, other_client, admin_client, passport_test_env
):
    """
    Publishing rules:
      - Only the linked user can publish their own row (members.user_id == current_user.id).
      - Another user gets 403.
      - Admin may NOT publish for others (gets 403).
      - Publishing again returns the existing active passport (idempotent).
    """
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]

    # 1. Other user tries to publish for member_a -> 403
    res_other = other_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    assert res_other.status_code == 403
    assert "own contribution" in res_other.json()["detail"].lower()

    # 2. Admin tries to publish for member_a -> 403 (explicit rule: admins may NOT publish for others)
    res_admin = admin_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    assert res_admin.status_code == 403
    assert "own contribution" in res_admin.json()["detail"].lower()

    # 3. Test user (linked to member_a) publishes -> 200 or 201
    res_owner = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    assert res_owner.status_code in (200, 201)
    data = res_owner.json()
    assert "code" in data
    assert data["already_published"] is False
    assert "/p/" in data["url"]
    code = data["code"]

    # 4. Publish again -> idempotent, returns existing active passport
    res_again = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    assert res_again.status_code in (200, 201)
    data_again = res_again.json()
    assert data_again["code"] == code
    assert data_again["already_published"] is True


def test_publish_missing_signing_secret(authenticated_client, passport_test_env):
    """If PASSPORT_SIGNING_SECRET is missing or empty, publishing returns 503."""
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]

    orig_secret = settings.PASSPORT_SIGNING_SECRET
    try:
        settings.PASSPORT_SIGNING_SECRET = None
        res = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
        assert res.status_code == 503
        assert "not configured" in res.json()["detail"].lower()

        settings.PASSPORT_SIGNING_SECRET = ""
        res2 = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
        assert res2.status_code == 503
    finally:
        settings.PASSPORT_SIGNING_SECRET = orig_secret


def test_verify_tampered_passport_in_db(client, authenticated_client, passport_test_env, db_session):
    """
    Public /verify endpoint returns valid: True initially,
    and valid: False after directly altering the snapshot in the database.
    """
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]

    # 1. Publish
    res = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    code = res.json()["code"]

    # 2. Public verify untouched
    res_verify = client.get(f"/public/passports/{code}/verify")
    assert res_verify.status_code == 200
    verify_data = res_verify.json()
    assert verify_data["valid"] is True
    assert verify_data["seal_version"] == "1"
    assert "checked_at" in verify_data

    # 3. Tamper directly in DB
    passport = db_session.query(Passport).filter(Passport.code == code).first()
    tampered_snapshot = dict(passport.snapshot)
    tampered_snapshot["score"] = dict(tampered_snapshot["score"])
    tampered_snapshot["score"]["share_percent"] = 99.9
    passport.snapshot = tampered_snapshot
    db_session.commit()

    # 4. Verify again -> False
    res_verify_tampered = client.get(f"/public/passports/{code}/verify")
    assert res_verify_tampered.status_code == 200
    tampered_data = res_verify_tampered.json()
    assert tampered_data["valid"] is False
    # Never leaks secret or recomputed seal
    assert "secret" not in tampered_data
    assert "seal" not in tampered_data


def test_passport_revocation(client, authenticated_client, other_client, admin_client, passport_test_env):
    """
    Revocation:
      - Non-owner / non-admin gets 404 (does not leak existence).
      - Owner can revoke.
      - Public endpoint returns 404 with identical body to an unknown code.
    """
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]

    # Publish
    res = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    code = res.json()["code"]

    # Other client tries to revoke -> 404
    res_other_del = other_client.delete(f"/passports/{code}")
    assert res_other_del.status_code == 404

    # Public endpoint works before revoking
    res_pub = client.get(f"/public/passports/{code}")
    assert res_pub.status_code == 200

    # Unknown code response for comparison
    res_unknown = client.get("/public/passports/nonexistent-code-123456789012")
    assert res_unknown.status_code == 404

    # Owner revokes
    res_del = authenticated_client.delete(f"/passports/{code}")
    assert res_del.status_code == 200
    assert res_del.json()["revoked"] is True

    # Public endpoint now returns 404 with identical body format
    res_pub_revoked = client.get(f"/public/passports/{code}")
    assert res_pub_revoked.status_code == 404
    assert res_pub_revoked.json() == res_unknown.json()


def test_public_passport_sanitization_and_anonymization(
    client, authenticated_client, other_client, passport_test_env
):
    """
    Public passport responses must:
      - Contain no emails, no user IDs, no dispute text.
      - Have X-Robots-Tag: noindex, nofollow and Referrer-Policy: no-referrer headers.
      - Anonymize teammates as "Teammate A", "Teammate B"... unless they hold an active passport.
    """
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]
    member_b = passport_test_env["member_b"]

    # 1. Test user publishes passport
    res = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    code_a = res.json()["code"]

    # 2. Fetch public passport
    res_pub = client.get(f"/public/passports/{code_a}")
    assert res_pub.status_code == 200
    assert res_pub.headers.get("x-robots-tag") == "noindex, nofollow"
    assert res_pub.headers.get("referrer-policy") == "no-referrer"

    pub_data = res_pub.json()
    snapshot = pub_data["snapshot"]

    # Check that no sensitive IDs or emails exist anywhere in raw text
    raw_str = res_pub.text
    assert "@example.com" not in raw_str
    assert "user_id" not in raw_str
    assert str(passport_test_env["project"].owner_id) not in raw_str
    assert str(member_b.id) not in raw_str

    # Teammate B should be anonymized because they haven't published a passport
    team = snapshot.get("team", [])
    assert len(team) == 1
    teammate = team[0]
    assert teammate["label"] == "Teammate A"
    assert teammate["login"] is None
    assert teammate["has_passport"] is False

    # 3. Now teammate B publishes their own passport
    res_b = other_client.post(f"/projects/{proj.id}/members/{member_b.id}/passport")
    assert res_b.status_code in (200, 201)

    # Build snapshot dynamically or check next run: teammate B's login is included when active passport exists
    # Verify via pure build_snapshot:
    s_updated = build_snapshot(
        repo_full_name=proj.repo_full_name,
        repo_url=proj.repo_url,
        head_sha="0123456789abcdef",
        finished_at=datetime.now(timezone.utc),
        member_login="teststudent",
        member_display_name="Test Student",
        share_percent=60.0,
        confidence="high",
        flags=[],
        signals={},
        stats={},
        top_commits=[],
        top_files=[],
        owned_modules=[],
        other_members_scores=[{"github_login": "otheruser", "display_name": "Other User", "share_percent": 40.0}],
        members_with_active_passports={"otheruser"},
        scoring_version="1.0",
        weights={},
    )
    assert s_updated["team"][0]["login"] == "otheruser"
    assert s_updated["team"][0]["has_passport"] is True


def test_disputes_crud_and_limits(
    authenticated_client, other_client, admin_client, test_user, other_user, passport_test_env
):
    """
    Disputes:
      - Create: allowed for linked user or owner/admin.
      - Max text length (1000) enforced.
      - Max open disputes per user enforced.
      - Resolution: owner/admin can resolve/reject. Raiser cannot resolve their own dispute.
    """
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]

    # 1. Text validation: empty text -> 400 or 422
    res_empty = authenticated_client.post(
        f"/projects/{proj.id}/members/{member_a.id}/disputes",
        json={"text": "   "},
    )
    assert res_empty.status_code in (400, 422)

    # 2. Text validation: > 1000 chars -> 400 or 422
    res_long = authenticated_client.post(
        f"/projects/{proj.id}/members/{member_a.id}/disputes",
        json={"text": "A" * 1001},
    )
    assert res_long.status_code in (400, 422)

    # 3. Create valid dispute by linked user
    res_create = authenticated_client.post(
        f"/projects/{proj.id}/members/{member_a.id}/disputes",
        json={"text": "The collaboration score did not reflect the 4 PR reviews I completed."},
    )
    assert res_create.status_code in (200, 201)
    dispute_id = res_create.json()["id"]

    # 4. Unrelated user cannot resolve -> 404 (or 403)
    res_other_res = other_client.post(
        f"/projects/{proj.id}/disputes/{dispute_id}/resolve",
        json={"status": "resolved", "resolution_note": "Unrelated trying to resolve"},
    )
    assert res_other_res.status_code in (403, 404)

    # 5. Raiser cannot resolve unless admin -> 403
    # (test_user raised it; even though test_user is project owner, raiser cannot resolve)
    res_raiser_res = authenticated_client.post(
        f"/projects/{proj.id}/disputes/{dispute_id}/resolve",
        json={"status": "resolved", "resolution_note": "Self-resolving"},
    )
    assert res_raiser_res.status_code == 403

    # 6. Admin resolves dispute -> 200
    res_admin_res = admin_client.post(
        f"/projects/{proj.id}/disputes/{dispute_id}/resolve",
        json={"status": "resolved", "resolution_note": "Reviewed commits and verified."},
    )
    assert res_admin_res.status_code == 200
    assert "re-running repository analysis may be needed" in res_admin_res.json()["message"].lower()

    # 7. Test open disputes limit enforcement
    settings.MAX_OPEN_DISPUTES_PER_USER = 2
    try:
        # Create 2 open disputes
        r1 = authenticated_client.post(
            f"/projects/{proj.id}/members/{member_a.id}/disputes",
            json={"text": "Dispute 1"},
        )
        assert r1.status_code in (200, 201)

        r2 = authenticated_client.post(
            f"/projects/{proj.id}/members/{member_a.id}/disputes",
            json={"text": "Dispute 2"},
        )
        assert r2.status_code in (200, 201)

        # 3rd open dispute must be blocked
        r3 = authenticated_client.post(
            f"/projects/{proj.id}/members/{member_a.id}/disputes",
            json={"text": "Dispute 3"},
        )
        assert r3.status_code == 400
        assert "maximum open disputes" in r3.json()["detail"].lower()
    finally:
        settings.MAX_OPEN_DISPUTES_PER_USER = 5


def test_public_rate_limiting(client, authenticated_client, passport_test_env):
    """Public passport endpoints enforce in-memory rate limiting returning 429."""
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]

    res = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    code = res.json()["code"]

    # Clear rate limit store
    _IP_REQUESTS.clear()

    # Perform 60 requests -> all 200
    for _ in range(60):
        r = client.get(f"/public/passports/{code}")
        assert r.status_code == 200

    # 61st request -> 429
    r_blocked = client.get(f"/public/passports/{code}")
    assert r_blocked.status_code == 429
    assert "rate limit exceeded" in r_blocked.json()["detail"].lower()

    # Clear after test to avoid affecting other tests
    _IP_REQUESTS.clear()


def test_qr_svg_endpoint(client, authenticated_client, passport_test_env):
    """
    QR code endpoint returns SVG with content-type image/svg+xml,
    cache-control public max-age 3600, and non-empty body containing SVG markup.
    """
    proj = passport_test_env["project"]
    member_a = passport_test_env["member_a"]

    res = authenticated_client.post(f"/projects/{proj.id}/members/{member_a.id}/passport")
    code = res.json()["code"]

    qr_res = client.get(f"/public/passports/{code}/qr.svg")
    assert qr_res.status_code == 200
    assert "image/svg+xml" in qr_res.headers.get("content-type", "")
    assert "max-age=3600" in qr_res.headers.get("cache-control", "")
    assert "<svg" in qr_res.text
    assert "</svg>" in qr_res.text
