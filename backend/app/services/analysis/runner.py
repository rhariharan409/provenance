from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.author_aliases import AuthorAlias
from app.models.blame_cache import BlameCache
from app.models.commits import Commit
from app.models.contributions import Contribution
from app.models.contribution_scores import ContributionScore, ScoreConfidence
from app.models.members import Member
from app.models.projects import Project
from app.models.pull_requests import PullRequest, Review
from app.services.analysis.collaboration import PRData, compute_collaboration_scores
from app.services.analysis.confidence import evaluate_member_confidence
from app.services.analysis.effective_change import compute_commit_effective_change
from app.services.analysis.file_filter import is_ignored
from app.services.analysis.flags import (
    check_late_dump,
    check_rewritten_history,
    check_single_bulk_commit,
    get_flag_message,
)
from app.services.analysis.ownership import compute_module_ownership
from app.services.analysis.scoring import calculate_final_scores
from app.services.analysis.survival import (
    ProjectSurvivalResults,
    apply_blame_result_to_survival,
    extract_file_blame_result,
    get_top_level_module,
    process_file_blame,
)
from app.services.progress import record_step_timing, set_progress

logger = logging.getLogger(__name__)

# Max 2 concurrent analysis runs system-wide
ANALYSIS_SEMAPHORE = threading.Semaphore(2)

# Per-project execution lock
_PROJECT_LOCKS: Dict[uuid.UUID, threading.Lock] = {}
_LOCKS_DICT_GUARD = threading.Lock()


def _get_project_lock(project_id: uuid.UUID) -> threading.Lock:
    with _LOCKS_DICT_GUARD:
        if project_id not in _PROJECT_LOCKS:
            _PROJECT_LOCKS[project_id] = threading.Lock()
        return _PROJECT_LOCKS[project_id]


def _resolve_head_sha(clone_path: str, default_branch: Optional[str] = None) -> Optional[str]:
    """
    Resolves the HEAD commit sha from bare clone repository.
    """
    branches_to_try = [default_branch, "HEAD", "main", "master"] if default_branch else ["HEAD", "main", "master"]
    for b in branches_to_try:
        if not b:
            continue
        cmd = ["git", "--git-dir", clone_path, "rev-parse", f"{b}^{{commit}}"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=False,
            timeout=15,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            if len(sha) == 40:
                return sha
    return None


class CandidateFilesResult(tuple):
    candidate_files: List[Tuple[str, int, str]]
    files_total: int
    files_ignored: int
    ignored_reasons: Dict[str, int]

    def __new__(cls, candidate_files, files_total, files_ignored, ignored_reasons=None):
        obj = super().__new__(cls, (candidate_files, files_total, files_ignored))
        obj.candidate_files = candidate_files
        obj.files_total = files_total
        obj.files_ignored = files_ignored
        obj.ignored_reasons = ignored_reasons or {}
        return obj


def _list_candidate_files(clone_path: str, head_sha: str) -> CandidateFilesResult:
    """
    Lists files in bare repository via git ls-tree -r -l <head_sha>.
    Returns CandidateFilesResult(candidate_files, files_total, files_ignored, ignored_reasons).
    Each candidate is (path, size_bytes, blob_sha).
    """
    cmd = ["git", "--git-dir", clone_path, "ls-tree", "-r", "-l", head_sha]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=60,
    )
    if proc.returncode != 0:
        return CandidateFilesResult([], 0, 0, {})

    candidate_files: List[Tuple[str, int, str]] = []
    files_total = 0
    files_ignored = 0
    ignored_reasons: Dict[str, int] = {}

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: <mode> SP <type> SP <object> SP <size>\t<file>
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta_part, file_path = parts[0], parts[1].strip()
        meta_tokens = meta_part.split()
        size_bytes = None
        blob_sha = meta_tokens[2] if len(meta_tokens) >= 3 else ""
        if len(meta_tokens) >= 4 and meta_tokens[3].isdigit():
            size_bytes = int(meta_tokens[3])

        files_total += 1
        ignored, reason = is_ignored(file_path, size_bytes)

        # Check license banner if file is > 20 KB and not ignored yet
        if not ignored and size_bytes and size_bytes > 20 * 1024 and blob_sha:
            try:
                p = subprocess.Popen(
                    ["git", "--git-dir", clone_path, "cat-file", "blob", blob_sha],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                )
                preview = p.stdout.read(2048) if p.stdout else b""
                if p.stdout:
                    p.stdout.close()
                p.terminate()
                p.wait()
                if preview:
                    is_lic, lic_reason = is_ignored(file_path, size_bytes, content_preview=preview)
                    if is_lic:
                        ignored, reason = is_lic, lic_reason
            except Exception:
                pass

        if ignored:
            files_ignored += 1
            reason_cat = reason.split(":")[0].strip() if ":" in reason else reason
            ignored_reasons[reason_cat] = ignored_reasons.get(reason_cat, 0) + 1
        else:
            candidate_files.append((file_path, size_bytes or 0, blob_sha))

    return CandidateFilesResult(candidate_files, files_total, files_ignored, ignored_reasons)


def _process_and_record_blame(
    file_path: str,
    blame_output: str,
    alias_lookup_fn: Callable[[str, str], Optional[str]],
    results: ProjectSurvivalResults,
) -> Dict[str, Any]:
    meaningful_lines = process_file_blame(
        file_path=file_path,
        blame_output=blame_output,
        alias_lookup_fn=alias_lookup_fn,
        results=results,
    )
    module = get_top_level_module(file_path)
    member_breakdown: Dict[str, int] = {}
    for m_id, m_data in results.members.items():
        if file_path in m_data.file_lines:
            member_breakdown[m_id] = m_data.file_lines[file_path]
    return {
        "meaningful_lines": meaningful_lines,
        "module": module,
        "member_lines": member_breakdown,
    }


def _apply_cached_file_survival(
    file_path: str,
    cached_data: Dict[str, Any],
    results: ProjectSurvivalResults,
) -> None:
    m_lines = cached_data.get("meaningful_lines", 0)
    module = cached_data.get("module") or get_top_level_module(file_path)
    results.total_surviving_lines += m_lines
    results.module_totals[module] = results.module_totals.get(module, 0) + m_lines
    results.file_totals[file_path] = m_lines
    for m_id, cnt in cached_data.get("member_lines", {}).items():
        m_data = results.get_or_create_member(m_id)
        m_data.total_lines += cnt
        m_data.file_lines[file_path] = cnt
        m_data.module_lines[module] = m_data.module_lines.get(module, 0) + cnt


def _update_analysis_progress(
    db: Session,
    project: Project,
    step: str,
    percent: int,
) -> None:
    try:
        project.progress_step = step
        project.progress_percent = percent
        db.commit()
    except Exception:
        db.rollback()


def run_analysis(
    project_id: uuid.UUID | str,
    db_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """
    Orchestrates repository contribution analysis for project_id.
    Ensures safe, bounded execution and stores evidence-backed contribution scores.
    """
    if isinstance(project_id, str):
        try:
            project_id = uuid.UUID(project_id)
        except ValueError:
            logger.error("Invalid project_id string for analysis: %s", project_id)
            return

    proj_lock = _get_project_lock(project_id)
    if not proj_lock.acquire(blocking=False):
        logger.info("Analysis for project %s is already running on this instance.", project_id)
        return

    run_id: Optional[uuid.UUID] = None
    start_time = time.time()
    analysis_timings: Dict[str, float] = {}

    try:
        if not ANALYSIS_SEMAPHORE.acquire(blocking=True, timeout=settings.ANALYSIS_TIMEOUT_SECONDS):
            logger.warning("System analysis concurrency capacity reached. Analysis skipped for %s.", project_id)
            return

        db: Session = db_factory()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                logger.error("Project %s not found for analysis", project_id)
                return

            clone_path = project.clone_path
            if not clone_path or not os.path.exists(clone_path):
                logger.info("Clone path missing for project %s (server restarted/wiped). Triggering re-clone before analysis.", project.id)
                _update_analysis_progress(db, project, "Re-collecting repository history...", 10)
                from app.services.collector import run_collection
                run_collection(project.id, db_factory=db_factory)
                db.refresh(project)
                clone_path = project.clone_path
                if not clone_path or not os.path.exists(clone_path):
                    project.analysis_status = "failed"
                    project.analysis_error = "Repository re-clone failed or clone was not found."
                    db.commit()
                    return

            # Mark running and create analysis_run
            head_sha = _resolve_head_sha(clone_path, project.default_branch)
            if not head_sha:
                project.analysis_status = "failed"
                project.analysis_error = "Could not resolve default branch HEAD commit."
                db.commit()
                return

            weights_dict = {
                "survival": settings.SCORE_WEIGHT_SURVIVAL,
                "effective_change": settings.SCORE_WEIGHT_EFFECTIVE_CHANGE,
                "ownership": settings.SCORE_WEIGHT_OWNERSHIP,
                "collaboration": settings.SCORE_WEIGHT_COLLABORATION,
            }

            analysis_run = AnalysisRun(
                project_id=project.id,
                status=AnalysisRunStatus.running,
                scoring_version="1.0",
                head_sha=head_sha,
                weights=weights_dict,
                started_at=datetime.now(timezone.utc),
            )
            db.add(analysis_run)
            project.analysis_status = "running"
            project.analysis_error = None
            _update_analysis_progress(db, project, "Analyzing repository files...", 70)
            db.refresh(analysis_run)
            run_id = analysis_run.id

            # 1. Candidate file selection
            t_list_start = time.time()
            candidates_res = _list_candidate_files(clone_path, head_sha)
            candidates, files_total, files_ignored = candidates_res
            ignored_reasons = getattr(candidates_res, "ignored_reasons", {})
            vendored_files_ignored = (
                ignored_reasons.get("vendored_library", 0) + ignored_reasons.get("license_banner", 0)
            )
            analysis_timings["list_files"] = round(time.time() - t_list_start, 3)

            is_truncated = False
            project_flags: List[str] = []
            files_candidates = len(candidates)
            files_skipped_by_cap = 0
            is_partial = bool(project.partial_analysis or project.history_since or getattr(project, "history_window_months", None))

            if files_candidates > settings.MAX_BLAME_FILES:
                is_truncated = True
                is_partial = True
                if "partial_file_coverage" not in project_flags:
                    project_flags.append("partial_file_coverage")
                try:
                    rank_cmd = ["git", "--git-dir", clone_path, "log", "--name-only", "--format=", head_sha]
                    if project.history_since:
                        rank_cmd.append(f"--since={project.history_since.isoformat()}")
                    rank_proc = subprocess.run(
                        rank_cmd,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        shell=False,
                        timeout=60,
                    )
                    file_counts = Counter(line.strip() for line in rank_proc.stdout.splitlines() if line.strip())
                except Exception:
                    file_counts = Counter()

                candidates.sort(key=lambda x: (file_counts.get(x[0], 0), x[1]), reverse=True)
                files_skipped_by_cap = files_candidates - settings.MAX_BLAME_FILES
                candidates = candidates[:settings.MAX_BLAME_FILES]

            files_blamed = len(candidates)
            files_analyzed = files_blamed
            if project.history_since and "window_applied" not in project_flags:
                project_flags.append("window_applied")

            # 2. Build alias mapping: (email, name) -> member_id
            aliases = db.query(AuthorAlias).filter(AuthorAlias.project_id == project.id).all()
            alias_map: Dict[Tuple[str, str], Optional[str]] = {}
            for a in aliases:
                email_key = a.email.strip().lower() if a.email else ""
                name_key = a.name.strip().lower() if a.name else ""
                m_str = str(a.member_id) if a.member_id else None
                alias_map[(email_key, name_key)] = m_str
                # Also index by email alone as fallback
                if email_key and (email_key, "") not in alias_map:
                    alias_map[(email_key, "")] = m_str

            def lookup_member(email: str, name: str) -> Optional[str]:
                e = email.strip().lower()
                n = name.strip().lower()
                if (e, n) in alias_map and alias_map[(e, n)]:
                    return alias_map[(e, n)]
                if (e, "") in alias_map:
                    return alias_map[(e, "")]
                return None

            # Members list
            members = db.query(Member).filter(Member.project_id == project.id).all()
            member_ids = [str(m.id) for m in members]
            member_id_to_member = {str(m.id): m for m in members}
            member_logins = {str(m.id): m.github_login for m in members}

            # 3. Blame and survival processing (with BlameCache and bounded parallel pool)
            t_blame_start = time.time()
            survival_results = ProjectSurvivalResults()
            per_file_timeout = 25
            current_file_survival: Dict[str, Any] = {}

            # Query database blame cache for this project
            cached_rows = (
                db.query(BlameCache)
                .filter(BlameCache.project_id == project.id)
                .all()
            )
            cached_map = {(r.blob_sha, r.path): r.result for r in cached_rows}

            cache_hits = 0
            cache_misses = 0
            files_to_blame: List[Tuple[str, int, str]] = []

            for item in candidates:
                f_path, size_bytes, b_sha = item
                if b_sha and (b_sha, f_path) in cached_map:
                    cache_hits += 1
                    author_counts = cached_map[(b_sha, f_path)]
                    apply_blame_result_to_survival(f_path, author_counts, lookup_member, survival_results)
                    current_file_survival[f_path] = {
                        "meaningful_lines": sum(author_counts.values()),
                        "module": get_top_level_module(f_path),
                        "member_lines": {lookup_member(em, ""): cnt for em, cnt in author_counts.items() if lookup_member(em, "")}
                    }
                else:
                    cache_misses += 1
                    files_to_blame.append(item)

            total_to_blame = len(files_to_blame)
            blamed_done = 0
            max_workers = max(1, settings.ANALYSIS_WORKERS)
            new_cache_rows: List[BlameCache] = []

            if total_to_blame > 0:
                set_progress(
                    project.id,
                    f"Blaming files 0 of {total_to_blame}",
                    0,
                    total_to_blame,
                    db_factory=db_factory,
                )

                def _blame_worker(item: Tuple[str, int, str]) -> Tuple[str, str, Optional[str]]:
                    f_path, sz, b_sha = item
                    # -w -M -C only when file is under 2000 lines (approximated by size < 80000 bytes)
                    blame_flags = ["-w", "-M", "-C"] if sz < 80000 else ["-w"]
                    cmd = [
                        "git",
                        "--git-dir",
                        clone_path,
                        "blame",
                        "--line-porcelain",
                    ] + blame_flags + [
                        head_sha,
                        "--",
                        f_path,
                    ]
                    try:
                        p = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            shell=False,
                            timeout=per_file_timeout,
                        )
                        if p.returncode == 0:
                            return f_path, b_sha, p.stdout
                    except Exception as ex:
                        logger.debug("Blame failed for %s: %s", f_path, ex)
                    return f_path, b_sha, None

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(_blame_worker, item): item[0] for item in files_to_blame}
                    for future in as_completed(futures):
                        elapsed = time.time() - start_time
                        if elapsed > settings.ANALYSIS_TIMEOUT_SECONDS:
                            is_truncated = True
                            if "truncated" not in project_flags:
                                project_flags.append("truncated")
                            for f in futures:
                                f.cancel()
                            break

                        f_path, b_sha, blame_out = future.result()
                        blamed_done += 1
                        if blame_out:
                            # Bound memory: process and discard blame_out immediately
                            email_counts = extract_file_blame_result(f_path, blame_out)
                            blame_out = None
                            apply_blame_result_to_survival(f_path, email_counts, lookup_member, survival_results)
                            current_file_survival[f_path] = {
                                "meaningful_lines": sum(email_counts.values()),
                                "module": get_top_level_module(f_path),
                                "member_lines": {lookup_member(em, ""): cnt for em, cnt in email_counts.items() if lookup_member(em, "")}
                            }
                            if b_sha:
                                new_cache_rows.append(BlameCache(
                                    project_id=project.id,
                                    blob_sha=b_sha,
                                    path=f_path,
                                    result=email_counts,
                                ))

                        set_progress(
                            project.id,
                            f"Blaming files {blamed_done} of {total_to_blame}",
                            blamed_done,
                            total_to_blame,
                            db_factory=db_factory,
                        )

                # Persist newly blamed files to BlameCache in batch
                if new_cache_rows:
                    try:
                        for row in new_cache_rows:
                            existing = db.query(BlameCache).filter(
                                BlameCache.project_id == project.id,
                                BlameCache.blob_sha == row.blob_sha,
                                BlameCache.path == row.path,
                            ).first()
                            if not existing:
                                db.add(row)
                        db.commit()

                        # Prune oldest rows beyond BLAME_CACHE_MAX_ENTRIES per project
                        total_cached = db.query(func.count(BlameCache.id)).filter(BlameCache.project_id == project.id).scalar() or 0
                        if total_cached > settings.BLAME_CACHE_MAX_ENTRIES:
                            excess = total_cached - settings.BLAME_CACHE_MAX_ENTRIES
                            oldest = (
                                db.query(BlameCache.id)
                                .filter(BlameCache.project_id == project.id)
                                .order_by(BlameCache.created_at.asc())
                                .limit(excess)
                                .all()
                            )
                            if oldest:
                                db.query(BlameCache).filter(BlameCache.id.in_([r[0] for r in oldest])).delete(synchronize_session=False)
                                db.commit()
                    except Exception as ex:
                        db.rollback()
                        logger.debug("Non-fatal blame cache persistence error: %s", ex)

            analysis_timings["git_blame"] = round(time.time() - t_blame_start, 3)
            record_step_timing(project.id, "blame", analysis_timings["git_blame"], db_factory=db_factory)

            # 4. Effective change over stored commits
            _update_analysis_progress(db, project, "Computing effective change...", 86)
            t_eff_start = time.time()
            db_commits = db.query(Commit).filter(Commit.project_id == project.id).all()

            # Apply history window filter if project has history_since
            if project.history_since:
                h_since = project.history_since
                if h_since.tzinfo is None:
                    h_since = h_since.replace(tzinfo=timezone.utc)
                filtered_commits = []
                for c in db_commits:
                    if c.authored_at:
                        c_date = c.authored_at
                        if c_date.tzinfo is None:
                            c_date = c_date.replace(tzinfo=timezone.utc)
                        if c_date >= h_since:
                            filtered_commits.append(c)
                db_commits = filtered_commits

            alias_to_bot = {a.id: a.is_bot for a in aliases}
            alias_to_member = {a.id: str(a.member_id) if a.member_id else None for a in aliases}

            member_effective_lines: Dict[str, float] = {m_id: 0.0 for m_id in member_ids}
            member_top_commits: Dict[str, List[Dict[str, Any]]] = {m_id: [] for m_id in member_ids}
            member_commit_dates: Dict[str, List[datetime]] = {m_id: [] for m_id in member_ids}
            member_counted_commits: Dict[str, int] = {m_id: 0 for m_id in member_ids}

            commits_counted = 0
            commits_excluded = 0
            commit_raw_additions: List[int] = []
            all_commit_dates: List[datetime] = []
            parent_child_dates: List[Tuple[datetime, List[datetime]]] = []
            bot_detected = False

            # Pre-index commits by sha for parent date lookups
            sha_to_commit_date = {c.sha: c.authored_at for c in db_commits if c.authored_at}

            for c in db_commits:
                is_bot = alias_to_bot.get(c.alias_id, False) if c.alias_id else False
                if is_bot:
                    bot_detected = True

                eff_lines, raw_lines, excluded, _ = compute_commit_effective_change(
                    commit_sha=c.sha,
                    parent_count=c.parent_count,
                    is_bot=is_bot,
                    repo_path=clone_path,
                )

                if excluded:
                    commits_excluded += 1
                else:
                    commits_counted += 1
                    commit_raw_additions.append(c.additions)
                    if c.authored_at:
                        all_commit_dates.append(c.authored_at)

                    # Lookup author member
                    m_id = alias_to_member.get(c.alias_id) if c.alias_id else None
                    if not m_id and c.author_email:
                        m_id = lookup_member(c.author_email, c.author_name or "")

                    if m_id and m_id in member_effective_lines:
                        member_effective_lines[m_id] += eff_lines
                        member_counted_commits[m_id] += 1
                        if c.authored_at:
                            member_commit_dates[m_id].append(c.authored_at)
                        member_top_commits[m_id].append({
                            "sha": c.sha,
                            "subject": c.subject or "",
                            "effective_lines": round(eff_lines, 2),
                        })
            analysis_timings["effective_change"] = round(time.time() - t_eff_start, 3)

            # 5. Module ownership
            t_own_start = time.time()
            member_module_lines: Dict[str, Dict[str, int]] = {m_id: {} for m_id in member_ids}
            for m_id in member_ids:
                if m_id in survival_results.members:
                    member_module_lines[m_id] = survival_results.members[m_id].module_lines

            member_ownership_signals, member_owned_modules = compute_module_ownership(
                module_totals=survival_results.module_totals,
                member_module_lines=member_module_lines,
                total_surviving_lines=survival_results.total_surviving_lines,
                min_module_lines=20,
            )
            analysis_timings["ownership"] = round(time.time() - t_own_start, 3)

            # 6. Collaboration
            _update_analysis_progress(db, project, "Analyzing ownership and collaboration...", 90)
            t_collab_start = time.time()
            db_prs = db.query(PullRequest).filter(PullRequest.project_id == project.id).all()
            pr_data_list: List[PRData] = []
            for pr in db_prs:
                rev_logins = [r.reviewer_login for r in pr.reviews if r.reviewer_login]
                pr_data_list.append(PRData(
                    number=pr.number,
                    author_login=pr.author_login,
                    state=pr.state,
                    merged=pr.merged,
                    reviewers=rev_logins,
                ))

            raw_collab, norm_collab, has_collab_data = compute_collaboration_scores(
                member_logins=member_logins,
                prs=pr_data_list,
            )
            analysis_timings["collaboration"] = round(time.time() - t_collab_start, 3)

            # 7. Final scoring
            _update_analysis_progress(db, project, "Calculating contribution scores...", 95)
            t_score_start = time.time()
            raw_survival_map: Dict[str, float] = {}
            for m_id in member_ids:
                m_data = survival_results.members.get(m_id)
                raw_survival_map[m_id] = float(m_data.total_lines) if m_data else 0.0

            final_percentages, per_member_signals, effective_weights = calculate_final_scores(
                member_ids=member_ids,
                raw_survival=raw_survival_map,
                raw_effective_change=member_effective_lines,
                raw_ownership=member_ownership_signals,
                raw_collaboration=raw_collab,
                weights=weights_dict,
                has_collaboration_data=has_collab_data,
            )

            # 8. Project-level flags
            has_unlinked = (survival_results.unlinked_surviving_lines > 0 or len(survival_results.unlinked_authors) > 0)
            if has_unlinked:
                project_flags.append("unlinked_identities")

            if not has_collab_data:
                project_flags.append("no_collaboration_data")

            if check_single_bulk_commit(commit_raw_additions):
                project_flags.append("single_bulk_commit")

            if check_late_dump(all_commit_dates):
                project_flags.append("late_dump")

            if commits_counted < 10:
                project_flags.append("low_data")

            if bot_detected:
                project_flags.append("bot_excluded")

            if check_rewritten_history(parent_child_dates):
                project_flags.append("rewritten_history_suspected")

            project_flags = list(dict.fromkeys(project_flags))

            # 9. Confidence and Member-level flags & Persistence
            # Clean up prior scores for this run
            db.query(ContributionScore).filter(ContributionScore.run_id == run_id).delete()

            for m_id in member_ids:
                m_lines = int(raw_survival_map.get(m_id, 0))
                m_commits = member_counted_commits.get(m_id, 0)
                m_dates = member_commit_dates.get(m_id, [])
                distinct_active_days = len(set(d.date() for d in m_dates))
                m_collab_raw = raw_collab.get(m_id, 0.0)

                conf_str = evaluate_member_confidence(
                    counted_commits=m_commits,
                    active_days=distinct_active_days,
                    surviving_lines=m_lines,
                    collaboration_raw=m_collab_raw,
                    has_unlinked_identities=has_unlinked,
                    project_is_truncated=is_truncated,
                    total_project_counted_commits=commits_counted,
                )

                if is_partial and conf_str == "high":
                    conf_str = "medium"

                # Member flags
                m_flags: List[str] = []
                if check_late_dump(m_dates):
                    m_flags.append("late_dump")

                # Top commits sorted by effective lines desc
                top_commits = sorted(
                    member_top_commits.get(m_id, []),
                    key=lambda x: x["effective_lines"],
                    reverse=True
                )[:5]

                # Top files sorted by surviving lines desc
                m_data = survival_results.members.get(m_id)
                top_files: List[Dict[str, Any]] = []
                if m_data and m_data.file_lines:
                    top_files = [
                        {"path": p, "surviving_lines": count}
                        for p, count in sorted(m_data.file_lines.items(), key=lambda x: x[1], reverse=True)[:5]
                    ]

                evidence_dict = {
                    "top_commits": top_commits,
                    "top_files": top_files,
                    "owned_modules": member_owned_modules.get(m_id, []),
                }

                score_row = ContributionScore(
                    run_id=analysis_run.id,
                    project_id=project.id,
                    member_id=uuid.UUID(m_id),
                    share_percent=final_percentages.get(m_id, Decimal("0.00")),
                    confidence=ScoreConfidence(conf_str),
                    signals=per_member_signals.get(m_id, {}),
                    flags=m_flags,
                    evidence=evidence_dict,
                )
                db.add(score_row)

                # Sync to contributions table
                conf_numeric = Decimal("0.90") if conf_str == "high" else (Decimal("0.60") if conf_str == "medium" else Decimal("0.30"))
                m_obj = member_id_to_member.get(m_id)
                if m_obj and m_obj.github_login:
                    contrib = db.query(Contribution).filter(
                        Contribution.project_id == project.id,
                        Contribution.github_login == m_obj.github_login
                    ).first()
                    if contrib:
                        contrib.score = final_percentages.get(m_id, Decimal("0.00"))
                        contrib.confidence = conf_numeric
                    else:
                        contrib = Contribution(
                            project_id=project.id,
                            user_id=m_obj.user_id,
                            github_login=m_obj.github_login,
                            commit_count=m_commits,
                            score=final_percentages.get(m_id, Decimal("0.00")),
                            confidence=conf_numeric,
                        )
                        db.add(contrib)

            # 10. Update analysis run stats and status
            total_elapsed = round(time.time() - start_time, 3)
            analysis_timings["scoring"] = round(time.time() - t_score_start, 3)
            analysis_timings["total"] = total_elapsed

            run_stats = {
                "files_total": files_total,
                "files_candidates": files_candidates,
                "files_blamed": files_blamed,
                "files_skipped_by_cap": files_skipped_by_cap,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "partial": is_partial,
                "window_since": project.history_since.isoformat() if project.history_since else None,
                "files_analyzed": files_analyzed,
                "files_ignored": files_ignored,
                "ignored_reasons": ignored_reasons,
                "vendored_files_ignored": vendored_files_ignored,
                "lines_surviving": survival_results.total_surviving_lines,
                "commits_counted": commits_counted,
                "commits_excluded": commits_excluded,
                "truncated": is_truncated,
                "project_flags": project_flags,
                "file_survival": current_file_survival,
                "timings": analysis_timings,
            }

            analysis_run.status = AnalysisRunStatus.complete
            analysis_run.finished_at = datetime.now(timezone.utc)
            analysis_run.stats = run_stats
            analysis_run.weights = effective_weights

            # Update project timings & progress
            p_timings = dict(project.timing_stats or {})
            p_timings["analysis"] = analysis_timings
            project.timing_stats = p_timings
            project.timings = p_timings
            project.partial_analysis = is_partial
            if project.history_since:
                project.analyzed_since = project.history_since
            project.analysis_status = "complete"
            project.analysis_error = None
            project.progress_step = "Analysis complete"
            project.progress_percent = 100
            db.commit()

            record_step_timing(project.id, "scoring", analysis_timings["scoring"], db_factory=db_factory)
            record_step_timing(project.id, "total", total_elapsed, db_factory=db_factory)
            set_progress(project.id, "Analysis complete", 100, 100, db_factory=db_factory)

            for step_name, sec in analysis_timings.items():
                logger.info("Timing [Analysis] %s: %.3fs", step_name, sec)
            logger.info("Analysis completed successfully for project %s in %.2fs", project.id, total_elapsed)

        except Exception as e:
            db.rollback()
            logger.exception("Analysis failed for project %s", project_id)
            err_msg = str(e)
            if settings.GITHUB_API_TOKEN:
                err_msg = err_msg.replace(settings.GITHUB_API_TOKEN, "[REDACTED]")

            # Safe short error
            safe_err = "An error occurred during repository analysis."
            if "not found" in err_msg.lower():
                safe_err = "Repository data not found."

            try:
                if run_id:
                    failed_run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
                    if failed_run:
                        failed_run.status = AnalysisRunStatus.failed
                        failed_run.finished_at = datetime.now(timezone.utc)
                        failed_run.error_message = safe_err

                proj_record = db.query(Project).filter(Project.id == project_id).first()
                if proj_record:
                    proj_record.analysis_status = "failed"
                    proj_record.analysis_error = safe_err
                db.commit()
            except Exception:
                db.rollback()

        finally:
            db.close()
            ANALYSIS_SEMAPHORE.release()

    finally:
        proj_lock.release()

