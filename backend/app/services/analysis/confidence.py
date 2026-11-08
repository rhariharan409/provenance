from typing import Dict, List, Set


def evaluate_member_confidence(
    counted_commits: int,
    active_days: int,
    surviving_lines: int,
    collaboration_raw: float,
    has_unlinked_identities: bool,
    project_is_truncated: bool,
    total_project_counted_commits: int,
) -> str:
    """
    Evaluates confidence level for a member:
    - High: >= 15 commits AND >= 5 active days AND (>= 100 surviving lines OR collaboration > 0)
    - Medium: >= 5 commits OR >= 40 surviving lines
    - Low: otherwise
    - Cap at Medium if unlinked identities exist or project is truncated
    - Cap at Low if total project counted commits < 5
    """
    if total_project_counted_commits < 5:
        return "low"

    has_collab = collaboration_raw > 0
    if counted_commits >= 15 and active_days >= 5 and (surviving_lines >= 100 or has_collab):
        level = "high"
    elif counted_commits >= 5 or surviving_lines >= 40:
        level = "medium"
    else:
        level = "low"

    # Caps
    if level == "high" and (has_unlinked_identities or project_is_truncated):
        level = "medium"

    return level

