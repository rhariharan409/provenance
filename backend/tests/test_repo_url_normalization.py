import os
import subprocess
import tempfile
import uuid
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateIndex

# Enable SQLite compatibility for in-memory testing
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return compiler.visit_JSON(type_, **kw)

@compiles(CreateIndex, "sqlite")
def _compile_create_index_sqlite(create, compiler, **kw):
    stmt = compiler.visit_create_index(create, **kw)
    return stmt.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS").replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS")

from app.config import settings
from app.db import Base
from app.models.projects import Project, ProjectStatus
from app.models.users import User, UserRole
from app.services.collector import normalize_repo_url, REPO_URL_ERROR_MESSAGE, run_collection


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Module-level override ensuring tests run autonomously with SQLite in test environment."""
    pass


@pytest.fixture
def sqlite_session_factory():
    """In-memory SQLite database session factory with all models created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# -----------------------------------------------------------------------------
# 1. Accepted forms all map to the exact same canonical (owner, repo, canonical_url)
# -----------------------------------------------------------------------------
def test_accepted_url_forms_map_to_same_owner_repo():
    accepted_forms = [
        "https://github.com/torvalds/linux",
        "https://github.com/torvalds/linux.git",
        "https://github.com/torvalds/linux.GIT",
        "https://github.com/torvalds/linux/",
        "https://github.com/torvalds/linux.git/",
        "https://github.com/torvalds/linux.GIT/",
        "http://github.com/torvalds/linux",
        "HTTP://GITHUB.COM/torvalds/linux",
        "HTTPS://WWW.GITHUB.COM/torvalds/linux",
        "github.com/torvalds/linux",
        "www.github.com/torvalds/linux",
        "  https://github.com/torvalds/linux.git/  ",
        "https://github.com/torvalds/linux/tree/main",
        "https://github.com/torvalds/linux/blob/master/Makefile",
        "https://github.com/torvalds/linux/issues",
        "https://github.com/torvalds/linux?tab=readme-ov-file",
        "https://github.com/torvalds/linux#readme",
        "https://github.com/torvalds/linux.git?foo=bar#baz",
    ]

    expected_owner = "torvalds"
    expected_repo = "linux"
    expected_canonical = "https://github.com/torvalds/linux"

    for url in accepted_forms:
        owner, repo, canonical = normalize_repo_url(url)
        assert owner == expected_owner, f"Failed on {url}: expected owner {expected_owner}, got {owner}"
        assert repo == expected_repo, f"Failed on {url}: expected repo {expected_repo}, got {repo}"
        assert canonical == expected_canonical, f"Failed on {url}: expected canonical {expected_canonical}, got {canonical}"


# -----------------------------------------------------------------------------
# 2. Rejection of invalid URLs with expected error message
# -----------------------------------------------------------------------------
def test_rejects_invalid_hosts_schemes_and_names():
    invalid_cases = [
        "https://gitlab.com/owner/repo",
        "https://bitbucket.org/owner/repo",
        "https://evil-github.com/owner/repo",
        "https://github.com.attacker.com/owner/repo",
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "file:///tmp/repo",
        "file://c:/repos/repo",
        "ftp://github.com/owner/repo",
        "https://github.com/-owner/repo",
        "https://github.com/owner/-repo",
        "https://github.com/-owner/-repo",
        "https://github.com/owner/.git",
        "https://github.com/owner/.git.git",
        "https://github.com/owner",
        "https://github.com/",
        "",
        "   ",
        None,
        12345,
    ]

    for raw in invalid_cases:
        with pytest.raises(ValueError) as exc_info:
            normalize_repo_url(raw)
        assert str(exc_info.value) == REPO_URL_ERROR_MESSAGE, f"Failed message check for {raw}: got {exc_info.value}"


# -----------------------------------------------------------------------------
# 3. Clone command uses rebuilt URL with double dash "--"
# -----------------------------------------------------------------------------
def test_clone_command_uses_rebuilt_url_with_double_dash(sqlite_session_factory):
    init_db = sqlite_session_factory()
    user = User(
        github_id=99111,
        username="clone_test_user",
        display_name="Clone Test User",
        email="clonetest@example.com",
        role=UserRole.student,
    )
    init_db.add(user)
    init_db.commit()

    owner, repo, canonical = normalize_repo_url("https://github.com/test-org/test-repo.git/")
    assert canonical == "https://github.com/test-org/test-repo"

    project = Project(
        owner_id=user.id,
        repo_url=canonical,
        repo_full_name=f"{owner}/{repo}",
        name=repo,
        github_owner=owner,
        github_repo=repo,
        default_branch="main",
        is_private=False,
        status=ProjectStatus.pending,
    )
    init_db.add(project)
    init_db.commit()
    project_id = project.id
    init_db.close()

    called_commands = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        called_commands.append(cmd)
        target_path = cmd[-1]
        os.makedirs(target_path, exist_ok=True)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        with patch("app.services.collector.GitHubClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.resolve_auth.return_value = MagicMock(token=None, app_installed=True, installation_id=None, warnings=[])
            mock_client.verify_and_get_metadata.return_value = ({"default_branch": "main", "description": "Mock", "size": 10}, [])
            mock_client.list_commits.return_value = ({}, [])
            mock_client.list_pull_requests_and_reviews.return_value = ([], [])
            mock_client_cls.return_value = mock_client

            run_collection(project_id, db_factory=sqlite_session_factory)

    # Verify clone command used rebuilt URL canonical_url + ".git" with "--" preceding it
    clone_cmds = [c for c in called_commands if "clone" in c]
    assert len(clone_cmds) >= 1
    clone_cmd = clone_cmds[0]
    expected_clone_url = f"{canonical}.git"
    assert "--" in clone_cmd
    dash_idx = clone_cmd.index("--")
    assert clone_cmd[dash_idx + 1] == expected_clone_url


# -----------------------------------------------------------------------------
# 4. Duplicate detection works across forms (.git, uppercase, without .git)
# -----------------------------------------------------------------------------
def test_duplicate_detection_across_forms(sqlite_session_factory):
    db = sqlite_session_factory()
    user = User(
        github_id=99222,
        username="dup_test_user",
        display_name="Dup Test User",
        email="duptest@example.com",
        role=UserRole.student,
    )
    db.add(user)
    db.commit()

    # Form 1: user adds https://github.com/my-org/my-project
    owner1, repo1, canonical1 = normalize_repo_url("https://github.com/my-org/my-project")
    proj1 = Project(
        owner_id=user.id,
        repo_url=canonical1,
        repo_full_name=f"{owner1}/{repo1}",
        name=repo1,
        github_owner=owner1,
        github_repo=repo1,
        default_branch="main",
        status=ProjectStatus.ready,
    )
    db.add(proj1)
    db.commit()

    # Form 2: user attempts to add https://github.com/MY-ORG/my-project.git/
    owner2, repo2, canonical2 = normalize_repo_url("https://github.com/MY-ORG/my-project.git/")
    norm_owner_repo2 = f"{owner2}/{repo2}".lower()

    duplicate = db.query(Project).filter(
        Project.owner_id == user.id,
        or_(
            func.lower(Project.repo_full_name) == norm_owner_repo2,
            func.lower(Project.repo_full_name) == f"{norm_owner_repo2}.git",
            func.lower(Project.repo_url) == canonical2.lower(),
            func.lower(Project.repo_url) == f"{canonical2.lower()}.git",
        )
    ).first()

    assert duplicate is not None
    assert duplicate.id == proj1.id
    db.close()

