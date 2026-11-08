from datetime import datetime, timezone
import uuid
import pytest
from app.models.author_aliases import AliasSource
from app.services.identity import (
    RawCommitData,
    is_bot_identity,
    parse_noreply_email,
    resolve_identities,
)


def test_noreply_email_parsing_both_formats():
    # ID+login format
    assert parse_noreply_email("123456+octocat@users.noreply.github.com") == "octocat"
    assert parse_noreply_email("9999+john_doe-123@users.noreply.github.com") == "john_doe-123"

    # login only format
    assert parse_noreply_email("octocat@users.noreply.github.com") == "octocat"
    assert parse_noreply_email("user-name@users.noreply.github.com") == "user-name"

    # Normal or invalid emails
    assert parse_noreply_email("octocat@gmail.com") is None
    assert parse_noreply_email("octocat@github.com") is None
    assert parse_noreply_email("") is None
    assert parse_noreply_email(None) is None  # type: ignore


def test_bot_detection():
    # Suffix [bot]
    assert is_bot_identity("dependabot[bot]") is True
    assert is_bot_identity("github-actions[bot]") is True
    assert is_bot_identity("some-custom-tool[bot]") is True

    # Known bot names
    assert is_bot_identity("dependabot") is True
    assert is_bot_identity("renovate") is True
    assert is_bot_identity("github-actions") is True

    # Regular human authors
    assert is_bot_identity("Linus Torvalds") is False
    assert is_bot_identity("Alice Smith", "asmith") is False
    assert is_bot_identity("Bob Jones", "bobjones") is False


def test_identity_resolution_pipeline():
    now = datetime.now(timezone.utc)

    # 1. Alias with noreply email
    commit_noreply = RawCommitData(
        sha="sha_noreply_1",
        author_name="Octo Cat",
        author_email="12345+octocat@users.noreply.github.com",
        authored_at=now,
        subject="Add feature",
    )

    # 2. Alias resolved via API match
    commit_api = RawCommitData(
        sha="sha_api_1",
        author_name="Alice Wonder",
        author_email="alice@personal.org",
        authored_at=now,
        subject="Fix bug",
    )
    commit_api_2 = RawCommitData(
        sha="sha_api_2",
        author_name="Alice Wonder",
        author_email="alice@personal.org",
        authored_at=now,
        subject="Fix another bug",
    )

    # 3. Alias resolved via name match (same name as Alice Wonder, but university email)
    commit_name = RawCommitData(
        sha="sha_name_1",
        author_name="Alice Wonder",
        author_email="awonder@university.edu",
        authored_at=now,
        subject="University lab commit",
    )

    # 4. Bot alias
    commit_bot = RawCommitData(
        sha="sha_bot_1",
        author_name="dependabot[bot]",
        author_email="49699333+dependabot[bot]@users.noreply.github.com",
        authored_at=now,
        subject="Bump dependency",
    )

    # 5. Unresolved alias (not matching noreply, no API login, no name match)
    commit_unresolved = RawCommitData(
        sha="sha_unresolved_1",
        author_name="Mysterious Contributor",
        author_email="anon@darknet.io",
        authored_at=now,
        subject="Secret patch",
    )

    commits = [
        commit_noreply,
        commit_api,
        commit_api_2,
        commit_name,
        commit_bot,
        commit_unresolved,
    ]

    # sha -> login map from GitHub API
    sha_to_login = {
        "sha_api_1": "alicew",
        "sha_api_2": "alicew",
        "sha_bot_1": "dependabot",
    }

    resolved = resolve_identities(commits, sha_to_login)

    # Verify noreply
    noreply_key = ("12345+octocat@users.noreply.github.com".lower(), "octo cat".lower())
    assert noreply_key in resolved
    assert resolved[noreply_key].login == "octocat"
    assert resolved[noreply_key].source == AliasSource.noreply
    assert resolved[noreply_key].is_bot is False

    # Verify API match
    api_key = ("alice@personal.org".lower(), "alice wonder".lower())
    assert api_key in resolved
    assert resolved[api_key].login == "alicew"
    assert resolved[api_key].source == AliasSource.api_match
    assert resolved[api_key].commit_count == 2

    # Verify Name match
    name_key = ("awonder@university.edu".lower(), "alice wonder".lower())
    assert name_key in resolved
    assert resolved[name_key].login == "alicew"
    assert resolved[name_key].source == AliasSource.name_match

    # Verify Bot
    bot_key = ("49699333+dependabot[bot]@users.noreply.github.com".lower(), "dependabot[bot]".lower())
    assert bot_key in resolved
    assert resolved[bot_key].is_bot is True

    # Verify Unresolved stays unlinked
    unresolved_key = ("anon@darknet.io".lower(), "mysterious contributor".lower())
    assert unresolved_key in resolved
    assert resolved[unresolved_key].login is None
    assert resolved[unresolved_key].source is None


def test_re_run_preserves_manual_assignments():
    now = datetime.now(timezone.utc)
    commit = RawCommitData(
        sha="sha_manual_1",
        author_name="Charlie Dave",
        author_email="charlie@work.com",
        authored_at=now,
        subject="Work commit",
    )

    mock_member_id = uuid.uuid4()
    existing_manual = {
        ("charlie@work.com".lower(), "charlie dave".lower()): ("charlie_gh", mock_member_id)
    }

    # API returns something else (e.g. wrong login)
    sha_to_login = {"sha_manual_1": "someone_else"}

    resolved = resolve_identities([commit], sha_to_login, existing_manual_assignments=existing_manual)

    key = ("charlie@work.com".lower(), "charlie dave".lower())
    assert resolved[key].login == "charlie_gh"
    assert resolved[key].source == AliasSource.manual
    assert resolved[key].existing_manual_member_id == mock_member_id


def test_case_insensitive_member_deduplication_devendiran(db_session, test_user):
    """
    Regression test: GitHub logins are case-insensitive.
    Different cases like 'Devendiran2007' and 'devendiran2007' must resolve to
    the exact same Member record (normalized to lower()) and never create two members.
    """
    from app.models.projects import Project, ProjectStatus
    from app.models.members import Member
    from app.models.contributions import Contribution
    from app.services.identity import sync_identities_and_commits_to_db, ResolvedAlias

    now = datetime.now(timezone.utc)

    # 1. Create project
    project = Project(
        owner_id=test_user.id,
        repo_url="https://github.com/test/case-test.git",
        repo_full_name="test/case-test",
        name="case-test",
        status=ProjectStatus.ready,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    # 2. Commit authored with capitalized login 'Devendiran2007'
    commit_1 = RawCommitData(
        sha="sha_dev_1",
        author_name="devendiran2007",
        author_email="devendirank61@gmail.com",
        authored_at=now,
        subject="Initial commit",
    )
    # API match resolves to capitalized login 'Devendiran2007'
    sha_to_login = {"sha_dev_1": "Devendiran2007"}
    resolved = resolve_identities([commit_1], sha_to_login)

    # Verify resolve_identities normalized login to lower
    key = ("devendirank61@gmail.com".lower(), "devendiran2007".lower())
    assert resolved[key].login == "devendiran2007"

    # 3. Simulate sync where PR extra logins contains lowercase 'devendiran2007'
    # and resolved_aliases has capitalized 'Devendiran2007'
    resolved[key].login = "Devendiran2007"  # inject capitalized login directly to test sync resilience
    pr_extra_logins = ["devendiran2007", "Devendiran2007"]

    sync_identities_and_commits_to_db(
        db=db_session,
        project_id=project.id,
        resolved_aliases=resolved,
        commits=[commit_1],
        pr_extra_logins=pr_extra_logins,
    )

    # 4. Assert only ONE member exists for this project
    members = db_session.query(Member).filter(Member.project_id == project.id).all()
    assert len(members) == 1, f"Expected 1 member, found {len(members)}: {[m.github_login for m in members]}"
    assert members[0].github_login == "devendiran2007"

    # 5. Assert only ONE contribution row exists for this project
    contribs = db_session.query(Contribution).filter(Contribution.project_id == project.id).all()
    assert len(contribs) == 1, f"Expected 1 contribution row, found {len(contribs)}"
    assert contribs[0].github_login == "devendiran2007"

    # 6. Re-run sync with alternative casing and verify no duplicate is produced
    sync_identities_and_commits_to_db(
        db=db_session,
        project_id=project.id,
        resolved_aliases=resolved,
        commits=[commit_1],
        pr_extra_logins=["DEVONDIRAN2007"],
    )
    members_after = db_session.query(Member).filter(Member.project_id == project.id).all()
    assert len(members_after) == 1


