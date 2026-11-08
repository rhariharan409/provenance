import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import func
from app.db import SessionLocal
from app.models.analysis_runs import AnalysisRun, AnalysisRunStatus
from app.models.contribution_scores import ContributionScore
from app.models.members import Member
from app.models.projects import Project
from app.models.contributions import Contribution


def compute_ranks(values: List[float]) -> List[float]:
    """
    Computes standard fractional ranks for a list of values (accounting for ties).
    """
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n

    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1

    return ranks


def spearman_rank_correlation(x: List[float], y: List[float]) -> float:
    """
    Computes Spearman rank correlation coefficient between two lists.
    """
    if len(x) < 2 or len(y) < 2 or len(x) != len(y):
        return 1.0 if len(x) == len(y) else 0.0

    rx = compute_ranks(x)
    ry = compute_ranks(y)

    mean_rx = sum(rx) / len(rx)
    mean_ry = sum(ry) / len(ry)

    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(len(rx)))
    den_x = sum((rx[i] - mean_rx) ** 2 for i in range(len(rx)))
    den_y = sum((ry[i] - mean_ry) ** 2 for i in range(len(ry)))

    denom = math.sqrt(den_x * den_y)
    if denom == 0.0:
        return 1.0

    return num / denom


def run_comparison(ground_truth_path: Optional[str] = None):
    if not ground_truth_path:
        default_gt = backend_dir / "scripts" / "ground_truth.json"
        example_gt = backend_dir / "scripts" / "ground_truth.example.json"
        if default_gt.exists():
            ground_truth_path = str(default_gt)
        elif example_gt.exists():
            ground_truth_path = str(example_gt)
            print(f"[Note] Using example ground truth file at {ground_truth_path}")
        else:
            print("Error: No ground_truth.json found in backend/scripts/")
            return

    try:
        with open(ground_truth_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {ground_truth_path}: {e}")
        return

    db = SessionLocal()
    try:
        print("=" * 80)
        print("PROVENANCE GROUND TRUTH ACCURACY BENCHMARK")
        print("=" * 80)

        for repo_key, expected_map in data.items():
            print(f"\nTarget Repository: {repo_key}")
            print("-" * 80)

            project = db.query(Project).filter(
                func.lower(Project.repo_full_name) == repo_key.lower().strip()
            ).first()

            if not project:
                print(f"  [Skipped] Repository {repo_key} is not present in development database.")
                continue

            latest_run = (
                db.query(AnalysisRun)
                .filter(AnalysisRun.project_id == project.id, AnalysisRun.status == AnalysisRunStatus.complete)
                .order_by(AnalysisRun.started_at.desc())
                .first()
            )

            if not latest_run:
                print(f"  [Skipped] No complete analysis run exists for {repo_key}.")
                continue

            scores = (
                db.query(ContributionScore)
                .filter(ContributionScore.run_id == latest_run.id)
                .all()
            )

            members = db.query(Member).filter(Member.project_id == project.id).all()
            member_id_to_login = {m.id: (m.github_login or "").lower() for m in members}

            app_scores_map: Dict[str, float] = {}
            for s in scores:
                login = member_id_to_login.get(s.member_id, "")
                if login:
                    app_scores_map[login] = float(s.share_percent)

            # Compute raw commit count percentages
            contribs = db.query(Contribution).filter(Contribution.project_id == project.id).all()
            total_raw_commits = sum(c.commit_count for c in contribs)
            raw_commit_map: Dict[str, float] = {}
            for c in contribs:
                c_login = c.github_login.lower()
                c_share = (c.commit_count / total_raw_commits * 100.0) if total_raw_commits > 0 else 0.0
                raw_commit_map[c_login] = round(c_share, 2)

            all_logins = sorted(set(expected_map.keys()) | set(app_scores_map.keys()))

            header = f"{'Login':<20} | {'Expected %':<11} | {'App %':<9} | {'Err (App)':<10} | {'Commit %':<10} | {'Err (Commit)':<12}"
            print(header)
            print("-" * len(header))

            exp_vals: List[float] = []
            app_vals: List[float] = []
            commit_vals: List[float] = []

            abs_errors_app: List[float] = []
            abs_errors_commit: List[float] = []

            for login in all_logins:
                exp_val = float(expected_map.get(login, 0.0))
                app_val = float(app_scores_map.get(login.lower(), 0.0))
                com_val = float(raw_commit_map.get(login.lower(), 0.0))

                err_app = abs(app_val - exp_val)
                err_com = abs(com_val - exp_val)

                exp_vals.append(exp_val)
                app_vals.append(app_val)
                commit_vals.append(com_val)

                abs_errors_app.append(err_app)
                abs_errors_commit.append(err_com)

                print(
                    f"{login:<20} | {exp_val:>10.2f}% | {app_val:>8.2f}% | {err_app:>9.2f}% | {com_val:>9.2f}% | {err_com:>11.2f}%"
                )

            # Metrics
            mae_app = sum(abs_errors_app) / len(abs_errors_app) if abs_errors_app else 0.0
            max_err_app = max(abs_errors_app) if abs_errors_app else 0.0
            rank_app = spearman_rank_correlation(exp_vals, app_vals)

            mae_com = sum(abs_errors_commit) / len(abs_errors_commit) if abs_errors_commit else 0.0
            max_err_com = max(abs_errors_commit) if abs_errors_commit else 0.0
            rank_com = spearman_rank_correlation(exp_vals, commit_vals)

            print("-" * len(header))
            print(f"Mean Absolute Error (MAE): App = {mae_app:.2f}% vs Raw Commits = {mae_com:.2f}%")
            print(f"Maximum Error:            App = {max_err_app:.2f}% vs Raw Commits = {max_err_com:.2f}%")
            print(f"Spearman Rank Agreement:  App = {rank_app:.3f} vs Raw Commits = {rank_com:.3f}")

            if mae_app < mae_com:
                improvement = mae_com - mae_app
                print(f"-> Provenance scoring improved contribution accuracy by {improvement:.2f}% MAE over raw commit counts.")
            print()

    finally:
        db.close()


if __name__ == "__main__":
    gt_file = sys.argv[1] if len(sys.argv) > 1 else None
    run_comparison(gt_file)
