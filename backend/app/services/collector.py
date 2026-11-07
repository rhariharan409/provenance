import base64
from datetime import datetime, timezone
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Dict, List, Optional, Tuple
import uuid
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.projects import Project, ProjectStatus
from app.models.pull_requests import PullRequest, Review
from app.models.author_aliases import AuthorAlias
from app.services.github_client import GitHubClient, RepoAccessError
from app.services.identity import (
    RawCommitData,
    resolve_identities,
    sync_identities_and_commits_to_db,
)

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


def _parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


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


def parse_git_log_output(output: str) -> List[RawCommitData]:
    """
    Parses machine-readable git log output formatted with Unit Separator (\x1f)
    and Record Separator (\x1e):
    --format=\x1e%H\x1f%an\x1f%ae\x1f%aI\x1f%s\x1f%P
    Followed by numstat lines.
    """
    commits: List[RawCommitData] = []
    if not output:
        return commits

    records = output.split("\x1e")
    for record in records:
        trimmed = record.strip()
        if not trimmed:
            continue

        lines = trimmed.split("\n")
        header_line = lines[0].strip()
        parts = header_line.split("\x1f")
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

        additions = 0
        deletions = 0
        files_changed = 0

        # Parse numstat lines
        for numstat_line in lines[1:]:
            stat_parts = numstat_line.strip().split("\t")
            if len(stat_parts) >= 3:
                files_changed += 1
                add_str, del_str = stat_parts[0], stat_parts[1]
                if add_str.isdigit():
                    additions += int(add_str)
                if del_str.isdigit():
                    deletions += int(del_str)

        commits.append(
            RawCommitData(
                sha=sha,
                author_name=author_name,
                author_email=author_email,
                authored_at=authored_at,
                subject=subject,
                additions=additions,
                deletions=deletions,
                files_changed=files_changed,
                parent_count=parent_count,
            )
        )

    return commits


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

            # Step 1: Resolve Auth and verify repo metadata
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
            if size_kb > max_size_kb:
                size_mb = round(size_kb / 1024, 1)
                project.status = ProjectStatus.failed
                project.error_message = (
                    f"Repository size ({size_mb} MB) exceeds maximum allowed size ({settings.MAX_REPO_SIZE_MB} MB)."
                )
                db.commit()
                return

            db.commit()

            # Step 2: Clone repository bare
            os.makedirs(settings.REPO_STORAGE_PATH, exist_ok=True)
            clone_path = os.path.abspath(
                os.path.join(settings.REPO_STORAGE_PATH, f"{project.id}.git")
            )
            project.clone_path = clone_path

            _safe_rmtree(clone_path)

            temp_hooks_dir = tempfile.mkdtemp(prefix="git_empty_hooks_")

            clone_env = os.environ.copy()
            clone_env["GIT_TERMINAL_PROMPT"] = "0"

            # For public repos where no GitHub App installation token exists, do NOT send any
            # Authorization header to git. Clone anonymously, and use the PAT only for API calls.
            # Only use the extraheader for GitHub App installation tokens (private repos).
            if auth_res.installation_id and token:
                auth_header = f"Authorization: Basic {base64.b64encode(f'x-access-token:{token}'.encode()).decode()}"
                clone_env["GIT_CONFIG_COUNT"] = "1"
                clone_env["GIT_CONFIG_KEY_0"] = "http.extraheader"
                clone_env["GIT_CONFIG_VALUE_0"] = auth_header

            clone_cmd = [
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
                f"https://github.com/{owner}/{repo}.git",
                clone_path,
            ]

            proc = subprocess.run(
                clone_cmd,
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

            # Step 3: Read commit history locally via git log
            log_format = "\x1e%H\x1f%an\x1f%ae\x1f%aI\x1f%s\x1f%P"
            log_cmd = [
                "git",
                "--git-dir",
                clone_path,
                "log",
                default_branch,
                f"-n{settings.MAX_COMMITS + 1}",
                "--numstat",
                f"--format={log_format}",
            ]

            log_proc = subprocess.run(
                log_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                shell=False,
            )

            if log_proc.returncode != 0:
                project.status = ProjectStatus.failed
                project.error_message = "Failed to parse commit history from repository."
                db.commit()
                return

            raw_commits = parse_git_log_output(log_proc.stdout)
            if len(raw_commits) > settings.MAX_COMMITS:
                raw_commits = raw_commits[: settings.MAX_COMMITS]
                all_warnings.append(
                    f"Commit count capped at maximum limit of {settings.MAX_COMMITS} commits."
                )

            # Step 4: API enrichment (commits & pull requests)
            sha_to_login, commit_warns = client.list_commits(
                owner, repo, token, settings.MAX_COMMITS
            )
            all_warnings.extend(commit_warns)

            prs_data, pr_warns = client.list_pull_requests_and_reviews(
                owner, repo, token, settings.MAX_PULL_REQUESTS
            )
            all_warnings.extend(pr_warns)

            # Save Pull Requests and Reviews
            pr_extra_logins: List[str] = []
            for pr_item in prs_data:
                author_login = pr_item.get("author_login")
                if author_login:
                    pr_extra_logins.append(author_login)

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
                        author_login=author_login,
                        state=pr_item.get("state", "closed"),
                        merged=pr_item.get("merged", False),
                        created_at=created_at_dt or datetime.now(timezone.utc),
                        merged_at=merged_at_dt,
                    )
                    db.add(pr_record)
                    db.flush()
                else:
                    pr_record = existing_pr
                    pr_record.state = pr_item.get("state", "closed")
                    pr_record.merged = pr_item.get("merged", False)
                    pr_record.merged_at = merged_at_dt
                    db.flush()

                # Add reviews
                for rev_item in pr_item.get("reviews", []):
                    rev_login = rev_item.get("reviewer_login")
                    if rev_login:
                        pr_extra_logins.append(rev_login)

                    sub_dt = _parse_iso_datetime(rev_item.get("submitted_at"))

                    # Avoid duplicate review rows
                    existing_rev = db.query(Review).filter(
                        Review.pull_request_id == pr_record.id,
                        Review.reviewer_login == rev_login,
                        Review.state == rev_item.get("state", "COMMENTED")
                    ).first()
                    if not existing_rev and rev_login:
                        rev_record = Review(
                            pull_request_id=pr_record.id,
                            reviewer_login=rev_login,
                            state=rev_item.get("state", "COMMENTED"),
                            submitted_at=sub_dt,
                        )
                        db.add(rev_record)

            db.flush()

            # Step 5: Identity resolution and DB sync
            # Fetch existing manual assignments to preserve them
            existing_manual_aliases = (
                db.query(AuthorAlias)
                .filter(AuthorAlias.project_id == project.id)
                .all()
            )
            manual_map: Dict[Tuple[str, str], Tuple[Optional[str], Optional[uuid.UUID]]] = {}
            for a in existing_manual_aliases:
                if a.source.value == "manual":
                    member_login = a.member.github_login if a.member else None
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

            # Step 6: Mark project ready
            deduped_warnings = list(dict.fromkeys(w for w in all_warnings if w))
            project.commit_total = len(raw_commits)
            project.last_collected_at = datetime.now(timezone.utc)
            project.warnings = "; ".join(deduped_warnings) if deduped_warnings else None
            project.status = ProjectStatus.ready
            db.commit()

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
