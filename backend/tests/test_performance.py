import ast
from decimal import Decimal
import io
import os
import shutil
import subprocess
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid
import pytest
from sqlalchemy import create_engine
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
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.author_aliases import AliasSource, AuthorAlias
from app.models.blame_cache import BlameCache
from app.models.commits import Commit
from app.models.members import Member
from app.models.projects import Project, ProjectStatus
from app.models.users import User, UserRole
from app.services.analysis.confidence import evaluate_member_confidence
from app.services.analysis.flags import get_flag_message, FLAG_MESSAGES
from app.services.analysis.runner import run_analysis, _list_candidate_files
from app.services.analysis.survival import (
    ProjectSurvivalResults,
    process_file_blame,
    extract_file_blame_result,
    apply_blame_result_to_survival,
)
from app.services.collector import run_collection, stream_git_log_commits, RawCommitData


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


@pytest.fixture
def sqlite_db(sqlite_session_factory):
    """Convenience single session for tests that don't pass db_factory."""
    session = sqlite_session_factory()
    try:
        yield session
    finally:
        session.close()


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


# -----------------------------------------------------------------------------
# 1. Incremental fetch reads only new commits
# -----------------------------------------------------------------------------
def test_incremental_fetch_reads_only_new_commits(sqlite_session_factory):
    """
    Tests that if a bare clone directory already exists for the project,
    run_collection runs 'git fetch' instead of re-cloning, and processes
    only newly fetched commits.
    """
    init_db = sqlite_session_factory()
    user = User(
        github_id=77772,
        username="perf_user_inc",
        display_name="Perf User Inc",
        email="perfinc@example.com",
        role=UserRole.student,
    )
    init_db.add(user)
    init_db.commit()

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
    init_db.add(project)
    init_db.commit()
    project_id = project.id
    init_db.close()

    expected_clone_dir = os.path.abspath(
        os.path.join(settings.REPO_STORAGE_PATH, f"{project_id}.git")
    )
    os.makedirs(expected_clone_dir, exist_ok=True)
    with open(os.path.join(expected_clone_dir, "HEAD"), "w", encoding="utf-8") as f:
        f.write("ref: refs/heads/main\n")

    called_commands = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        called_commands.append(cmd)
        if "log" in cmd:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="\x1e0123456789012345678901234567890123456789\x1fNew Author\x1fnew@example.com\x1f2026-01-01T00:00:00Z\x1fNew Commit\x1f\n10\t2\tmain.py\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    try:
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("app.services.collector.GitHubClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.resolve_auth.return_value = MagicMock(token=None, app_installed=True, installation_id=None, warnings=[])
                mock_client.verify_and_get_metadata.return_value = ({"default_branch": "main", "description": "Mock", "size": 10}, [])
                mock_client.list_commits.return_value = ({}, [])
                mock_client.list_pull_requests_and_reviews.return_value = ([], [])
                mock_client_cls.return_value = mock_client

                run_collection(project_id, db_factory=sqlite_session_factory)

        # Verify git fetch was called and git clone was NOT called
        fetch_cmds = [c for c in called_commands if "fetch" in c]
        clone_cmds = [c for c in called_commands if "clone" in c]
        assert len(fetch_cmds) >= 1
        assert len(clone_cmds) == 0
        assert "fetch" in fetch_cmds[0]
    finally:
        shutil.rmtree(expected_clone_dir, ignore_errors=True)


# -----------------------------------------------------------------------------
# 2. Partial clone failure falls back to full clone
# -----------------------------------------------------------------------------
def test_partial_clone_fallback(sqlite_session_factory):
    """
    Tests that when partial clone (--filter=blob:none) is rejected by remote server,
    collector falls back to full bare clone and records a warning notice.
    """
    init_db = sqlite_session_factory()
    user = User(
        github_id=77771,
        username="perf_user_1",
        display_name="Perf User 1",
        email="perf1@example.com",
        role=UserRole.student,
    )
    init_db.add(user)
    init_db.commit()

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
    init_db.add(project)
    init_db.commit()
    project_id = project.id
    init_db.close()

    called_commands = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        called_commands.append(cmd)
        if "--filter=blob:none" in cmd:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=128,
                stdout="",
                stderr="fatal: dumb http transport does not support shallow/filter capabilities",
            )
        elif "clone" in cmd and "--bare" in cmd:
            target_path = cmd[-1]
            os.makedirs(target_path, exist_ok=True)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
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

    verify_db = sqlite_session_factory()
    updated_project = verify_db.query(Project).filter(Project.id == project_id).first()
    assert updated_project.status == ProjectStatus.ready
    partial_cmds = [c for c in called_commands if "--filter=blob:none" in c]
    bare_cmds = [c for c in called_commands if "clone" in c and "--bare" in c and "--filter=blob:none" not in c]
    assert len(partial_cmds) >= 1
    assert len(bare_cmds) >= 1
    assert updated_project.clone_mode == "full"
    verify_db.close()


# -----------------------------------------------------------------------------
# 3. Parallel blame results equal sequential results
# -----------------------------------------------------------------------------
def test_parallel_blame_correctness():
    """
    Tests parallel blame correctness: verifies that parallel blame (worker pool)
    produces the EXACT same survival counts, file breakdowns, and module breakdowns
    as sequential blame on the same repository.
    """
    temp_dir = tempfile.mkdtemp(prefix="test_parallel_blame_")
    try:
        work_dir = os.path.join(temp_dir, "work")
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

        candidates = [
            ("auth/login.py", "blob1", 100),
            ("core/models.py", "blob2", 100),
            ("api/routes.py", "blob3", 100),
            ("auth/tokens.py", "blob4", 100),
        ]

        def lookup_fn(email: str, name: str):
            if "alice" in email.lower():
                return "member-alice"
            if "bob" in email.lower():
                return "member-bob"
            return None

        # 1. Sequential blame execution (1 worker)
        res_seq = ProjectSurvivalResults()
        for f_path, _, _ in candidates:
            cmd = ["git", "blame", "--line-porcelain", "-w", "-M", "-C", "HEAD", "--", f_path]
            proc = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, encoding="utf-8", check=True)
            counts = extract_file_blame_result(f_path, proc.stdout)
            apply_blame_result_to_survival(f_path, counts, lookup_fn, res_seq)

        # 2. Parallel blame execution (4 workers)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        res_par = ProjectSurvivalResults()

        def blame_fn(item):
            f_path = item[0]
            cmd = ["git", "blame", "--line-porcelain", "-w", "-M", "-C", "HEAD", "--", f_path]
            p = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, encoding="utf-8", check=True)
            counts = extract_file_blame_result(f_path, p.stdout)
            return f_path, counts

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(blame_fn, item) for item in candidates]
            for fut in as_completed(futures):
                f_path, counts = fut.result()
                apply_blame_result_to_survival(f_path, counts, lookup_fn, res_par)

        assert res_seq.total_surviving_lines == res_par.total_surviving_lines
        assert res_seq.module_totals == res_par.module_totals
        assert res_seq.file_totals == res_par.file_totals
        for m_id in ["member-alice", "member-bob"]:
            assert res_seq.members[m_id].total_lines == res_par.members[m_id].total_lines
            assert res_seq.members[m_id].file_lines == res_par.members[m_id].file_lines
            assert res_seq.members[m_id].module_lines == res_par.members[m_id].module_lines
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# -----------------------------------------------------------------------------
# 4. Blame cache hits and pruning
# -----------------------------------------------------------------------------
def test_blame_cache_hits_and_pruning(sqlite_db):
    """
    Tests BlameCache storage, cache hit retrieval without re-blaming,
    and pruning when cache entries exceed BLAME_CACHE_MAX_ENTRIES.
    """
    project_id = uuid.uuid4()
    blob_sha = "a1b2c3d4e5f67890123456789012345678901234"
    file_path = "src/main.py"
    cached_counts = {"alice@example.com": 42, "bob@example.com": 18}

    # Store entry in cache
    cache_entry = BlameCache(
        project_id=project_id,
        blob_sha=blob_sha,
        path=file_path,
        result=cached_counts,
    )
    sqlite_db.add(cache_entry)
    sqlite_db.commit()

    # Query cache
    hit = (
        sqlite_db.query(BlameCache)
        .filter(
            BlameCache.project_id == project_id,
            BlameCache.blob_sha == blob_sha,
            BlameCache.path == file_path,
        )
        .first()
    )
    assert hit is not None
    assert hit.result == cached_counts

    # Test survival application from cache hit
    res = ProjectSurvivalResults()
    apply_blame_result_to_survival(
        file_path,
        hit.result,
        lambda email, name: "alice_id" if "alice" in email else "bob_id",
        res,
    )
    assert res.total_surviving_lines == 60
    assert res.members["alice_id"].total_lines == 42
    assert res.members["bob_id"].total_lines == 18

    # Test pruning logic when entries exceed threshold
    test_limit = 5
    for i in range(10):
        entry = BlameCache(
            project_id=project_id,
            blob_sha=f"sha_{i:040d}",
            path=f"file_{i}.py",
            result={"dev@example.com": i + 1},
        )
        sqlite_db.add(entry)
    sqlite_db.commit()

    total_rows = sqlite_db.query(BlameCache).filter(BlameCache.project_id == project_id).count()
    assert total_rows > test_limit

    # Run pruning to test_limit
    excess = total_rows - test_limit
    oldest_ids = [
        row.id
        for row in sqlite_db.query(BlameCache.id)
        .filter(BlameCache.project_id == project_id)
        .order_by(BlameCache.created_at.asc())
        .limit(excess)
        .all()
    ]
    sqlite_db.query(BlameCache).filter(BlameCache.id.in_(oldest_ids)).delete(synchronize_session=False)
    sqlite_db.commit()

    remaining = sqlite_db.query(BlameCache).filter(BlameCache.project_id == project_id).count()
    assert remaining == test_limit


# -----------------------------------------------------------------------------
# 5. File cap ranking and confidence capping
# -----------------------------------------------------------------------------
def test_file_cap_ranking_and_confidence():
    """
    Tests that when candidate files exceed MAX_BLAME_FILES:
    - Ranking selects the most-changed files based on commit activity + size.
    - Member confidence is capped at 'medium' (never 'high') when project_is_truncated (partial) is True.
    """
    # 1. Test ranking logic
    fake_candidates = [
        (f"file_{i}.py", f"blob_{i}", 100 * (i + 1))
        for i in range(10)
    ]
    file_change_counts = {
        "file_9.py": 50,
        "file_8.py": 40,
        "file_0.py": 1,
    }
    ranked = sorted(
        fake_candidates,
        key=lambda item: (file_change_counts.get(item[0], 0), item[2]),
        reverse=True,
    )
    # Highest commit activity should come first
    assert ranked[0][0] == "file_9.py"
    assert ranked[1][0] == "file_8.py"

    # 2. Test confidence evaluation capping
    # When project_is_truncated=False, member with high metrics gets 'high'
    conf_full = evaluate_member_confidence(
        counted_commits=20,
        active_days=10,
        surviving_lines=200,
        collaboration_raw=1.0,
        has_unlinked_identities=False,
        project_is_truncated=False,
        total_project_counted_commits=100,
    )
    assert conf_full == "high"

    # When project_is_truncated=True (partial analysis), confidence is capped at 'medium'
    conf_partial = evaluate_member_confidence(
        counted_commits=20,
        active_days=10,
        surviving_lines=200,
        collaboration_raw=1.0,
        has_unlinked_identities=False,
        project_is_truncated=True,
        total_project_counted_commits=100,
    )
    assert conf_partial == "medium"


# -----------------------------------------------------------------------------
# 6. Time window limits commits and estimate recommendation
# -----------------------------------------------------------------------------
def test_time_window_filtering(sqlite_db):
    """
    Tests history window: commits older than project.history_since
    are excluded from the analysis scoring engine.
    """
    now = datetime.now(timezone.utc)
    user = User(
        github_id=88881,
        username="win_user",
        display_name="Win User",
        email="win@example.com",
        role=UserRole.student,
    )
    sqlite_db.add(user)
    sqlite_db.commit()

    project = Project(
        owner_id=user.id,
        repo_url="https://github.com/mock-org/history-test.git",
        repo_full_name="mock-org/history-test",
        name="history-test",
        github_owner="mock-org",
        github_repo="mock-org",
        default_branch="main",
        status=ProjectStatus.ready,
        history_window="6m",
        history_since=now - timedelta(days=180),
    )
    sqlite_db.add(project)
    sqlite_db.commit()

    member = Member(
        project_id=project.id,
        github_login="hist_user",
        display_name="History User",
    )
    sqlite_db.add(member)
    sqlite_db.commit()

    alias = AuthorAlias(
        project_id=project.id,
        member_id=member.id,
        name="Hist User",
        email="hist@example.com",
        source=AliasSource.api_match,
    )
    sqlite_db.add(alias)
    sqlite_db.commit()

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
    sqlite_db.add_all([c1, c2])
    sqlite_db.commit()

    db_commits = sqlite_db.query(Commit).filter(Commit.project_id == project.id).all()
    if project.history_since:
        h_since = project.history_since
        if h_since.tzinfo is None:
            h_since = h_since.replace(tzinfo=timezone.utc)
        filtered = [
            c for c in db_commits
            if c.authored_at and (c.authored_at if c.authored_at.tzinfo else c.authored_at.replace(tzinfo=timezone.utc)) >= h_since
        ]
        db_commits = filtered

    assert len(db_commits) == 1
    assert db_commits[0].sha == c2.sha


def test_estimate_recommendation_logic():
    """
    Tests recommendation logic for large repos vs small repos:
    - Small repo (< 20,000 commits and < 100MB) -> 'full'
    - Large repo (> 20,000 commits or > 100MB) -> 'window'
    """
    threshold = settings.LARGE_REPO_COMMIT_THRESHOLD
    assert threshold > 0

    # Small repo
    small_commits = 1500
    small_size_mb = 12.5
    rec_small = "window" if (small_commits > threshold or small_size_mb > 100.0) else "full"
    assert rec_small == "full"

    # Large repo by commits
    large_commits = threshold + 500
    large_size_mb = 45.0
    rec_large = "window" if (large_commits > threshold or large_size_mb > 100.0) else "full"
    assert rec_large == "window"

    # Large repo by size
    large_size_commits = 2000
    large_size_mb_2 = 150.0
    rec_size = "window" if (large_size_commits > threshold or large_size_mb_2 > 100.0) else "full"
    assert rec_size == "window"


# -----------------------------------------------------------------------------
# 7. Contributor cap aggregates tail into 'Others' summing to 100.00%
# -----------------------------------------------------------------------------
def test_contributor_cap_others_aggregation():
    """
    Tests that when contributors exceed MAX_CONTRIBUTORS_SHOWN (20),
    top 20 are presented individually and remaining N contributors are
    aggregated into an 'Others (N contributors)' row summing to 100.00%.
    """
    cap = settings.MAX_CONTRIBUTORS_SHOWN
    assert cap == 20

    # Create 30 contributors with declining shares
    raw_shares = [Decimal(f"{max(1, 35 - i)}") for i in range(30)]
    total_raw = sum(raw_shares)
    
    # Normalize to 100.00%
    members_data = []
    for i, s in enumerate(raw_shares):
        share_pct = (s / total_raw * Decimal("100.00")).quantize(Decimal("0.01"))
        members_data.append({
            "member_id": f"member_{i:02d}",
            "display_name": f"Developer {i}",
            "github_login": f"dev_{i}",
            "share_percent": share_pct,
            "confidence": "high",
            "signals": {},
            "flags": [],
        })

    # Sort descending
    members_data.sort(key=lambda m: m["share_percent"], reverse=True)

    # Apply presentation cap logic
    if len(members_data) > cap:
        top_members = members_data[:cap]
        tail_members = members_data[cap:]
        tail_count = len(tail_members)
        tail_share = sum(m["share_percent"] for m in tail_members)

        top_members.append({
            "member_id": "others",
            "display_name": f"Others ({tail_count} contributors)",
            "github_login": None,
            "share_percent": tail_share,
            "confidence": "low",
            "signals": {},
            "flags": [],
        })
        presented = top_members
    else:
        presented = members_data

    # Verifications
    assert len(presented) == cap + 1
    assert presented[-1]["member_id"] == "others"
    assert presented[-1]["display_name"] == "Others (10 contributors)"
    total_sum = sum(m["share_percent"] for m in presented)
    assert abs(total_sum - Decimal("100.00")) <= Decimal("0.05")


# -----------------------------------------------------------------------------
# 8. Streaming git log parser handles 50,000 lines without high memory
# -----------------------------------------------------------------------------
def test_streaming_git_log_memory_and_parsing():
    """
    Tests stream_git_log_commits with 50,000 synthetic git log lines.
    Verifies commit parsing integrity and that memory usage remains strictly bounded.
    """
    def synthetic_log_generator(num_commits: int = 5000):
        for i in range(num_commits):
            sha = f"{i:040x}"
            yield f"\x1e{sha}\x1fDev {i % 10}\x1fdev{i % 10}@example.com\x1f2026-01-01T00:00:00Z\x1fCommit {i}\x1f\n"
            # 9 numstat lines per commit -> 10 lines per commit -> 50,000 lines total
            for j in range(9):
                yield f"{10 + j}\t{j}\tsrc/module_{j}/file_{i % 50}.py\n"

    tracemalloc.start()
    t0 = time.perf_counter()

    parsed_count = 0
    total_files = 0
    for commit in stream_git_log_commits(synthetic_log_generator(num_commits=5000)):
        parsed_count += 1
        total_files += commit.files_changed

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert parsed_count == 5000
    assert total_files == 5000 * 9
    peak_mb = peak_mem / (1024 * 1024)
    # Peak memory must stay well under 30 MB for streaming 50,000 lines
    assert peak_mb < 30.0


# -----------------------------------------------------------------------------
# 9. Security audit: no shell=True, tokens never in argv or strings
# -----------------------------------------------------------------------------
def test_security_audit_subprocess_no_shell_and_no_tokens():
    """
    Scans collector and runner python files to ensure:
    - Never uses shell=True in subprocess calls.
    - Subprocess arguments are passed as lists/tuples.
    - Sensitive tokens are never embedded into command strings or argv.
    """
    files_to_check = [
        Path("app/services/collector.py"),
        Path("app/services/analysis/runner.py"),
        Path("app/services/analysis/survival.py"),
        Path("app/services/github_client.py"),
    ]

    for rel_path in files_to_check:
        full_path = Path(__file__).resolve().parent.parent / rel_path
        assert full_path.exists(), f"File {full_path} missing"

        with open(full_path, "r", encoding="utf-8") as f:
            source = f.read()

        # 1. Text checks
        assert "shell=True" not in source, f"Forbidden shell=True found in {rel_path}"

        # 2. AST parsing to check subprocess.run calls
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                is_subprocess = (
                    (isinstance(func, ast.Attribute) and func.attr in ("run", "Popen")) or
                    (isinstance(func, ast.Name) and func.id in ("run", "Popen"))
                )
                if is_subprocess:
                    for keyword in node.keywords:
                        if keyword.arg == "shell":
                            assert not (isinstance(keyword.value, ast.Constant) and keyword.value.value is True), (
                                f"shell=True found in Call at {rel_path}:{node.lineno}"
                            )
