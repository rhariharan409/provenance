import os
import stat
import subprocess
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from app.models.projects import Project, ProjectStatus
from app.models.users import User, UserRole
from app.services.collector import run_collection, _sanitize_git_error, _safe_rmtree
from app.services.github_client import GitHubClient, AuthResolution
from tests.conftest import TestSessionLocal


def test_sanitize_git_error_masks_tokens_and_formats_first_fatal_line():
    token = "ghp_VERY_SECRET_TOKEN_12345"
    stderr = (
        f"Cloning into bare repository 'C:\\Users\\repo.git'...\n"
        f"fatal: Authentication failed for 'https://x-access-token:{token}@github.com/org/repo.git/'\n"
        f"fatal: secondary fatal message\n"
    )

    result = _sanitize_git_error(stderr, [token])
    assert "Clone failed: fatal:" in result
    assert token not in result
    assert "[REDACTED]" in result
    assert "destination path" not in result


def test_sanitize_git_error_with_existing_non_empty_directory():
    stderr = (
        "fatal: destination path 'C:\\Users\\repo.git' already exists and is not an empty directory.\n"
    )
    result = _sanitize_git_error(stderr, [])
    assert result == "Clone failed: fatal: destination path 'C:\\Users\\repo.git' already exists and is not an empty directory."


def test_safe_rmtree_removes_readonly_files():
    temp_dir = tempfile.mkdtemp(prefix="test_safe_rmtree_")
    file_path = os.path.join(temp_dir, "pack-readonly.idx")
    with open(file_path, "w") as f:
        f.write("dummy pack data")

    # Set file read-only (Windows 0o444 / stat.S_IREAD)
    os.chmod(file_path, stat.S_IREAD)

    assert os.path.exists(file_path)
    _safe_rmtree(temp_dir)
    assert not os.path.exists(temp_dir)


def test_public_repo_clones_anonymously_without_auth_header():
    """
    Regression: For public repos where no GitHub App installation token exists,
    do NOT send any Authorization header to git clone.
    """
    fake_pat = "github_pat_11AAAAA_SECRET_PAT"

    session = TestSessionLocal()
    project_id = None
    user_id = None
    try:
        user = User(
            github_id=88881,
            username="public_test_user",
            display_name="Public User",
            email="public@example.com",
            role=UserRole.student,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        project = Project(
            owner_id=user.id,
            repo_url="https://github.com/public-org/public-repo.git",
            repo_full_name="public-org/public-repo",
            name="public-repo",
            github_owner="public-org",
            github_repo="public-repo",
            status=ProjectStatus.pending,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

        class MockPublicClient(GitHubClient):
            def resolve_auth(self, owner: str, repo: str):
                # PAT returned, but no installation_id (public repo)
                return AuthResolution(token=fake_pat, installation_id=None)

            def verify_and_get_metadata(self, owner, repo, user, token):
                return {
                    "default_branch": "main",
                    "size": 100,
                    "private": False,
                    "description": "Public test repository",
                }, []

        recorded_env = {}

        def mock_subprocess_run(cmd, *args, **kwargs):
            nonlocal recorded_env
            if "clone" in cmd:
                recorded_env = kwargs.get("env", {})
                # Simulate successful clone
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            elif "log" in cmd:
                # Return empty git log output to finish cleanly
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            run_collection(
                project_id=project_id,
                github_client=MockPublicClient(),
                db_factory=TestSessionLocal,
            )

        # GIT_CONFIG extraheader must NOT be set for public repo
        assert "GIT_CONFIG_COUNT" not in recorded_env
        assert "GIT_CONFIG_KEY_0" not in recorded_env
        assert "GIT_CONFIG_VALUE_0" not in recorded_env

    finally:
        if project_id:
            session.query(Project).filter(Project.id == project_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
        session.close()


def test_private_repo_with_installation_token_sends_extraheader():
    """
    Regression: For private repos with GitHub App installation token,
    extraheader IS sent.
    """
    fake_inst_token = "ghs_INSTALLATION_TOKEN_9999"

    session = TestSessionLocal()
    project_id = None
    user_id = None
    try:
        user = User(
            github_id=88882,
            username="private_test_user",
            display_name="Private User",
            email="private@example.com",
            role=UserRole.student,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        project = Project(
            owner_id=user.id,
            repo_url="https://github.com/private-org/private-repo.git",
            repo_full_name="private-org/private-repo",
            name="private-repo",
            github_owner="private-org",
            github_repo="private-repo",
            status=ProjectStatus.pending,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

        class MockPrivateClient(GitHubClient):
            def resolve_auth(self, owner: str, repo: str):
                return AuthResolution(token=fake_inst_token, installation_id=12345)

            def verify_and_get_metadata(self, owner, repo, user, token):
                return {
                    "default_branch": "main",
                    "size": 100,
                    "private": True,
                    "description": "Private test repository",
                }, []

        recorded_env = {}

        def mock_subprocess_run(cmd, *args, **kwargs):
            nonlocal recorded_env
            if "clone" in cmd:
                recorded_env = kwargs.get("env", {})
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            elif "log" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            run_collection(
                project_id=project_id,
                github_client=MockPrivateClient(),
                db_factory=TestSessionLocal,
            )

        # GIT_CONFIG extraheader MUST be set for private repo with app
        assert recorded_env.get("GIT_CONFIG_KEY_0") == "http.extraheader"
        assert "Authorization: Basic " in recorded_env.get("GIT_CONFIG_VALUE_0", "")

    finally:
        if project_id:
            session.query(Project).filter(Project.id == project_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
        session.close()


def test_clone_failure_stores_first_stderr_line_in_error_message():
    """
    Regression: When git clone fails, project.error_message contains git's first
    stderr line (e.g. 'Clone failed: fatal: ...') with tokens redacted.
    """
    fake_token = "ghp_SECRET_FAIL_TOKEN"

    session = TestSessionLocal()
    project_id = None
    user_id = None
    try:
        user = User(
            github_id=88883,
            username="fail_test_user",
            display_name="Fail User",
            email="fail@example.com",
            role=UserRole.student,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        project = Project(
            owner_id=user.id,
            repo_url="https://github.com/public-org/failing-repo.git",
            repo_full_name="public-org/failing-repo",
            name="failing-repo",
            github_owner="public-org",
            github_repo="failing-repo",
            status=ProjectStatus.pending,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

        class MockClient(GitHubClient):
            def resolve_auth(self, owner: str, repo: str):
                return AuthResolution(token=fake_token, installation_id=None)

            def verify_and_get_metadata(self, owner, repo, user, token):
                return {
                    "default_branch": "main",
                    "size": 100,
                    "private": False,
                    "description": "Failing repository",
                }, []

        def mock_subprocess_run(cmd, *args, **kwargs):
            if "clone" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    returncode=128,
                    stdout="",
                    stderr=f"Cloning into bare repository...\nfatal: repository not found with token {fake_token}\n",
                )
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            run_collection(
                project_id=project_id,
                github_client=MockClient(),
                db_factory=TestSessionLocal,
            )

        session.expire_all()
        updated_project = session.query(Project).filter(Project.id == project_id).first()
        assert updated_project.status == ProjectStatus.failed
        assert updated_project.error_message.startswith("Clone failed: fatal: repository not found with token [REDACTED]")
        assert fake_token not in updated_project.error_message

    finally:
        if project_id:
            session.query(Project).filter(Project.id == project_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
        session.close()

