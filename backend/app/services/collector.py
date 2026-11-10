import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple
import uuid
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.projects import Project, ProjectStatus
from app.models.commits import Commit
from app.models.pull_requests import PullRequest, Review
from app.models.author_aliases import AuthorAlias
from app.services.github_client import GitHubClient, RepoAccessError
from app.services.identity import (
    RawCommitData,
    resolve_identities,
    sync_identities_and_commits_to_db,
)
from app.services.progress import record_step_timing, set_progress

logger = logging.getLogger(__name__)


def _remove_readonly(func, path, excinfo):
    import stat
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _safe_rmtree(path: str) -> None:
    if os.path.exists(path):
        try:
            shutil.rmtree(path, onexc=_remove_readonly)
        except Exception:
            try:
                shutil.rmtree(path, onerror=_remove_readonly)
            except Exception:
                shutil.rmtree(path, ignore_errors=True)


def _sanitize_git_error(stderr: str, secrets: List[Optional[str]]) -> str:
    cleaned = stderr or ""
    for s in secrets:
        if s:
            cleaned = cleaned.replace(s, "[REDACTED]")

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    fatal_lines = [l for l in lines if l.lower().startswith("fatal:") or l.lower().startswith("error:")]
    if fatal_lines:
        first_err = fatal_lines[0]
    elif lines:
        non_cloning = [l for l in lines if not l.lower().startswith("cloning into")]
        first_err = non_cloning[0] if non_cloning else lines[0]
    else:
        first_err = "fatal: clone process exited with an error"

    return f"Clone failed: {first_err}"


# Strict repository URL pattern
GITHUB_URL_PATTERN = re.compile(
    r"^https:\/\/github\.com\/([A-Za-z0-9_.-]{1,100})\/([A-Za-z0-9_.-]{1,100})(?:\.git)?\/?$"
)

# Concurrency semaphore: max 2 concurrent runs
COLLECTION_SEMAPHORE = threading.Semaphore(2)

# Per-project execution lock for collector
_COLLECTOR_PROJECT_LOCKS: Dict[uuid.UUID, threading.Lock] = {}
_COLLECTOR_LOCKS_GUARD = threading.Lock()


def _get_project_lock(project_id: uuid.UUID) -> threading.Lock:
    with _COLLECTOR_LOCKS_GUARD:
        if project_id not in _COLLECTOR_PROJECT_LOCKS:
            _COLLECTOR_PROJECT_LOCKS[project_id] = threading.Lock()
        return _COLLECTOR_PROJECT_LOCKS[project_id]


def _parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _update_project_progress(db: Session, project: Project, step: str, percent: int) -> None:
    """Updates progress step and percent on the project without failing."""
    try:
        project.progress_step = step
        project.progress_percent = percent
        db.commit()
    except Exception:
        pass


REPO_URL_ERROR_MESSAGE = "Enter a GitHub repository link like https://github.com/owner/repo"
REPO_IDENT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def normalize_repo_url(raw: Any) -> Tuple[str, str, str]:
    """
    Normalizes a GitHub repository URL:
    - trim whitespace; accept http or https or no scheme; accept github.com and www.github.com only
    - strip a trailing ".git" from the repo name (case-insensitive) BEFORE any API call or database save,
      strip trailing slashes, and ignore anything after the repo name (/tree/..., /blob/..., /issues, query strings, #fragments)
    - owner and repo must match ^[A-Za-z0-9_.-]{1,100}$ and must not start with "-"; a repo literally named ".git" or empty is rejected
    - canonical_url is always https://github.com/{owner}/{repo}
    - reject other hosts, ssh (git@github.com:...), file:, extra schemes, and anything else with a plain message
    Returns (owner, repo, canonical_url).
    """
    if not raw or not isinstance(raw, str):
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    cleaned = raw.strip()
    if not cleaned:
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    # Reject ssh (git@...), file:, and anything with @
    if "@" in cleaned or cleaned.lower().startswith("file:"):
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    # Parse scheme if present
    if "://" in cleaned:
        scheme, rest = cleaned.split("://", 1)
        if scheme.lower() not in ("http", "https"):
            raise ValueError(REPO_URL_ERROR_MESSAGE)
    else:
        rest = cleaned

    # Strip query strings and fragment
    rest = rest.split("#", 1)[0].split("?", 1)[0]

    # Split host and path
    parts = rest.split("/", 1)
    host = parts[0].strip().lower()
    if host not in ("github.com", "www.github.com"):
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    if len(parts) < 2:
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    path = parts[1].strip("/")
    path_segments = [s.strip() for s in path.split("/") if s.strip()]
    if len(path_segments) < 2:
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    owner = path_segments[0]
    repo = path_segments[1]

    # Strip trailing .git (case-insensitive) BEFORE validation or use
    if repo.lower().endswith(".git"):
        repo = repo[:-4]

    # Strip trailing slashes
    repo = repo.strip("/")

    # Reject repo literally named .git (or empty after stripping)
    if not repo or repo.lower() == ".git":
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    # Reject names starting with '-'
    if owner.startswith("-") or repo.startswith("-"):
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    # Validate regex ^[A-Za-z0-9_.-]{1,100}$
    if not REPO_IDENT_PATTERN.match(owner) or not REPO_IDENT_PATTERN.match(repo):
        raise ValueError(REPO_URL_ERROR_MESSAGE)

    canonical_url = f"https://github.com/{owner}/{repo}"
    return owner, repo, canonical_url


def validate_and_parse_github_url(url: str) -> Tuple[str, str, str]:
    """
    Validates the GitHub URL strictly:
    - Must start with https://github.com/
    - Owner and repo must match ^[A-Za-z0-9_.-]{1,100}$
    - Neither owner nor repo may start with '-'
    - Rebuilds canonical URL: https://github.com/{owner}/{repo}.git
    Returns (owner, repo, canonical_url).
    Raises ValueError on invalid URL.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Repository URL must be a non-empty string.")

    cleaned_url = url.strip()
    match = GITHUB_URL_PATTERN.match(cleaned_url)
    if not match:
        raise ValueError("Invalid GitHub URL. Must be in the format https://github.com/owner/repo.")

    owner, repo = match.group(1), match.group(2)

    if owner.startswith("-") or repo.startswith("-"):
        raise ValueError("GitHub owner and repository names cannot start with a hyphen.")

    canonical_url = f"https://github.com/{owner}/{repo}.git"
    return owner, repo, canonical_url


def stream_git_log_commits(stream: Iterator[str]) -> Iterator[RawCommitData]:
    """
    Parses machine-readable git log output formatted with Unit Separator (\x1f)
    and Record Separator (\x1e):
    --format=\x1e%H\x1f%an\x1f%ae\x1f%aI\x1f%s\x1f%P
    Followed by numstat lines.
    Streams commits line-by-line without buffering full output in memory.
    """
    current_commit: Optional[RawCommitData] = None

    for raw_line in stream:
        line = raw_line.strip("\r\n")
        if not line:
            continue

        if "\x1e" in line:
            # New commit record begins
            parts_rec = line.split("\x1e")
            if current_commit is not None:
                yield current_commit
                current_commit = None

            header_str = parts_rec[-1].strip()
            if not header_str:
                continue

            parts = header_str.split("\x1f")
            if len(parts) < 5:
                continue

            sha = parts[0].strip()
            author_name = parts[1].strip()
            author_email = parts[2].strip()
            authored_date_str = parts[3].strip()
            subject = parts[4].strip()
            parents_str = parts[5].strip() if len(parts) >= 6 else ""

            authored_at = _parse_iso_datetime(authored_date_str) or datetime.now(timezone.utc)
            parents = parents_str.split() if parents_str else []
            parent_count = len(parents)

            current_commit = RawCommitData(
                sha=sha,
                author_name=author_name,
                author_email=author_email,
                authored_at=authored_at,
                subject=subject,
                additions=0,
                deletions=0,
                files_changed=0,
                parent_count=parent_count,
            )
        elif current_commit is not None:
            # Numstat line for current commit
            stat_parts = line.strip().split("\t")
            if len(stat_parts) >= 3:
                current_commit.files_changed += 1
                add_str, del_str = stat_parts[0], stat_parts[1]
                if add_str.isdigit():
                    current_commit.additions += int(add_str)
                if del_str.isdigit():
                    current_commit.deletions += int(del_str)

    if current_commit is not None:
        yield current_commit


def parse_git_log_output(output: str) -> List[RawCommitData]:
    """
    Parses machine-readable git log output.
    Kept for backward-compatibility with existing tests and callers.
    """
    if not output:
        return []
    return list(stream_git_log_commits(io.StringIO(output)))


def run_collection(
    project_id: uuid.UUID,
    github_client: Optional[GitHubClient] = None,
    db_factory=SessionLocal
) -> None:
    """
    Executes the repository collection pipeline for a project:
    1. Sets status to analyzing.
    2. Verifies repo metadata and checks size limits.
    3. Performs hardened bare clone with in-memory token.
    4. Parses local git history using machine-readable git log --numstat.
    5. Enriches data via GitHub API (commits, pull requests, reviews).
    6. Merges identities, stores commits/PRs, and updates contributions.
    7. Updates status to ready with warnings, or failed with safe error_message.
    """
    # Enforce concurrency limit
    acquired = COLLECTION_SEMAPHORE.acquire(blocking=True)
    temp_hooks_dir = None

    try:
        db: Session = db_factory()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return

            project.status = ProjectStatus.analyzing
            project.error_message = None
            db.commit()

            owner = project.github_owner
            repo = project.github_repo
            submitting_user = project.owner

            if not owner or not repo or not submitting_user:
                project.status = ProjectStatus.failed
                project.error_message = "Project metadata is incomplete."
                db.commit()
                return

            client = github_client or GitHubClient()
            t_collection_start = time.time()
            timing_summary: Dict[str, float] = {}

            # Step 1: Resolve Auth and verify repo metadata
            _update_project_progress(db, project, "Verifying repository metadata...", 5)
            t_auth_start = time.time()
            auth_res = client.resolve_auth(owner, repo)
            token = auth_res.token
            all_warnings: List[str] = list(auth_res.warnings)

            try:
                meta, meta_warns = client.verify_and_get_metadata(
                    owner, repo, submitting_user.username, token
                )
                all_warnings.extend(meta_warns)
            except RepoAccessError as rae:
                project.status = ProjectStatus.failed
                project.error_message = rae.message
                db.commit()
                return

            default_branch = meta.get("default_branch") or "main"
            size_kb = meta.get("size", 0)
            is_private = bool(meta.get("private", False))
            description = meta.get("description")

            project.default_branch = default_branch
            project.is_private = is_private
            if description and not project.description:
                project.description = description
            if auth_res.installation_id:
                project.github_installation_id = auth_res.installation_id

            max_size_kb = settings.MAX_REPO_SIZE_MB * 1024
            has_window = bool(project.history_since or getattr(project, "history_window_months", None))
            if size_kb > max_size_kb and not has_window:
                size_mb = round(size_kb / 1024, 1)
                project.status = ProjectStatus.failed
                project.error_message = (
                    f"Repository size ({size_mb} MB) exceeds maximum allowed size ({settings.MAX_REPO_SIZE_MB} MB)."
                )
                db.commit()
                return

            db.commit()
            t_auth_elapsed = time.time() - t_auth_start
            timing_summary["estimate"] = round(t_auth_elapsed, 3)
            record_step_timing(project.id, "estimate", timing_summary["estimate"], db_factory=db_factory)
            logger.info("Timing [Collection] estimate: %.2fs", t_auth_elapsed)

            # Step 2: Clone or Fetch repository bare (protected with per-project lock)
            proj_lock = _get_project_lock(project.id)
            with proj_lock:
                t_clone_start = time.time()
                os.makedirs(settings.REPO_STORAGE_PATH, exist_ok=True)
                clone_path = os.path.abspath(
                    os.path.join(settings.REPO_STORAGE_PATH, f"{project.id}.git")
                )
                project.clone_path = clone_path

                temp_hooks_dir = tempfile.mkdtemp(prefix="git_empty_hooks_")

                clone_env = os.environ.copy()
                clone_env["GIT_TERMINAL_PROMPT"] = "0"

                if auth_res.installation_id and token:
                    auth_header = f"Authorization: Basic {base64.b64encode(f'x-access-token:{token}'.encode()).decode()}"
                    clone_env["GIT_CONFIG_COUNT"] = "1"
                    clone_env["GIT_CONFIG_KEY_0"] = "http.extraheader"
                    clone_env["GIT_CONFIG_VALUE_0"] = auth_header

                is_incremental = bool(os.path.exists(clone_path) and os.path.exists(os.path.join(clone_path, "HEAD")))
                clone_success = False
                clone_mode = getattr(project, "clone_mode", None)

                if is_incremental:
                    set_progress(project.id, "Fetching repository updates...", 0, 100, db_factory=db_factory)
                    fetch_cmd = [
                        "git",
                        "--git-dir",
                        clone_path,
                        "-c",
                        f"core.hooksPath={temp_hooks_dir}",
                        "-c",
                        "protocol.file.allow=never",
                        "-c",
                        "core.fsmonitor=false",
                        "fetch",
                        "--prune",
                        "origin",
                        "+refs/heads/*:refs/heads/*",
                    ]
                    fetch_proc = subprocess.run(
                        fetch_cmd,
                        env=clone_env,
                        capture_output=True,
                        text=True,
                        timeout=settings.CLONE_TIMEOUT_SECONDS,
                        shell=False,
                    )
                    if fetch_proc.returncode == 0:
                        clone_success = True
                        clone_mode = clone_mode or "partial"
                    else:
                        logger.warning("Incremental git fetch failed, falling back to clean clone: %s", fetch_proc.stderr[:200])
                        is_incremental = False
                        _safe_rmtree(clone_path)

                if not clone_success:
                    _safe_rmtree(clone_path)
                    if getattr(project, "last_collected_at", None) is not None:
                        set_progress(project.id, "Re-collecting repository history...", 0, 100, db_factory=db_factory)
                    else:
                        set_progress(project.id, "Cloning repository...", 0, 100, db_factory=db_factory)

                    canonical_url = f"https://github.com/{owner}/{repo}"
                    clone_url = f"{canonical_url}.git"

                    # Attempt 1: Partial clone with --filter=blob:none --no-checkout --bare
                    partial_clone_cmd = [
                        "git",
                        "clone",
                        "--filter=blob:none",
                        "--no-checkout",
                        "--bare",
                        "-c",
                        f"core.hooksPath={temp_hooks_dir}",
                        "-c",
                        "protocol.file.allow=never",
                        "-c",
                        "core.fsmonitor=false",
                    ]
                    if project.history_since:
                        shallow_date = project.history_since.strftime("%Y-%m-%d")
                        partial_clone_cmd.append(f"--shallow-since={shallow_date}")
                    partial_clone_cmd.extend(["--", clone_url, clone_path])

                    proc = subprocess.run(
                        partial_clone_cmd,
                        env=clone_env,
                        capture_output=True,
                        text=True,
                        timeout=settings.CLONE_TIMEOUT_SECONDS,
                        shell=False,
                    )

                    # If shallow-since failed, retry partial without shallow-since
                    if proc.returncode != 0 and project.history_since:
                        _safe_rmtree(clone_path)
                        retry_partial = [
                            "git",
                            "clone",
                            "--filter=blob:none",
                            "--no-checkout",
                            "--bare",
                            "-c",
                            f"core.hooksPath={temp_hooks_dir}",
                            "-c",
                            "protocol.file.allow=never",
                            "-c",
                            "core.fsmonitor=false",
                            "--",
                            clone_url,
                            clone_path,
                        ]
                        proc = subprocess.run(
                            retry_partial,
                            env=clone_env,
                            capture_output=True,
                            text=True,
                            timeout=settings.CLONE_TIMEOUT_SECONDS,
                            shell=False,
                        )

                    if proc.returncode == 0:
                        clone_success = True
                        clone_mode = "partial"
                        project.clone_mode = "partial"
                    else:
                        logger.warning("Partial clone failed (%s); falling back to full bare clone", proc.stderr[:200])
                        all_warnings.append("Server rejected partial clone (--filter=blob:none); fell back to full bare clone.")
                        clone_mode = "full"
                        project.clone_mode = "full"
                        _safe_rmtree(clone_path)
                        full_clone_cmd = [
                            "git",
                            "clone",
                            "--bare",
                            "-c",
                            f"core.hooksPath={temp_hooks_dir}",
                            "-c",
                            "protocol.file.allow=never",
                            "-c",
                            "core.fsmonitor=false",
                            "--",
                            clone_url,
                            clone_path,
                        ]
                        proc = subprocess.run(
                            full_clone_cmd,
                            env=clone_env,
                            capture_output=True,
                            text=True,
                            timeout=settings.CLONE_TIMEOUT_SECONDS,
                            shell=False,
                        )

                    if proc.returncode != 0:
                        project.status = ProjectStatus.failed
                        secrets_to_mask = [token, settings.GITHUB_API_TOKEN]
                        project.error_message = _sanitize_git_error(proc.stderr, secrets_to_mask)
                        db.commit()
                        return

                project.clone_mode = clone_mode
                t_clone_elapsed = round(time.time() - t_clone_start, 3)
                timing_summary["clone"] = t_clone_elapsed
                record_step_timing(project.id, "clone", t_clone_elapsed, db_factory=db_factory)
                logger.info("Timing [Collection] clone: %.2fs", t_clone_elapsed)

                # Step 3: Read commit history locally via streaming git log
                set_progress(project.id, "Reading commits...", 0, 100, db_factory=db_factory)
                t_log_start = time.time()

                since_filter: Optional[str] = None
                revision_range = default_branch
                if is_incremental and project.last_collected_at:
                    latest_commit = (
                        db.query(Commit.sha)
                        .filter(Commit.project_id == project.id)
                        .order_by(Commit.authored_at.desc())
                        .first()
                    )
                    if latest_commit:
                        old_head = latest_commit[0]
                        chk = subprocess.run(
                            ["git", "--git-dir", clone_path, "cat-file", "-e", old_head],
                            capture_output=True,
                            shell=False,
                        )
                        if chk.returncode == 0:
                            revision_range = f"{old_head}..{default_branch}"
                elif project.history_since:
                    since_filter = project.history_since.isoformat()

                log_format = "\x1e%H\x1f%an\x1f%ae\x1f%aI\x1f%s\x1f%P"
                log_cmd = [
                    "git",
                    "--git-dir",
                    clone_path,
                    "log",
                    revision_range,
                    f"-n{settings.MAX_COMMITS + 1}",
                    "--numstat",
                    f"--format={log_format}",
                ]
                if since_filter:
                    log_cmd.append(f"--since={since_filter}")

                log_proc = subprocess.Popen(
                    log_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                )

                raw_commits: List[RawCommitData] = []
                capped = False
                est_total = getattr(project, "estimated_commits", None) or 500

                if log_proc.stdout:
                    for commit_item in stream_git_log_commits(log_proc.stdout):
                        if len(raw_commits) >= settings.MAX_COMMITS:
                            capped = True
                            try:
                                log_proc.terminate()
                                log_proc.wait(timeout=3)
                            except Exception:
                                pass
                            break
                        raw_commits.append(commit_item)
                        if len(raw_commits) % 500 == 0:
                            set_progress(
                                project.id,
                                f"Reading commits {len(raw_commits)} of {max(len(raw_commits), est_total)}",
                                len(raw_commits),
                                max(len(raw_commits), est_total),
                                db_factory=db_factory,
                            )

                log_proc.wait()
                if capped:
                    all_warnings.append(
                        f"Commit count capped at maximum limit of {settings.MAX_COMMITS} commits."
                    )

                t_log_elapsed = round(time.time() - t_log_start, 3)
                timing_summary["read_history"] = t_log_elapsed
                record_step_timing(project.id, "read_history", t_log_elapsed, db_factory=db_factory)
                logger.info("Timing [Collection] read_history: %.2fs", t_log_elapsed)
                set_progress(
                    project.id,
                    f"Reading commits {len(raw_commits)} of {len(raw_commits)}",
                    len(raw_commits),
                    len(raw_commits),
                    db_factory=db_factory,
                )

                # Step 4: API enrichment (commits & pull requests) concurrently
                set_progress(project.id, "Fetching pull requests & reviews...", 0, 100, db_factory=db_factory)
                t_api_start = time.time()

                with ThreadPoolExecutor(max_workers=settings.FETCH_WORKERS) as api_pool:
                    future_commits = api_pool.submit(
                        client.list_commits, owner, repo, token, settings.MAX_COMMITS
                    )
                    future_prs = api_pool.submit(
                        client.list_pull_requests_and_reviews, owner, repo, token, settings.MAX_PULL_REQUESTS
                    )
                    sha_to_login, commit_warns = future_commits.result()
                    prs_data, pr_warns = future_prs.result()

                all_warnings.extend(commit_warns)
                all_warnings.extend(pr_warns)

                t_api_elapsed = round(time.time() - t_api_start, 3)
                timing_summary["api_enrichment"] = t_api_elapsed
                record_step_timing(project.id, "api_enrichment", t_api_elapsed, db_factory=db_factory)
                logger.info("Timing [Collection] api_enrichment: %.2fs", t_api_elapsed)
            timing_summary["github_api"] = round(t_api_elapsed, 3)
            logger.info("Timing [Collection] github_api: %.2fs", t_api_elapsed)

            # Save Pull Requests and Reviews
            pr_extra_logins: List[str] = []
            for pr_item in prs_data:
                author_login = pr_item.get("author_login")
                author_login_clean = author_login.strip().lower() if author_login else None
                if author_login_clean:
                    pr_extra_logins.append(author_login_clean)

                pr_num = pr_item["number"]
                existing_pr = db.query(PullRequest).filter(
                    PullRequest.project_id == project.id,
                    PullRequest.number == pr_num
                ).first()

                created_at_dt = _parse_iso_datetime(pr_item.get("created_at"))
                merged_at_dt = _parse_iso_datetime(pr_item.get("merged_at"))

                if not existing_pr:
                    pr_record = PullRequest(
                        project_id=project.id,
                        number=pr_num,
                        title=pr_item.get("title", ""),
                        author_login=author_login_clean,
                        state=pr_item.get("state", "closed"),
                        merged=pr_item.get("merged", False),
                        created_at=created_at_dt or datetime.now(timezone.utc),
                        merged_at=merged_at_dt,
                    )
                    db.add(pr_record)
                    db.flush()
                else:
                    pr_record = existing_pr
                    if author_login_clean and pr_record.author_login != author_login_clean:
                        pr_record.author_login = author_login_clean
                    pr_record.state = pr_item.get("state", "closed")
                    pr_record.merged = pr_item.get("merged", False)
                    pr_record.merged_at = merged_at_dt
                    db.flush()

                # Add reviews
                for rev_item in pr_item.get("reviews", []):
                    rev_login = rev_item.get("reviewer_login")
                    rev_login_clean = rev_login.strip().lower() if rev_login else None
                    if rev_login_clean:
                        pr_extra_logins.append(rev_login_clean)

                    sub_dt = _parse_iso_datetime(rev_item.get("submitted_at"))

                    # Avoid duplicate review rows
                    existing_rev = db.query(Review).filter(
                        Review.pull_request_id == pr_record.id,
                        func.lower(Review.reviewer_login) == rev_login_clean,
                        Review.state == rev_item.get("state", "COMMENTED")
                    ).first() if rev_login_clean else None
                    if not existing_rev and rev_login_clean:
                        rev_record = Review(
                            pull_request_id=pr_record.id,
                            reviewer_login=rev_login_clean,
                            state=rev_item.get("state", "COMMENTED"),
                            submitted_at=sub_dt,
                        )
                        db.add(rev_record)

            db.flush()

            # Step 5: Identity resolution and DB sync
            _update_project_progress(db, project, "Resolving identities & syncing database...", 60)
            t_sync_start = time.time()

            existing_manual_aliases = (
                db.query(AuthorAlias)
                .filter(AuthorAlias.project_id == project.id)
                .all()
            )
            manual_map: Dict[Tuple[str, str], Tuple[Optional[str], Optional[uuid.UUID]]] = {}
            for a in existing_manual_aliases:
                if a.source.value == "manual":
                    member_login = a.member.github_login.strip().lower() if (a.member and a.member.github_login) else None
                    manual_map[(a.email.strip().lower(), a.name.strip().lower())] = (
                        member_login,
                        a.member_id,
                    )

            resolved_aliases = resolve_identities(
                commits=raw_commits,
                sha_to_login=sha_to_login,
                existing_manual_assignments=manual_map,
            )

            sync_identities_and_commits_to_db(
                db=db,
                project_id=project.id,
                resolved_aliases=resolved_aliases,
                commits=raw_commits,
                pr_extra_logins=pr_extra_logins,
            )

            t_sync_elapsed = time.time() - t_sync_start
            timing_summary["identity"] = round(t_sync_elapsed, 3)
            record_step_timing(project.id, "identity", timing_summary["identity"], db_factory=db_factory)
            logger.info("Timing [Collection] identity: %.2fs", t_sync_elapsed)

            # Step 6: Mark project ready and store timings
            t_total_elapsed = round(time.time() - t_collection_start, 3)
            timing_summary["total"] = t_total_elapsed
            logger.info("Timing [Collection] total: %.2fs", t_total_elapsed)

            current_timing_stats = dict(project.timing_stats) if project.timing_stats else {}
            current_timing_stats["collection"] = timing_summary
            project.timing_stats = current_timing_stats
            project.timings = current_timing_stats

            deduped_warnings = list(dict.fromkeys(w for w in all_warnings if w))
            total_stored_commits = db.query(Commit).filter(Commit.project_id == project.id).count()
            project.commit_total = total_stored_commits
            project.last_collected_at = datetime.now(timezone.utc)
            project.warnings = "; ".join(deduped_warnings) if deduped_warnings else None
            project.status = ProjectStatus.ready
            set_progress(project.id, "Collection complete", 70, 100, db_factory=db_factory)
            db.commit()

            # Step 7: Run analysis and scoring engine
            try:
                from app.services.analysis.runner import run_analysis
                run_analysis(project_id=project.id, db_factory=db_factory)
            except Exception as analysis_err:
                logger.warning("Analysis step failed for project %s: %s", project_id, analysis_err)

        except subprocess.TimeoutExpired:
            db.rollback()
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = ProjectStatus.failed
                project.error_message = (
                    f"Repository clone timed out after {settings.CLONE_TIMEOUT_SECONDS} seconds."
                )
                db.commit()
        except Exception as e:
            db.rollback()
            err_msg = str(e)
            if token:
                err_msg = err_msg.replace(token, "[REDACTED]")
            logger.error("Repository collection failed for project %s: %s", project_id, err_msg)
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = ProjectStatus.failed
                project.error_message = (
                    "An unexpected error occurred while analyzing the repository history."
                )
                db.commit()
        finally:
            db.close()

    finally:
        if temp_hooks_dir:
            _safe_rmtree(temp_hooks_dir)
        COLLECTION_SEMAPHORE.release()
