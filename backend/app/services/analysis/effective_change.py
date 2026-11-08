import math
import subprocess
from typing import Dict, List, Optional, Tuple
from app.config import settings
from app.services.analysis.file_filter import is_ignored
from app.services.analysis.line_filter import classify_lines


def calculate_dampened_lines(total: int, cap: int = 1500) -> float:
    """
    If total > cap, effective = cap + sqrt(total - cap)
    """
    if total <= 0:
        return 0.0
    if total <= cap:
        return float(total)
    return float(cap) + math.sqrt(float(total - cap))


def parse_patch_meaningful_lines(patch_output: str) -> int:
    """
    Parses unified diff output (e.g. from git show -w -U0),
    groups added and deleted lines per file, filters out ignored files,
    and uses classify_lines to count only meaningful lines.
    """
    current_file = None
    file_additions: Dict[str, List[str]] = {}
    file_deletions: Dict[str, List[str]] = {}

    lines = patch_output.splitlines()
    for line in lines:
        if line.startswith("diff --git"):
            # Header line: diff --git a/path b/path
            parts = line.split(" ")
            if len(parts) >= 4:
                # Prefer b/ path if present
                b_path = parts[3]
                if b_path.startswith("b/"):
                    current_file = b_path[2:]
                else:
                    current_file = b_path
            else:
                current_file = None
            continue

        if not current_file:
            continue

        if line.startswith("+++ ") or line.startswith("--- "):
            continue

        if line.startswith("+"):
            added_text = line[1:]
            if current_file not in file_additions:
                file_additions[current_file] = []
            file_additions[current_file].append(added_text)
        elif line.startswith("-"):
            deleted_text = line[1:]
            if current_file not in file_deletions:
                file_deletions[current_file] = []
            file_deletions[current_file].append(deleted_text)

    all_files = set(file_additions.keys()) | set(file_deletions.keys())
    total_meaningful = 0

    for file_path in all_files:
        ignored, _ = is_ignored(file_path)
        if ignored:
            continue

        added = file_additions.get(file_path, [])
        if added:
            meaningful_add = classify_lines(file_path, added)
            total_meaningful += sum(1 for m in meaningful_add if m)

        deleted = file_deletions.get(file_path, [])
        if deleted:
            meaningful_del = classify_lines(file_path, deleted)
            total_meaningful += sum(1 for m in meaningful_del if m)

    return total_meaningful


def compute_commit_effective_change(
    commit_sha: str,
    parent_count: int,
    is_bot: bool,
    repo_path: Optional[str] = None,
    bulk_cap: Optional[int] = None,
    numstat_text: Optional[str] = None,
    patch_text: Optional[str] = None,
) -> Tuple[float, int, bool, str]:
    """
    Computes effective change for a commit:
    Returns (effective_lines, raw_lines, is_excluded, note)
    - If parent_count > 1 (merge) or is_bot: returns (0.0, 0, True, reason)
    - Otherwise returns dampened effective lines over non-ignored, meaningful code changes.
    """
    cap = bulk_cap if bulk_cap is not None else settings.BULK_COMMIT_LINE_CAP

    if is_bot:
        return 0.0, 0, True, "bot_excluded"

    if parent_count > 1:
        return 0.0, 0, True, "merge_commit"

    raw_total = 0
    file_count = 0
    note = ""

    # 1. Fetch numstat with -w -M
    if numstat_text is None and repo_path:
        cmd = [
            "git",
            "--git-dir",
            repo_path,
            "show",
            "-w",
            "--numstat",
            "-M",
            "--format=",
            commit_sha,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=30,
        )
        if proc.returncode == 0:
            numstat_text = proc.stdout
        else:
            numstat_text = ""

    # Parse numstat
    non_ignored_files: List[str] = []
    if numstat_text:
        for line in numstat_text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            adds_str, dels_str, path = parts[0], parts[1], parts[2]
            # Handle renames: 'old => new' or '{old => new}/file'
            if " => " in path:
                if "{" in path and "}" in path:
                    # e.g. src/{old => new}/file.py
                    prefix, rest = path.split("{", 1)
                    rename_part, suffix = rest.split("}", 1)
                    _, new_part = rename_part.split(" => ", 1)
                    path = prefix + new_part + suffix
                else:
                    _, path = path.split(" => ", 1)

            path = path.strip()
            ignored, _ = is_ignored(path)
            if ignored:
                continue

            file_count += 1
            non_ignored_files.append(path)

            if adds_str.isdigit() and dels_str.isdigit():
                raw_total += int(adds_str) + int(dels_str)

    meaningful_lines = raw_total

    # 2. For commits with <= 200 non-ignored files, parse actual patch with classify_lines
    if file_count > 0:
        if file_count <= 200:
            if patch_text is None and repo_path:
                patch_cmd = [
                    "git",
                    "--git-dir",
                    repo_path,
                    "show",
                    "-w",
                    "-U0",
                    "--format=",
                    commit_sha,
                ]
                patch_proc = subprocess.run(
                    patch_cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                    timeout=45,
                )
                if patch_proc.returncode == 0:
                    patch_text = patch_proc.stdout

            if patch_text is not None:
                meaningful_lines = parse_patch_meaningful_lines(patch_text)
        else:
            note = f"commit has {file_count} files (>200); patch parsing skipped, numstat used"

    dampened = calculate_dampened_lines(meaningful_lines, cap)
    return dampened, raw_total, False, note
