from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

FLAG_MESSAGES: Dict[str, str] = {
    "single_bulk_commit": "A single commit accounts for over 70% of all added lines in the repository.",
    "late_dump": "60% or more of counted commits were submitted in the final 10% of the project timeline or last 3 days.",
    "unlinked_identities": "One or more authors could not be linked to known project members.",
    "low_data": "Fewer than 10 commits analyzed; contribution confidence is limited.",
    "truncated": "Repository commit cap or blame file cap was reached.",
    "no_collaboration_data": "No pull requests or reviews found; collaboration weight redistributed to other signals.",
    "rewritten_history_suspected": "Commit timestamps show non-chronological parent relationships exceeding 30 days.",
    "bot_excluded": "Automated bot accounts were detected and excluded from contribution scores.",
}


def get_flag_message(code: str) -> str:
    return FLAG_MESSAGES.get(code, code)


def check_single_bulk_commit(commit_raw_additions: List[int]) -> bool:
    """
    Returns True if any single commit holds > 70% of total raw additions.
    """
    total = sum(commit_raw_additions)
    if total <= 0:
        return False
    largest = max(commit_raw_additions)
    return (largest / total) > 0.70


def check_late_dump(commit_dates: List[datetime]) -> bool:
    """
    Returns True if 60% or more of counted commits fall in the final 10%
    of the project's time span or the last 3 days.
    """
    if len(commit_dates) < 3:
        return False

    sorted_dates = sorted(commit_dates)
    earliest = sorted_dates[0]
    latest = sorted_dates[-1]

    total_time = latest - earliest
    if total_time.total_seconds() <= 0:
        return False

    final_10_percent_start = earliest + (total_time * 0.90)
    last_3_days_start = latest - timedelta(days=3)

    count_10_percent = sum(1 for d in sorted_dates if d >= final_10_percent_start)
    count_3_days = sum(1 for d in sorted_dates if d >= last_3_days_start)

    n = len(sorted_dates)
    return (count_10_percent / n >= 0.60) or (count_3_days / n >= 0.60)


def check_low_data(commits_counted: int) -> bool:
    """
    Returns True if fewer than 10 commits were counted.
    """
    return commits_counted < 10


def check_rewritten_history(
    commit_and_parent_dates: List[Tuple[datetime, List[datetime]]]
) -> bool:
    """
    Returns True if an author date is earlier than its parent's author date by > 30 days.
    """
    for child_date, parent_dates in commit_and_parent_dates:
        for p_date in parent_dates:
            # If child is earlier than parent by > 30 days
            if (p_date - child_date).total_seconds() > (30 * 86400):
                return True
    return False
