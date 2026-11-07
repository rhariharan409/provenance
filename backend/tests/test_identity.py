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
