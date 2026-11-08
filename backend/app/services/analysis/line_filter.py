import os
from typing import List

C_LIKE_EXTENSIONS = {
    ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".cc", ".cxx",
    ".h", ".hpp", ".cs", ".go", ".kt", ".kts", ".swift", ".php",
    ".scss", ".css",
}

HASH_COMMENT_EXTENSIONS = {
    ".py", ".sh", ".bash", ".zsh", ".yml", ".yaml", ".toml", ".rb",
}

HTML_XML_EXTENSIONS = {
    ".html", ".htm", ".xml", ".svg",
}

SQL_EXTENSIONS = {
    ".sql",
}


def classify_lines(path: str, lines: List[str]) -> List[bool]:
    """
    Classifies each line in `lines` as meaningful (True) or not (False).
    A line is NOT meaningful if blank/whitespace-only or a comment-only line.
    Lines mixing code and comments are meaningful.
    """
    if not lines:
        return []

    _, ext = os.path.splitext(path.lower())
    family = "unknown"
    if ext in C_LIKE_EXTENSIONS:
        family = "c_like"
    elif ext in HASH_COMMENT_EXTENSIONS:
        family = "hash"
    elif ext in HTML_XML_EXTENSIONS:
        family = "html"
    elif ext in SQL_EXTENSIONS:
        family = "sql"

    # State machine variables
    in_block_comment = False      # For /* ... */ and <!-- ... -->
    in_docstring = None           # '"""' or "'''" for python docstrings

    result: List[bool] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(False)
            continue

        if family == "unknown":
            result.append(True)
            continue

        has_code = False
        i = 0
        n = len(stripped)

        while i < n:
            # 1. Inside C-style / SQL block comment /* ... */
            if in_block_comment and (family in ("c_like", "sql")):
                close_idx = stripped.find("*/", i)
                if close_idx != -1:
                    in_block_comment = False
                    i = close_idx + 2
                    continue
                else:
                    i = n
                    break

            # 2. Inside HTML comment <!-- ... -->
            if in_block_comment and family == "html":
                close_idx = stripped.find("-->", i)
                if close_idx != -1:
                    in_block_comment = False
                    i = close_idx + 3
                    continue
                else:
                    i = n
                    break

            # 3. Inside Python standalone triple-quoted docstring
            if in_docstring is not None:
                close_idx = stripped.find(in_docstring, i)
                if close_idx != -1:
                    in_docstring = None
                    i = close_idx + 3
                    continue
                else:
                    i = n
                    break

            ch = stripped[i]

            # String literals handling (skip strings so comments inside strings don't trigger)
            if ch in ('"', "'") and family != "html":
                # Check for Python triple-quote docstring initiation at the start of a statement
                if ext == ".py" and i + 2 < n and stripped[i:i+3] in ('"""', "'''"):
                    quote_delim = stripped[i:i+3]
                    # If there's no code before it on this line, treat as docstring
                    if not has_code:
                        close_idx = stripped.find(quote_delim, i + 3)
                        if close_idx != -1:
                            # Closes on the same line
                            i = close_idx + 3
                            continue
                        else:
                            in_docstring = quote_delim
                            i = n
                            break
                    else:
                        # Part of an expression/assignment -> counts as code
                        has_code = True
                        close_idx = stripped.find(quote_delim, i + 3)
                        if close_idx != -1:
                            i = close_idx + 3
                        else:
                            i = n
                        continue

                # Normal single/double quote string
                has_code = True
                quote_char = ch
                i += 1
                while i < n:
                    if stripped[i] == "\\":
                        i += 2  # Skip escaped char
                        continue
                    if stripped[i] == quote_char:
                        i += 1
                        break
                    i += 1
                continue

            # Check single line comments
            if family == "c_like" and stripped[i:i+2] == "//":
                # Rest of line is comment
                break

            if family in ("hash",) and ch == "#":
                # Rest of line is comment
                break

            if family == "sql" and stripped[i:i+2] == "--":
                # Rest of line is comment
                break

            # Check start of block comments
            if (family in ("c_like", "sql")) and stripped[i:i+2] == "/*":
                close_idx = stripped.find("*/", i + 2)
                if close_idx != -1:
                    i = close_idx + 2
                    continue
                else:
                    in_block_comment = True
                    i = n
                    break

            if family == "html" and stripped[i:i+4] == "<!--":
                close_idx = stripped.find("-->", i + 4)
                if close_idx != -1:
                    i = close_idx + 3
                    continue
                else:
                    in_block_comment = True
                    i = n
                    break

            # If it's non-whitespace outside comments/strings, it is code
            if not ch.isspace():
                has_code = True

            i += 1

        result.append(has_code)

    return result

