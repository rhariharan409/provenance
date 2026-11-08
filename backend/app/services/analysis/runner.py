from datetime import datetime, timezone
from decimal import Decimal
import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.author_aliases import AuthorAlias
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
from app.services.analysis.survival import ProjectSurvivalResults, process_file_blame

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


def _list_candidate_files(clone_path: str, head_sha: str) -> Tuple[List[Tuple[str, int]], int, int]:
    """
    Lists files in bare repository via git ls-tree -r -l <head_sha>.
    Returns (candidate_files, files_total, files_ignored).
    Each candidate is (path, size_bytes).
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
        return [], 0, 0

    candidate_files: List[Tuple[str, int]] = []
    files_total = 0
    files_ignored = 0

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
        if len(meta_tokens) >= 4 and meta_tokens[3].isdigit():
            size_bytes = int(meta_tokens[3])

        files_total += 1
        ignored, _ = is_ignored(file_path, size_bytes)
        if ignored:
            files_ignored += 1
        else:
            candidate_files.append((file_path, size_bytes or 0))

    return candidate_files, files_total, files_ignored


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
                project.analysis_status = "failed"
                project.analysis_error = "Repository bare clone was not found."
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
            db.commit()
            db.refresh(analysis_run)
            run_id = analysis_run.id

            # 1. Candidate file selection
            candidates, files_total, files_ignored = _list_candidate_files(clone_path, head_sha)

            is_truncated = False
            project_flags: List[str] = []

            if len(candidates) > settings.MAX_BLAME_FILES:
                is_truncated = True
                project_flags.append("truncated")
                # Sort by size descending and cap
                candidates.sort(key=lambda x: x[1], reverse=True)
                candidates = candidates[:settings.MAX_BLAME_FILES]

            files_analyzed = len(candidates)

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

            # 3. Blame and survival processing
            survival_results = ProjectSurvivalResults()
            per_file_timeout = 25

            for file_path, _ in candidates:
                # Check global analysis timeout
                elapsed = time.time() - start_time
                if elapsed > settings.ANALYSIS_TIMEOUT_SECONDS:
                    is_truncated = True
                    if "truncated" not in project_flags:
                        project_flags.append("truncated")
                    break

                blame_cmd = [
                    "git",
                    "--git-dir",
                    clone_path,
                    "blame",
                    "--line-porcelain",
                    "-w",
                    "-M",
                    "-C",
                    head_sha,
                    "--",
                    file_path,
                ]
                try:
                    blame_proc = subprocess.run(
                        blame_cmd,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        shell=False,
                        timeout=per_file_timeout,
                    )
                    if blame_proc.returncode == 0:
                        process_file_blame(
                            file_path=file_path,
                            blame_output=blame_proc.stdout,
                            alias_lookup_fn=lookup_member,
                            results=survival_results,
                        )
                except subprocess.TimeoutExpired:
                    continue
                except Exception as ex:
                    logger.debug("Blame failed for %s: %s", file_path, ex)
                    continue

            # 4. Effective change over stored commits
            db_commits = db.query(Commit).filter(Commit.project_id == project.id).all()
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

            # 5. Module ownership
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

            # 6. Collaboration
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

            # 7. Final scoring
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
            run_stats = {
                "files_total": files_total,
                "files_analyzed": files_analyzed,
                "files_ignored": files_ignored,
                "lines_surviving": survival_results.total_surviving_lines,
                "commits_counted": commits_counted,
                "commits_excluded": commits_excluded,
                "truncated": is_truncated,
                "project_flags": project_flags,
            }

            analysis_run.status = AnalysisRunStatus.complete
            analysis_run.finished_at = datetime.now(timezone.utc)
            analysis_run.stats = run_stats
            analysis_run.weights = effective_weights

            project.analysis_status = "complete"
            project.analysis_error = None
            db.commit()
            logger.info("Analysis completed successfully for project %s in %.2fs", project.id, time.time() - start_time)

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
