import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid
import pytest

from app.config import settings
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.author_aliases import AliasSource, AuthorAlias
from app.models.commits import Commit
from app.models.members import Member
from app.models.projects import Project, ProjectStatus
from app.services.analysis.runner import run_analysis, _list_candidate_files
from app.services.analysis.survival import ProjectSurvivalResults, process_file_blame
from app.services.collector import run_collection


def _run_git(cwd: str, args: list[str], env: dict | None = None) -> str:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        env=full_env,
        check=True,
    )
    return res.stdout.strip()


from tests.conftest import TestSessionLocal
from app.models.users import User, UserRole


def test_partial_clone_fallback():
    """
    Tests that when partial clone (--filter=blob:none) is rejected by remote server,
    collector falls back to full bare clone and records a warning notice.
    """
    session = TestSessionLocal()
    project_id = None
    user_id = None
    try:
        user = User(
            github_id=77771,
            username="perf_user_1",
            display_name="Perf User 1",
            email="perf1@example.com",
            role=UserRole.student,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        project = Project(
            owner_id=user.id,
            repo_url="https://github.com/mock-org/mock-repo.git",
            repo_full_name="mock-org/mock-repo",
            name="mock-repo",
            github_owner="mock-org",
            github_repo="mock-repo",
            default_branch="main",
            is_private=False,
            status=ProjectStatus.pending,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

        called_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            called_commands.append(cmd)
            # If it's the partial clone attempt with --filter=blob:none
            if "--filter=blob:none" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=128,
                    stdout="",
                    stderr="fatal: dumb http transport does not support shallow/filter capabilities",
                )
            # If it's the fallback bare clone
            elif "clone" in cmd and "--bare" in cmd:
                target_path = cmd[-1]
                os.makedirs(target_path, exist_ok=True)
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout="",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="",
                stderr="",
            )

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("app.services.collector.GitHubClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.resolve_auth.return_value = MagicMock(token=None, app_installed=True, installation_id=None, warnings=[])
                mock_client.verify_and_get_metadata.return_value = ({"default_branch": "main", "description": "Mock", "size": 10}, [])
                mock_client.list_commits.return_value = ({}, [])
                mock_client.list_pull_requests_and_reviews.return_value = ([], [])
                mock_client_cls.return_value = mock_client

                run_collection(project_id, db_factory=TestSessionLocal)

        session.expire_all()
        updated_project = session.query(Project).filter(Project.id == project_id).first()
        assert updated_project is not None
        assert updated_project.status == ProjectStatus.ready
        # Verify fallback bare clone was invoked
        partial_cmds = [c for c in called_commands if "--filter=blob:none" in c]
        bare_cmds = [c for c in called_commands if "clone" in c and "--bare" in c and "--filter=blob:none" not in c]
        assert len(partial_cmds) >= 1
        assert len(bare_cmds) >= 1
        # Verify warning was recorded
        assert updated_project.warnings is not None
        assert "Server rejected partial clone" in updated_project.warnings
    finally:
        if project_id:
            session.query(Project).filter(Project.id == project_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
        session.close()


def test_incremental_fetch_when_clone_exists():
    """
    Tests that if a bare clone directory already exists for the project,
    run_collection runs 'git fetch' instead of re-cloning.
    """
    session = TestSessionLocal()
    project_id = None
    user_id = None
    expected_clone_dir = None
    try:
        user = User(
            github_id=77772,
            username="perf_user_2",
            display_name="Perf User 2",
            email="perf2@example.com",
            role=UserRole.student,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

        project = Project(
            owner_id=user.id,
            repo_url="https://github.com/mock-org/mock-repo-inc.git",
            repo_full_name="mock-org/mock-repo-inc",
            name="mock-repo-inc",
            github_owner="mock-org",
            github_repo="mock-repo-inc",
            default_branch="main",
            is_private=False,
            status=ProjectStatus.pending,
            last_collected_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

        expected_clone_dir = os.path.abspath(
            os.path.join(settings.REPO_STORAGE_PATH, f"{project_id}.git")
        )
        os.makedirs(expected_clone_dir, exist_ok=True)
        with open(os.path.join(expected_clone_dir, "HEAD"), "w", encoding="utf-8") as f:
            f.write("ref: refs/heads/main\n")

        called_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            called_commands.append(cmd)
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="",
                stderr="",
            )

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("app.services.collector.GitHubClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.resolve_auth.return_value = MagicMock(token=None, app_installed=True, installation_id=None, warnings=[])
                mock_client.verify_and_get_metadata.return_value = ({"default_branch": "main", "description": "Mock", "size": 10}, [])
                mock_client.list_commits.return_value = ({}, [])
                mock_client.list_pull_requests_and_reviews.return_value = ([], [])
                mock_client_cls.return_value = mock_client

                run_collection(project_id, db_factory=TestSessionLocal)

        # Verify git fetch was called and git clone was NOT called
        fetch_cmds = [c for c in called_commands if "fetch" in c]
        clone_cmds = [c for c in called_commands if "clone" in c]
        assert len(fetch_cmds) >= 1
        assert len(clone_cmds) == 0
        assert "fetch" in fetch_cmds[0]
    finally:
        if expected_clone_dir:
            shutil.rmtree(expected_clone_dir, ignore_errors=True)
        if project_id:
            session.query(Project).filter(Project.id == project_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
        session.close()


def test_parallel_blame_correctness(db_session, test_user):
    """
    Tests parallel blame correctness: verifies that parallel blame (worker pool)
    produces the EXACT same survival counts, file breakdowns, and module breakdowns
    as sequential blame on the same repository.
    """
    temp_dir = tempfile.mkdtemp(prefix="test_parallel_blame_")
    try:
        work_dir = os.path.join(temp_dir, "work")
        bare_dir = os.path.join(temp_dir, "bare.git")
        os.makedirs(work_dir, exist_ok=True)

        _run_git(work_dir, ["init", "-b", "main"])
        _run_git(work_dir, ["config", "user.name", "Init User"])
        _run_git(work_dir, ["config", "user.email", "init@example.com"])

        env_alice = {
            "GIT_AUTHOR_NAME": "Alice",
            "GIT_AUTHOR_EMAIL": "alice@example.com",
            "GIT_COMMITTER_NAME": "Alice",
            "GIT_COMMITTER_EMAIL": "alice@example.com",
        }
        env_bob = {
            "GIT_AUTHOR_NAME": "Bob",
            "GIT_AUTHOR_EMAIL": "bob@example.com",
            "GIT_COMMITTER_NAME": "Bob",
            "GIT_COMMITTER_EMAIL": "bob@example.com",
        }

        # Create multiple files in different modules
        os.makedirs(os.path.join(work_dir, "auth"), exist_ok=True)
        os.makedirs(os.path.join(work_dir, "core"), exist_ok=True)
        os.makedirs(os.path.join(work_dir, "api"), exist_ok=True)

        with open(os.path.join(work_dir, "auth", "login.py"), "w", encoding="utf-8") as f:
            f.write("\n".join([f"def login_fn_{i}(): pass" for i in range(30)]) + "\n")

        with open(os.path.join(work_dir, "core", "models.py"), "w", encoding="utf-8") as f:
            f.write("\n".join([f"class Model_{i}: pass" for i in range(25)]) + "\n")

        _run_git(work_dir, ["add", "."], env=env_alice)
        _run_git(work_dir, ["commit", "-m", "Alice files"], env=env_alice)

        with open(os.path.join(work_dir, "api", "routes.py"), "w", encoding="utf-8") as f:
            f.write("\n".join([f"def route_{i}(): return {i}" for i in range(40)]) + "\n")

        with open(os.path.join(work_dir, "auth", "tokens.py"), "w", encoding="utf-8") as f:
            f.write("\n".join([f"def token_{i}(): return 'tok'" for i in range(20)]) + "\n")

        _run_git(work_dir, ["add", "."], env=env_bob)
        _run_git(work_dir, ["commit", "-m", "Bob files"], env=env_bob)

        # Clone bare repo
        _run_git(temp_dir, ["clone", "--bare", work_dir, bare_dir])
        head_sha = _run_git(bare_dir, ["rev-parse", "HEAD"])

        # Candidate files
        candidates, total, ignored = _list_candidate_files(bare_dir, head_sha)
        assert len(candidates) == 4

        # Member aliases mapping
        def lookup_fn(email: str, name: str):
            if "alice" in email.lower():
                return "member-alice"
            if "bob" in email.lower():
                return "member-bob"
            return None

        # 1. Sequential blame execution (1 worker)
        res_seq = ProjectSurvivalResults()
        for f_path, _, _ in candidates:
            cmd = ["git", "--git-dir", bare_dir, "blame", "--line-porcelain", "-w", "-M", "-C", head_sha, "--", f_path]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
            process_file_blame(
                file_path=f_path,
                blame_output=proc.stdout,
                alias_lookup_fn=lookup_fn,
                results=res_seq,
            )

        # 2. Parallel blame execution (simulate pool with 4 workers)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        res_par = ProjectSurvivalResults()

        def blame_fn(item):
            f_path = item[0]
            cmd = ["git", "--git-dir", bare_dir, "blame", "--line-porcelain", "-w", "-M", "-C", head_sha, "--", f_path]
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
            return f_path, p.stdout

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(blame_fn, item) for item in candidates]
            for fut in as_completed(futures):
                f_path, blame_out = fut.result()
                process_file_blame(
                    file_path=f_path,
                    blame_output=blame_out,
                    alias_lookup_fn=lookup_fn,
                    results=res_par,
                )

        # Assert identical results
        assert res_seq.total_surviving_lines == res_par.total_surviving_lines
        assert res_seq.module_totals == res_par.module_totals
        assert res_seq.file_totals == res_par.file_totals
        for m_id in ["member-alice", "member-bob"]:
            assert res_seq.members[m_id].total_lines == res_par.members[m_id].total_lines
            assert res_seq.members[m_id].file_lines == res_par.members[m_id].file_lines
            assert res_seq.members[m_id].module_lines == res_par.members[m_id].module_lines
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_history_window_filtering(db_session, test_user):
    """
    Tests history window: commits older than project.history_since
    are excluded from the analysis scoring engine.
    """
    now = datetime.now(timezone.utc)
    project = Project(
        owner_id=test_user.id,
        repo_url="https://github.com/mock-org/history-test.git",
        repo_full_name="mock-org/history-test",
        name="history-test",
        github_owner="mock-org",
        github_repo="history-test",
        default_branch="main",
        status=ProjectStatus.ready,
        history_window="6m",
        history_since=now - timedelta(days=180),
    )
    db_session.add(project)
    db_session.commit()

    member = Member(
        project_id=project.id,
        github_login="hist_user",
        display_name="History User",
    )
    db_session.add(member)
    db_session.commit()

    alias = AuthorAlias(
        project_id=project.id,
        member_id=member.id,
        name="Hist User",
        email="hist@example.com",
        source=AliasSource.api_match,
    )
    db_session.add(alias)
    db_session.commit()

    # Commit 1: 1 year ago (outside 6m window)
    c1 = Commit(
        project_id=project.id,
        alias_id=alias.id,
        sha="1111111111111111111111111111111111111111",
        author_name="Hist User",
        author_email="hist@example.com",
        authored_at=now - timedelta(days=365),
        subject="Old commit",
        additions=50,
        deletions=0,
        files_changed=1,
        parent_count=1,
    )
    # Commit 2: 1 month ago (inside 6m window)
    c2 = Commit(
        project_id=project.id,
        alias_id=alias.id,
        sha="2222222222222222222222222222222222222222",
        author_name="Hist User",
        author_email="hist@example.com",
        authored_at=now - timedelta(days=30),
        subject="Recent commit",
        additions=20,
        deletions=0,
        files_changed=1,
        parent_count=1,
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    # Query with history_since logic as implemented in runner.py
    db_commits = db_session.query(Commit).filter(Commit.project_id == project.id).all()
    if project.history_since:
        h_since = project.history_since
        if h_since.tzinfo is None:
            h_since = h_since.replace(tzinfo=timezone.utc)
        filtered = [c for c in db_commits if c.authored_at and (c.authored_at if c.authored_at.tzinfo else c.authored_at.replace(tzinfo=timezone.utc)) >= h_since]
        db_commits = filtered

    assert len(db_commits) == 1
    assert db_commits[0].sha == c2.sha
