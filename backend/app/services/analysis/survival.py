import os
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from app.services.analysis.line_filter import classify_lines


def get_top_level_module(path: str) -> str:
    """
    Returns the first directory segment of path, or '(root)' if at root level.
    """
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if len(parts) > 1:
        return parts[0]
    return "(root)"


def parse_git_blame_porcelain(blame_output: str) -> List[Tuple[str, str, str]]:
    """
    Parses 'git blame --line-porcelain' output.
    Returns a list of (author_email, author_name, line_content).
    """
    lines_info: List[Tuple[str, str, str]] = []
    current_email = ""
    current_name = ""

    for line in blame_output.splitlines():
        if line.startswith("author "):
            current_name = line[len("author "):].strip()
        elif line.startswith("author-mail "):
            raw_mail = line[len("author-mail "):].strip()
            # strip < and >
            current_email = raw_mail.strip("<>").strip().lower()
        elif line.startswith("\t"):
            # Line content begins with a tab
            content = line[1:]
            lines_info.append((current_email, current_name, content))

    return lines_info


class MemberSurvivalData:
    def __init__(self, member_id: Optional[str] = None):
        self.member_id = member_id
        self.total_lines: int = 0
        self.file_lines: Dict[str, int] = {}
        self.module_lines: Dict[str, int] = {}


class ProjectSurvivalResults:
    def __init__(self):
        self.members: Dict[str, MemberSurvivalData] = {}
        self.total_surviving_lines: int = 0
        self.unlinked_surviving_lines: int = 0
        self.module_totals: Dict[str, int] = {}
        self.file_totals: Dict[str, int] = {}
        self.unlinked_authors: Set[str] = set()

    def get_or_create_member(self, member_id: str) -> MemberSurvivalData:
        if member_id not in self.members:
            self.members[member_id] = MemberSurvivalData(member_id)
        return self.members[member_id]


def process_file_blame(
    file_path: str,
    blame_output: str,
    alias_lookup_fn: Callable[[str, str], Optional[str]],
    results: ProjectSurvivalResults,
) -> int:
    """
    Processes the blame output of a single file:
    - Extracts author email, name, content
    - Filters meaningful lines via classify_lines
    - Maps author to member_id via alias_lookup_fn(email, name)
    - Accumulates lines into results
    Returns the number of surviving meaningful lines in this file.
    """
    parsed = parse_git_blame_porcelain(blame_output)
    if not parsed:
        return 0

    raw_lines = [item[2] for item in parsed]
    meaningful_flags = classify_lines(file_path, raw_lines)

    module = get_top_level_module(file_path)
    file_meaningful_count = 0

    for idx, (email, name, _) in enumerate(parsed):
        if not meaningful_flags[idx]:
            continue

        file_meaningful_count += 1
        results.total_surviving_lines += 1
        results.module_totals[module] = results.module_totals.get(module, 0) + 1
        results.file_totals[file_path] = results.file_totals.get(file_path, 0) + 1

        member_id = alias_lookup_fn(email, name)
        if member_id:
            m_data = results.get_or_create_member(member_id)
            m_data.total_lines += 1
            m_data.file_lines[file_path] = m_data.file_lines.get(file_path, 0) + 1
            m_data.module_lines[module] = m_data.module_lines.get(module, 0) + 1
        else:
            results.unlinked_surviving_lines += 1
            results.unlinked_authors.add(email)

    return file_meaningful_count


def extract_file_blame_result(file_path: str, blame_output: str) -> Dict[str, int]:
    """
    Parses blame output and classifies meaningful lines.
    Returns {author_email: surviving_meaningful_line_count}.
    """
    parsed = parse_git_blame_porcelain(blame_output)
    if not parsed:
        return {}
    raw_lines = [item[2] for item in parsed]
    meaningful_flags = classify_lines(file_path, raw_lines)
    email_counts: Dict[str, int] = {}
    for idx, (email, _, _) in enumerate(parsed):
        if meaningful_flags[idx]:
            e = email.lower()
            email_counts[e] = email_counts.get(e, 0) + 1
    return email_counts


def apply_blame_result_to_survival(
    file_path: str,
    author_counts: Dict[str, int],
    alias_lookup_fn: Callable[[str, str], Optional[str]],
    results: ProjectSurvivalResults,
) -> int:
    """
    Applies per-author meaningful line counts to ProjectSurvivalResults.
    """
    module = get_top_level_module(file_path)
    file_meaningful = 0
    for email, count in author_counts.items():
        if count <= 0:
            continue
        file_meaningful += count
        results.total_surviving_lines += count
        results.module_totals[module] = results.module_totals.get(module, 0) + count
        results.file_totals[file_path] = results.file_totals.get(file_path, 0) + count

        member_id = alias_lookup_fn(email, "")
        if member_id:
            m_data = results.get_or_create_member(member_id)
            m_data.total_lines += count
            m_data.file_lines[file_path] = m_data.file_lines.get(file_path, 0) + count
            m_data.module_lines[module] = m_data.module_lines.get(module, 0) + count
        else:
            results.unlinked_surviving_lines += count
            results.unlinked_authors.add(email)
    return file_meaningful

