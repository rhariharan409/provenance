from datetime import datetime, timezone, timedelta
from decimal import Decimal
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import pytest

from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.author_aliases import AliasSource, AuthorAlias
from app.models.commits import Commit
from app.models.contribution_scores import ContributionScore
from app.models.members import Member
from app.models.projects import Project, ProjectStatus
from app.services.analysis.effective_change import compute_commit_effective_change
from app.services.analysis.file_filter import is_ignored
from app.services.analysis.flags import (
    check_late_dump,
    check_low_data,
    check_single_bulk_commit,
)
from app.services.analysis.runner import run_analysis, _list_candidate_files


def run_git_cmd(cwd: str, args: list[str], env: dict | None = None) -> str:
    """Helper to run git commands with arguments list and check output."""
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


def test_analysis_e2e_git_repo(db_session, test_user):
    """
    End-to-end Git analysis test:
    - Author A writes a module and a 5000-line lockfile.
    - Author B writes code in small commits and reformats Author A's file with whitespace only.
    - Assert Author B's whitespace-only commit adds 0 effective lines.
    - Assert lockfile is ignored.
    - Assert blame survival credits Author A for original lines (blame with -w).
    - Assert scores sum to exactly 100.00%.
    """
    temp_dir = tempfile.mkdtemp(prefix="test_prov_git_")
    try:
        work_dir = os.path.join(temp_dir, "work")
        bare_dir = os.path.join(temp_dir, "bare.git")
        os.makedirs(work_dir, exist_ok=True)

        # Initialize working git repo
        run_git_cmd(work_dir, ["init", "-b", "main"])
        run_git_cmd(work_dir, ["config", "user.name", "Test Init"])
        run_git_cmd(work_dir, ["config", "user.email", "init@example.com"])

        # Environment for Author A
        env_a = {
            "GIT_AUTHOR_NAME": "Author A",
            "GIT_AUTHOR_EMAIL": "author_a@example.com",
            "GIT_COMMITTER_NAME": "Author A",
            "GIT_COMMITTER_EMAIL": "author_a@example.com",
        }
        # Environment for Author B
        env_b = {
            "GIT_AUTHOR_NAME": "Author B",
            "GIT_AUTHOR_EMAIL": "author_b@example.com",
            "GIT_COMMITTER_NAME": "Author B",
            "GIT_COMMITTER_EMAIL": "author_b@example.com",
        }

        # 1. Author A writes src/module.py (50 lines) and package-lock.json (5000 lines)
        src_dir = os.path.join(work_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        module_path = os.path.join(src_dir, "module.py")
        code_lines = [f"def func_{i}():\n    return {i}\n" for i in range(25)]
        with open(module_path, "w", encoding="utf-8") as f:
            f.writelines(code_lines)

        lock_path = os.path.join(work_dir, "package-lock.json")
        lock_lines = [f'{{"line_{i}": true}},\n' for i in range(5000)]
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write("[\n")
            f.writelines(lock_lines)
            f.write("]\n")

        run_git_cmd(work_dir, ["add", "src/module.py", "package-lock.json"])
        run_git_cmd(work_dir, ["commit", "-m", "Commit 1: Author A initial code and lockfile"], env=env_a)
        c1_sha = run_git_cmd(work_dir, ["rev-parse", "HEAD"])

        # 2. Author B reformats src/module.py with whitespace only (adding trailing spaces/blank lines)
        with open(module_path, "w", encoding="utf-8") as f:
            for line in code_lines:
                f.write(line.rstrip() + "   \n")  # whitespace only modification

        run_git_cmd(work_dir, ["add", "src/module.py"])
        run_git_cmd(work_dir, ["commit", "-m", "Commit 2: Author B whitespace reformat"], env=env_b)
        c2_sha = run_git_cmd(work_dir, ["rev-parse", "HEAD"])

        # 3. Author B adds small code commit (helper.py: 10 lines)
        helper_path = os.path.join(src_dir, "helper.py")
        helper_lines = [f"def helper_{i}(): return {i}\n" for i in range(10)]
        with open(helper_path, "w", encoding="utf-8") as f:
            f.writelines(helper_lines)

        run_git_cmd(work_dir, ["add", "src/helper.py"])
        run_git_cmd(work_dir, ["commit", "-m", "Commit 3: Author B helper module"], env=env_b)
        c3_sha = run_git_cmd(work_dir, ["rev-parse", "HEAD"])

        # Clone bare to bare_dir
        run_git_cmd(temp_dir, ["clone", "--bare", work_dir, bare_dir])

        # Verification 1: Lockfile is ignored
        ignored, reason = is_ignored("package-lock.json")
        assert ignored is True
        assert "lockfile" in reason.lower()

        candidates, total_f, ignored_f = _list_candidate_files(bare_dir, c3_sha)
        candidate_paths = [c[0] for c in candidates]
        assert "package-lock.json" not in candidate_paths
        assert "src/module.py" in candidate_paths
        assert "src/helper.py" in candidate_paths
        assert ignored_f >= 1

        # Verification 2: Author B's whitespace-only commit adds 0 effective lines
        eff_lines, raw_lines, excluded, _ = compute_commit_effective_change(
            commit_sha=c2_sha,
            parent_count=1,
            is_bot=False,
            repo_path=bare_dir,
        )
        assert excluded is False
        assert eff_lines == 0.0, f"Expected 0 effective lines for whitespace-only commit, got {eff_lines}"

        # Verification 3: Blame survival credits Author A for original lines (due to -w)
        blame_out = run_git_cmd(
            bare_dir,
            ["blame", "--line-porcelain", "-w", "-M", "-C", c3_sha, "--", "src/module.py"]
        )
        # All lines in src/module.py should originate from c1_sha (Author A)
        assert c1_sha[:8] in blame_out
        assert c2_sha[:8] not in blame_out, "Author B's whitespace commit should be ignored by git blame -w"

        # Verification 4: End-to-end database + runner pipeline
        project = Project(
            owner_id=test_user.id,
            repo_url="https://github.com/test/e2e-repo.git",
            repo_full_name="test/e2e-repo",
            name="e2e-repo",
            clone_path=bare_dir,
            default_branch="main",
            status=ProjectStatus.ready,
            analysis_status="pending",
        )
        db_session.add(project)
        db_session.flush()

        member_a = Member(
            project_id=project.id,
            display_name="Author A",
            github_login="author_a_gh",
        )
        member_b = Member(
            project_id=project.id,
            display_name="Author B",
            github_login="author_b_gh",
        )
        db_session.add_all([member_a, member_b])
        db_session.flush()
        m_a_id = member_a.id
        m_b_id = member_b.id

        alias_a = AuthorAlias(
            project_id=project.id,
            member_id=m_a_id,
            email="author_a@example.com",
            name="Author A",
            source=AliasSource.name_match,
        )
        alias_b = AuthorAlias(
            project_id=project.id,
            member_id=m_b_id,
            email="author_b@example.com",
            name="Author B",
            source=AliasSource.name_match,
        )
        db_session.add_all([alias_a, alias_b])

        # Add Commits to DB
        commit_records = [
            Commit(
                project_id=project.id,
                sha=c1_sha,
                author_name="Author A",
                author_email="author_a@example.com",
                authored_at=datetime.now(timezone.utc) - timedelta(days=5),
                subject="Commit 1: Author A initial code and lockfile",
                parent_count=0,
                additions=5050,
                deletions=0,
                alias_id=alias_a.id,
            ),
            Commit(
                project_id=project.id,
                sha=c2_sha,
                author_name="Author B",
                author_email="author_b@example.com",
                authored_at=datetime.now(timezone.utc) - timedelta(days=2),
                subject="Commit 2: Author B whitespace reformat",
                parent_count=1,
                additions=50,
                deletions=50,
                alias_id=alias_b.id,
            ),
            Commit(
                project_id=project.id,
                sha=c3_sha,
                author_name="Author B",
                author_email="author_b@example.com",
                authored_at=datetime.now(timezone.utc) - timedelta(days=1),
                subject="Commit 3: Author B helper module",
                parent_count=1,
                additions=10,
                deletions=0,
                alias_id=alias_b.id,
            ),
        ]
        db_session.add_all(commit_records)
        db_session.commit()

        # Run analysis using db_session
        run_analysis(project.id, db_factory=lambda: db_session)

        # Reload project and scores
        project = db_session.query(Project).filter(Project.id == project.id).first()
        assert project.analysis_status == "complete", f"Analysis failed: {project.analysis_error}"

        scores = db_session.query(ContributionScore).filter(
            ContributionScore.project_id == project.id
        ).all()
        assert len(scores) == 2

        score_map = {s.member_id: s for s in scores}
        score_a = score_map[m_a_id]
        score_b = score_map[m_b_id]

        # Author A should have majority of the survival signal
        assert score_a.signals["survival"]["raw"] > score_b.signals["survival"]["raw"]

        # Scores must sum to exactly 100.00%
        total_pct = sum([s.share_percent for s in scores], Decimal("0.00"))
        assert total_pct == Decimal("100.00"), f"Expected 100.00%, got {total_pct}"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_flags_firing_scenarios():
    """
    Asserts flags single_bulk_commit, late_dump and low_data fire in the constructed scenarios.
    """
    # 1. single_bulk_commit flag
    # Scenario: One commit has 900 lines added out of 1000 total (> 80% and >= 300)
    bulk_commits = [900, 50, 30, 20]
    assert check_single_bulk_commit(bulk_commits) is True

    # Negative scenario: Distributed commits
    balanced_commits = [200, 250, 180, 220, 150]
    assert check_single_bulk_commit(balanced_commits) is False

    # 2. late_dump flag
    # Scenario: 4 commits over 6 months, then 8 commits in the last 24 hours (> 70% in last 48h)
    base_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    early_dates = [base_time - timedelta(days=90 - i * 10) for i in range(3)]
    late_dates = [base_time - timedelta(hours=i * 2) for i in range(10)]
    all_dates = early_dates + late_dates
    assert check_late_dump(all_dates) is True

    # Negative scenario: Evenly distributed over 2 weeks
    regular_dates = [base_time - timedelta(days=i) for i in range(14)]
    assert check_late_dump(regular_dates) is False

    # 3. low_data flag
    # Scenario: Fewer than 10 counted commits
    assert check_low_data(5) is True
    assert check_low_data(9) is True
    assert check_low_data(10) is False
    assert check_low_data(25) is False
