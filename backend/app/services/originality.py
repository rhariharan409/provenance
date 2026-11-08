from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
import struct
import subprocess
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.analysis_runs import AnalysisRun
from app.models.originality import Fingerprint, OriginalityMatch
from app.models.projects import Project
from app.services.analysis.file_filter import is_ignored
from app.services.analysis.line_filter import (
    C_LIKE_EXTENSIONS,
    HASH_COMMENT_EXTENSIONS,
    HTML_XML_EXTENSIONS,
    SQL_EXTENSIONS,
    classify_lines,
)

logger = logging.getLogger(__name__)

ORIGINALITY_DISCLAIMER = (
    "Similarity can come from shared templates, tutorials or team collaboration. "
    "It is not a finding of misconduct."
)

ELIGIBLE_EXTENSIONS = (
    C_LIKE_EXTENSIONS
    | HASH_COMMENT_EXTENSIONS
    | SQL_EXTENSIONS
    | {".html", ".htm"}
)

STR_LITERAL_REGEX = re.compile(r'(\"[^\"]*\"|\'[^\']*\')')
NUM_LITERAL_REGEX = re.compile(r'\b(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b')
WHITESPACE_REGEX = re.compile(r'\s+')


def normalize_line(line: str) -> str:
    """
    Normalizes a single code line:
      - replaces string and number literals with placeholders
      - lowercases
      - collapses whitespace
    """
    line = STR_LITERAL_REGEX.sub("__STR__", line)
    line = NUM_LITERAL_REGEX.sub("__NUM__", line)
    line = line.lower()
    line = WHITESPACE_REGEX.sub(" ", line).strip()
    return line


def hash_kgram(kgram_lines: List[str]) -> int:
    """
    Computes a signed 64-bit integer hash for a k-gram of normalized lines.
    Fits in Postgres signed BIGINT (-2^63 to 2^63 - 1).
    """
    blob = "\n".join(kgram_lines).encode("utf-8")
    digest = hashlib.sha256(blob).digest()[:8]
    val = struct.unpack(">q", digest)[0]
    return val


def winnow(
    hashes: List[Tuple[int, int]],
    window_size: int,
) -> List[Tuple[int, int]]:
    """
    Winnowing algorithm: selects minimum hash in each window of size `window_size`.
    `hashes` is a list of (hash_val, line_start).
    Returns unique selected (hash_val, line_start) preserving order.
    """
    if not hashes:
        return []

    if len(hashes) <= window_size:
        min_item = min(hashes, key=lambda x: x[0])
        return [min_item]

    selected: List[Tuple[int, int]] = []
    last_min_idx = -1

    for i in range(len(hashes) - window_size + 1):
        window = hashes[i : i + window_size]
        # Rightmost minimum in window
        min_idx_in_window = 0
        min_val = window[0][0]
        for w_idx in range(1, len(window)):
            if window[w_idx][0] <= min_val:
                min_val = window[w_idx][0]
                min_idx_in_window = w_idx

        global_idx = i + min_idx_in_window
        if global_idx != last_min_idx:
            selected.append(hashes[global_idx])
            last_min_idx = global_idx

    return selected


def fingerprint_file(
    file_path: str,
    content: str,
    k: int = 8,
    w: int = 4,
) -> List[Tuple[int, str, int]]:
    """
    Normalizes lines, generates k-gram hashes, winnows, and returns:
    List of (hash, file_path, line_start).
    """
    raw_lines = content.splitlines()
    if not raw_lines:
        return []

    # Filter out blank and comment-only lines using AST line classifier
    meaningful = classify_lines(file_path, raw_lines)

    norm_lines: List[str] = []
    line_starts: List[int] = []

    for idx, (raw_l, is_m) in enumerate(zip(raw_lines, meaningful)):
        if not is_m:
            continue
        norm = normalize_line(raw_l)
        if norm:
            norm_lines.append(norm)
            line_starts.append(idx + 1)  # 1-indexed

    if len(norm_lines) < k:
        # Fewer lines than k-gram: take single hash if at least 1 meaningful line
        if norm_lines:
            h = hash_kgram(norm_lines)
            return [(h, file_path, line_starts[0])]
        return []

    # Generate k-grams
    kgram_hashes: List[Tuple[int, int]] = []
    for i in range(len(norm_lines) - k + 1):
        k_slice = norm_lines[i : i + k]
        h = hash_kgram(k_slice)
        kgram_hashes.append((h, line_starts[i]))

    # Winnow
    winnowed = winnow(kgram_hashes, w)
    return [(h, file_path, start) for h, start in winnowed]


def read_repo_files_at_head(
    repo_path: Path,
    head_sha: str,
) -> List[Tuple[str, str]]:
    """
    Lists and reads source files from bare clone using git commands without checkout.
    Skips ignored directories, non-source extensions, and files exceeding max size.
    Caps at MAX_BLAME_FILES (default 1500).
    """
    if not repo_path.exists():
        logger.warning("Repo path %s does not exist", repo_path)
        return []

    try:
        # 1. git ls-tree -r --name-only <head_sha>
        cmd = ["git", "ls-tree", "-r", "--name-only", head_sha]
        proc = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=30,
        )
        all_paths = proc.stdout.splitlines()
    except Exception as e:
        logger.error("Failed to list files in %s: %s", repo_path, e)
        return []

    eligible_files: List[Tuple[str, str]] = []
    max_size_bytes = settings.MAX_FILE_SIZE_KB * 1024

    for path in all_paths:
        if len(eligible_files) >= settings.MAX_BLAME_FILES:
            break

        _, ext = Path(path).suffix.lower(), Path(path).suffix.lower()
        if ext not in ELIGIBLE_EXTENSIONS:
            continue

        ignored, _ = is_ignored(path, max_size_kb=settings.MAX_FILE_SIZE_KB)
        if ignored:
            continue

        # Read content via git cat-file -p <head_sha>:<path>
        try:
            read_proc = subprocess.run(
                ["git", "cat-file", "-p", f"{head_sha}:{path}"],
                cwd=str(repo_path),
                capture_output=True,
                check=True,
                timeout=10,
            )
            raw_bytes = read_proc.stdout
            if len(raw_bytes) > max_size_bytes:
                continue
            text = raw_bytes.decode("utf-8", errors="replace")
            eligible_files.append((path, text))
        except Exception:
            continue

    return eligible_files


def run_fingerprinting_for_project(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session,
) -> int:
    """
    Computes fingerprints for the project head commit and stores them in DB.
    Deletes any existing fingerprints for this run first.
    Returns the count of fingerprints stored.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not project or not run or not run.head_sha:
        return 0

    repo_dir = Path(settings.REPO_STORAGE_PATH) / f"{project.id}.git"
    files = read_repo_files_at_head(repo_dir, run.head_sha)

    # Delete existing fingerprints for this run
    db.query(Fingerprint).filter(Fingerprint.run_id == run_id).delete()
    db.commit()

    k = settings.ORIGINALITY_KGRAM
    w = settings.ORIGINALITY_WINDOW

    fingerprints_to_add: List[Fingerprint] = []
    seen_in_project: Set[Tuple[int, str, int]] = set()

    for file_path, content in files:
        fps = fingerprint_file(file_path, content, k=k, w=w)
        for h, path, line_start in fps:
            key = (h, path, line_start)
            if key not in seen_in_project:
                seen_in_project.add(key)
                fingerprints_to_add.append(
                    Fingerprint(
                        project_id=project.id,
                        run_id=run.id,
                        hash=h,
                        file_path=path,
                        line_start=line_start,
                    )
                )

    if fingerprints_to_add:
        db.bulk_save_objects(fingerprints_to_add)
        db.commit()

    return len(fingerprints_to_add)


def compute_originality_matches(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session,
) -> List[OriginalityMatch]:
    """
    Compares project fingerprints against other projects' fingerprints.
    Rules:
      - Only joins across different projects owned by DIFFERENT users.
      - Ignores boilerplate hashes appearing in > 5 distinct projects.
      - Estimates shared lines = shared_fingerprints * k / 2.
      - Stores and returns matches exceeding ORIGINALITY_MIN_SHARED_LINES.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return []

    k = settings.ORIGINALITY_KGRAM
    min_shared = settings.ORIGINALITY_MIN_SHARED_LINES

    # 1. Identify boilerplate hashes appearing in > 5 distinct projects
    boilerplate_rows = (
        db.query(Fingerprint.hash)
        .group_by(Fingerprint.hash)
        .having(func.count(func.distinct(Fingerprint.project_id)) > 5)
        .all()
    )
    boilerplate_hashes = {row[0] for row in boilerplate_rows}

    # 2. Get current project fingerprints for this run (excluding boilerplate)
    curr_fps = (
        db.query(Fingerprint)
        .filter(Fingerprint.run_id == run_id)
        .all()
    )
    curr_fp_map: Dict[int, List[Fingerprint]] = {}
    for fp in curr_fps:
        if fp.hash not in boilerplate_hashes:
            curr_fp_map.setdefault(fp.hash, []).append(fp)

    if not curr_fp_map:
        return []

    candidate_hashes = list(curr_fp_map.keys())

    # 3. Find other projects with different owners that have matching fingerprints
    # Query other fingerprints in chunks if necessary
    other_fps = (
        db.query(Fingerprint, Project.owner_id)
        .join(Project, Fingerprint.project_id == Project.id)
        .filter(
            Fingerprint.project_id != project_id,
            Project.owner_id != project.owner_id,
            Fingerprint.hash.in_(candidate_hashes),
        )
        .all()
    )

    # Group by other_project_id
    matches_by_other: Dict[uuid.UUID, Dict[str, Any]] = {}
    for other_fp, other_owner_id in other_fps:
        other_proj_id = other_fp.project_id
        if other_proj_id not in matches_by_other:
            matches_by_other[other_proj_id] = {
                "shared_hashes": set(),
                "top_files_map": {},
            }

        matches_by_other[other_proj_id]["shared_hashes"].add(other_fp.hash)
        # Record file pair
        for my_fp in curr_fp_map.get(other_fp.hash, []):
            pair_key = (my_fp.file_path, other_fp.file_path)
            matches_by_other[other_proj_id]["top_files_map"][pair_key] = (
                matches_by_other[other_proj_id]["top_files_map"].get(pair_key, 0) + 1
            )

    # 4. Clear old matches for this run
    db.query(OriginalityMatch).filter(OriginalityMatch.run_id == run_id).delete()
    db.commit()

    saved_matches: List[OriginalityMatch] = []

    for other_proj_id, data in matches_by_other.items():
        shared_count = len(data["shared_hashes"])
        shared_lines_est = int(shared_count * k / 2)

        if shared_lines_est < min_shared:
            continue

        # Sort top files by occurrence count
        sorted_pairs = sorted(
            data["top_files_map"].items(),
            key=lambda item: item[1],
            reverse=True,
        )
        top_files = [
            {"path": pair[0], "other_path": pair[1]}
            for pair, count in sorted_pairs[:5]
        ]

        match_obj = OriginalityMatch(
            project_id=project_id,
            other_project_id=other_proj_id,
            run_id=run_id,
            shared_fingerprints=shared_count,
            shared_lines_estimate=shared_lines_est,
            top_files=top_files,
            created_at=datetime.now(timezone.utc),
        )
        db.add(match_obj)
        saved_matches.append(match_obj)

    db.commit()
    return saved_matches
