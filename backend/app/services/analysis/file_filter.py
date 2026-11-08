import os
from pathlib import PurePosixPath
from typing import Optional, Tuple, Union
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
    ".otf", ".woff", ".woff2", ".ttf", ".eot",
    ".exe", ".dll", ".so", ".class", ".jar", ".pyc",
}

FONT_EXTENSIONS = {
    ".otf",
    ".ttf",
    ".woff",
    ".woff2",
    ".eot",
}

VENDORED_PATH_MARKERS = [
    "/static/vendor/",
    "/static/lib/",
    "/static/libs/",
    "/assets/vendor/",
    "/third_party/",
    "/bower_components/",
    "/wwwroot/lib/",
]

LIB_PARENT_FOLDERS = {
    "static",
    "assets",
    "public",
    "lib",
    "libs",
    "vendor",
    "vendors",
}

LICENSE_BANNER_STRINGS = [
    "bootstrap v",
    "jquery v",
    "font awesome",
    "@license",
]

GENERATED_MARKERS = [
    ".generated.",
    "_pb2.py",
    ".designer.cs",
]


def is_ignored(
    path: str,
    size_bytes: Optional[int] = None,
    max_size_kb: Optional[int] = None,
    content_preview: Optional[Union[str, bytes]] = None,
) -> Tuple[bool, str]:
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
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    # 1. Font files check (otf, ttf, woff, woff2, eot)
    if ext in FONT_EXTENSIONS:
        return True, "font"

    # 2. Vendored path markers check
    p_lower = f"/{normalized_path.lower()}/"
    for marker in VENDORED_PATH_MARKERS:
        if marker in p_lower:
            return True, "vendored_library"

    # 3. Known third-party library filenames under static, assets, public, lib or vendor folders
    # (bootstrap*, jquery*, font-awesome*, fontawesome*, popper*, normalize*, animate*, d3*, chart*.js)
    has_lib_parent = any(part.lower() in LIB_PARENT_FOLDERS for part in parts[:-1])
    is_at_root = len(parts) == 1

    is_third_party_lib = (
        filename.startswith("bootstrap")
        or filename.startswith("jquery")
        or filename.startswith("font-awesome")
        or filename.startswith("fontawesome")
        or filename.startswith("popper")
        or filename.startswith("normalize")
        or filename.startswith("animate")
        or filename.startswith("d3")
        or (filename.startswith("chart") and filename.endswith(".js"))
    )

    if (has_lib_parent or (is_at_root and (
        filename.startswith("bootstrap")
        or filename.startswith("jquery")
        or filename.startswith("font-awesome")
        or filename.startswith("fontawesome")
    ))) and is_third_party_lib:
        return True, "vendored_library"

    # 4. License banner in first 2 KB combined with size over 20 KB
    effective_size = size_bytes
    if effective_size is None and content_preview is not None and len(content_preview) > 20 * 1024:
        effective_size = len(content_preview)

    if effective_size is None:
        try:
            if os.path.isfile(path):
                effective_size = os.path.getsize(path)
        except Exception:
            pass

    if effective_size is not None and effective_size > 20 * 1024:
        sample = content_preview
        if sample is None:
            try:
                if os.path.isfile(path):
                    with open(path, "rb") as f:
                        sample = f.read(2048)
            except Exception:
                pass

        if sample:
            if isinstance(sample, bytes):
                text_sample = sample[:2048].decode("utf-8", errors="replace")
            else:
                text_sample = str(sample)[:2048]

            text_lower = text_sample.lower()
            has_license_banner = (
                any(bs in text_lower for bs in LICENSE_BANNER_STRINGS)
                or ("copyright" in text_lower and "and other contributors" in text_lower)
                or ("copyright (c) ... and other contributors" in text_lower)
            )
            if has_license_banner:
                return True, "license_banner"

    # 5. Directory check
    for part in parts[:-1]:
        if part.lower() in IGNORED_DIRECTORIES:
            return True, f"ignored_directory: {part}"

    # 6. Lockfile check
    if filename in LOCKFILES or filename.endswith(".lock"):
        return True, f"lockfile: {filename}"

    # 7. Minified check (*.min.js, *.min.css)
    if filename.endswith(".min.js") or filename.endswith(".min.css"):
        return True, f"minified: {filename}"

    # 8. Source map check (*.map)
    if filename.endswith(".map"):
        return True, f"source_map: {filename}"

    # 9. Generated code markers in the path
    lowered_path = normalized_path.lower()
    for marker in GENERATED_MARKERS:
        if marker in lowered_path:
            return True, f"generated_marker: {marker}"

    # 10. Binary, media, archives extension check
    if ext in BINARY_MEDIA_EXTENSIONS:
        return True, f"binary_or_media: {ext}"

    # 11. File size check
    cap_kb = max_size_kb if max_size_kb is not None else settings.MAX_FILE_SIZE_KB
    if size_bytes is not None and size_bytes > (cap_kb * 1024):
        return True, f"file_size_exceeded: {size_bytes} > {cap_kb * 1024} bytes"

    return False, ""

