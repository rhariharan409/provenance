import os
from pathlib import PurePosixPath
from typing import Optional, Tuple
from app.config import settings

IGNORED_DIRECTORIES = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    "out",
    ".next",
    "target",
    "bin",
    "obj",
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    "coverage",
    ".idea",
    ".vscode",
}

LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "cargo.lock",
    "composer.lock",
    "go.sum",
    "gemfile.lock",
}

BINARY_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".mp3", ".mp4",
    ".woff", ".woff2", ".ttf", ".eot",
    ".exe", ".dll", ".so", ".class", ".jar", ".pyc",
}

GENERATED_MARKERS = [
    ".generated.",
    "_pb2.py",
    ".designer.cs",
]


def is_ignored(path: str, size_bytes: Optional[int] = None, max_size_kb: Optional[int] = None) -> Tuple[bool, str]:
    """
    Returns (True, reason) if the file should be excluded from analysis,
    or (False, "") if it should be analyzed.
    """
    if not path:
        return True, "empty_path"

    # Normalize path separators
    normalized_path = path.replace("\\", "/").strip("/")
    parts = normalized_path.split("/")
    filename = parts[-1].lower()

    # 1. Directory check
    for part in parts[:-1]:
        if part.lower() in IGNORED_DIRECTORIES:
            return True, f"ignored_directory: {part}"

    # 2. Lockfile check
    if filename in LOCKFILES or filename.endswith(".lock"):
        return True, f"lockfile: {filename}"

    # 3. Minified check (*.min.js, *.min.css)
    if filename.endswith(".min.js") or filename.endswith(".min.css"):
        return True, f"minified: {filename}"

    # 4. Source map check (*.map)
    if filename.endswith(".map"):
        return True, f"source_map: {filename}"

    # 5. Generated code markers in the path
    lowered_path = normalized_path.lower()
    for marker in GENERATED_MARKERS:
        if marker in lowered_path:
            return True, f"generated_marker: {marker}"

    # 6. Binary, media, archives, fonts extension check
    _, ext = os.path.splitext(filename)
    if ext in BINARY_MEDIA_EXTENSIONS:
        return True, f"binary_or_media: {ext}"

    # 7. File size check
    cap_kb = max_size_kb if max_size_kb is not None else settings.MAX_FILE_SIZE_KB
    if size_bytes is not None and size_bytes > (cap_kb * 1024):
        return True, f"file_size_exceeded: {size_bytes} > {cap_kb * 1024} bytes"

    return False, ""

