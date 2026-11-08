from typing import Dict, List, Optional, Tuple


class PRData:
    def __init__(
        self,
        number: int,
        author_login: Optional[str],
        state: str,
        merged: bool,
        reviewers: Optional[List[str]] = None,
    ):
        self.number = number
        self.author_login = author_login.lower() if author_login else None
        self.state = state.lower() if state else "closed"
        self.merged = merged
        self.reviewers = [r.lower() for r in (reviewers or []) if r]


def compute_collaboration_scores(
    member_logins: Dict[str, Optional[str]],  # member_id -> github_login
    prs: List[PRData],
) -> Tuple[Dict[str, float], Dict[str, float], bool]:
    """
    Computes collaboration scores per member:
    - Merged PRs authored: 1.0 each
    - Open/closed unmerged PRs authored: 0.25 each
    - Reviews given on other people's PRs: 0.5 each (max 3 counted per PR per reviewer)
    Returns:
      (raw_scores, normalized_shares, has_collaboration_data)
    """
    login_to_member_id: Dict[str, str] = {}
    for m_id, login in member_logins.items():
        if login:
            login_to_member_id[login.lower()] = m_id

    raw_scores: Dict[str, float] = {m_id: 0.0 for m_id in member_logins.keys()}
    total_reviews_count = 0

    for pr in prs:
        # PR authorship
        if pr.author_login and pr.author_login in login_to_member_id:
            author_mid = login_to_member_id[pr.author_login]
            if pr.merged:
                raw_scores[author_mid] += 1.0
            else:
                raw_scores[author_mid] += 0.25

        # Reviews on other people's PRs
        # Count occurrences per reviewer on this PR
        reviewer_counts: Dict[str, int] = {}
        for rev_login in pr.reviewers:
            total_reviews_count += 1
            if pr.author_login and rev_login == pr.author_login:
                # Do not count self-reviews
                continue
            reviewer_counts[rev_login] = reviewer_counts.get(rev_login, 0) + 1

        for rev_login, count in reviewer_counts.items():
            if rev_login in login_to_member_id:
                rev_mid = login_to_member_id[rev_login]
                counted_reviews = min(count, 3)
                raw_scores[rev_mid] += counted_reviews * 0.5

    has_collaboration_data = (len(prs) > 0 or total_reviews_count > 0)

    total_score = sum(raw_scores.values())
    normalized_shares: Dict[str, float] = {}

    if total_score > 0:
        for m_id, score in raw_scores.items():
            normalized_shares[m_id] = score / total_score
    else:
        # Equal zero share if no collaboration points
        for m_id in member_logins.keys():
            normalized_shares[m_id] = 0.0

    return raw_scores, normalized_shares, has_collaboration_data
