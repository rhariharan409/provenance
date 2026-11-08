from datetime import datetime, timezone
from decimal import Decimal
import hmac
import hashlib
import json
import secrets
from typing import Any, Dict, List, Optional, Set
import uuid

from app.config import settings
from app.services.analysis.flags import get_flag_message


SEAL_PREFIX = b"provenance-seal-v1\n"


def generate_passport_code() -> str:
    """
    Generates a secure, non-sequential URL-safe code for passports.
    secrets.token_urlsafe(24) produces a 32-character string.
    """
    return secrets.token_urlsafe(24)


def canonical_json(data: Any) -> bytes:
    """
    Produces deterministic UTF-8 bytes for JSON data:
    - Keys sorted recursively
    - Compact separators (no trailing spaces)
    - UTF-8 encoded without escaping unicode
    """
    def _default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    canonical_str = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    )
    return canonical_str.encode("utf-8")


def compute_seal(snapshot: Dict[str, Any], secret: str) -> str:
    """
    Computes HMAC-SHA256 hex digest over b"provenance-seal-v1\n" + canonical_json(snapshot).
    """
    if not secret:
        raise ValueError("Passport signing secret is not configured.")

    canonical_bytes = canonical_json(snapshot)
    message = SEAL_PREFIX + canonical_bytes
    h = hmac.new(secret.encode("utf-8"), message, hashlib.sha256)
    return h.hexdigest()


def verify_seal(snapshot: Dict[str, Any], seal: str, secret: Optional[str]) -> bool:
    """
    Recomputes the HMAC-SHA256 seal from snapshot and compares with stored seal
    using constant-time hmac.compare_digest.
    """
    if not secret or not seal:
        return False
    try:
        expected_seal = compute_seal(snapshot, secret)
        return hmac.compare_digest(expected_seal, seal)
    except Exception:
        return False


def build_snapshot(
    repo_full_name: str,
    repo_url: str,
    head_sha: str,
    finished_at: Optional[datetime],
    member_login: Optional[str],
    member_display_name: Optional[str],
    share_percent: float | Decimal,
    confidence: str,
    flags: List[str],
    signals: Dict[str, Any],
    stats: Dict[str, Any],
    top_commits: List[Dict[str, Any]],
    top_files: List[Dict[str, Any]],
    owned_modules: List[Dict[str, Any]],
    other_members_scores: List[Dict[str, Any]],
    members_with_active_passports: Optional[Set[str]] = None,
    scoring_version: str = "1.0",
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Builds the immutable frozen snapshot for a contribution passport.
    Public-safe: never includes emails, internal user IDs, or other members' internal IDs.
    Teammates without active passports are anonymized as Teammate A, Teammate B, etc.
    """
    active_passport_logins = {l.lower() for l in (members_with_active_passports or set())}

    # Format project
    project_dict = {
        "repo_full_name": repo_full_name,
        "github_url": f"https://github.com/{repo_full_name}",
        "head_sha": head_sha,
        "finished_at": finished_at.isoformat() if finished_at else None,
    }

    # Format member
    member_dict = {
        "login": member_login or "",
        "display_name": member_display_name or member_login or "",
    }

    # Format flags with plain messages
    formatted_flags = [
        {"code": f, "message": get_flag_message(f)}
        for f in flags
    ]

    # Format score
    score_dict = {
        "share_percent": round(float(share_percent), 2),
        "confidence": confidence,
        "flags": formatted_flags,
    }

    # Format evidence with commit URLs
    formatted_commits: List[Dict[str, Any]] = []
    for c in (top_commits or [])[:5]:
        sha = c.get("sha", "")
        formatted_commits.append({
            "sha": sha,
            "sha_short": sha[:7] if len(sha) >= 7 else sha,
            "subject": c.get("subject", ""),
            "effective_lines": round(float(c.get("effective_lines", 0)), 2),
            "github_url": f"https://github.com/{repo_full_name}/commit/{sha}" if sha else "",
        })

    evidence_dict = {
        "top_commits": formatted_commits,
        "top_files": (top_files or [])[:5],
        "owned_modules": owned_modules or [],
    }

    # Format team context (Teammate A, B... anonymized unless they hold an active passport)
    team_list: List[Dict[str, Any]] = []
    anon_index = 0
    # Sort other members by share_percent descending
    sorted_others = sorted(
        other_members_scores,
        key=lambda x: float(x.get("share_percent", 0)),
        reverse=True,
    )
    for other in sorted_others:
        other_login = (other.get("github_login") or "").strip()
        other_name = other.get("display_name")
        other_share = round(float(other.get("share_percent", 0)), 2)

        if other_login and other_login.lower() in active_passport_logins:
            team_list.append({
                "label": other_name or other_login,
                "login": other_login,
                "share_percent": other_share,
                "has_passport": True,
            })
        else:
            anon_label = f"Teammate {chr(65 + (anon_index % 26))}"
            if anon_index >= 26:
                anon_label += f"_{anon_index // 26}"
            anon_index += 1
            team_list.append({
                "label": anon_label,
                "login": None,
                "share_percent": other_share,
                "has_passport": False,
            })

    notes_dict = {
        "scoring_version": scoring_version,
        "weights": weights or {},
        "disclaimer": (
            "This record is an evidence-backed analysis of repository history, "
            "not a measure of total effort. Work outside the repository is not captured."
        ),
    }

    snapshot = {
        "project": project_dict,
        "member": member_dict,
        "score": score_dict,
        "signals": signals or {},
        "stats": stats or {},
        "evidence": evidence_dict,
        "team": team_list,
        "notes": notes_dict,
    }
    return snapshot
