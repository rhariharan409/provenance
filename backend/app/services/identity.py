from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.author_aliases import AliasSource, AuthorAlias
from app.models.commits import Commit
from app.models.contributions import Contribution
from app.models.members import Member
from app.models.users import User

NOREPLY_PATTERN = re.compile(
    r"^(?:(\d+)\+)?([a-zA-Z0-9_\-]+)@users\.noreply\.github\.com$",
    re.IGNORECASE
)

KNOWN_BOTS: Set[str] = {
    "dependabot",
    "github-actions",
    "renovate",
    "greenkeeper",
    "snyk-bot",
}


def parse_noreply_email(email: str) -> Optional[str]:
    """
    Extracts the GitHub login from a GitHub noreply email address.
    Matches both:
      - 'ID+login@users.noreply.github.com'
      - 'login@users.noreply.github.com'
    """
    if not email:
        return None
    match = NOREPLY_PATTERN.match(email.strip())
    if match:
        return match.group(2)
    return None


def is_bot_identity(name: str, login: Optional[str] = None) -> bool:
    """
    Detects whether an author name or login represents an automated bot.
    Bots are marked is_bot=True and excluded from project members.
    """
    cleaned_name = (name or "").strip().lower()
    cleaned_login = (login or "").strip().lower() if login else ""

    if cleaned_name.endswith("[bot]") or (cleaned_login and cleaned_login.endswith("[bot]")):
        return True

    if cleaned_name in KNOWN_BOTS or (cleaned_login and cleaned_login in KNOWN_BOTS):
        return True

    return False


@dataclass
class RawCommitData:
    sha: str
    author_name: str
    author_email: str
    authored_at: datetime
    subject: str
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0
    parent_count: int = 0


@dataclass
class ResolvedAlias:
    name: str
    email: str
    commit_count: int
    commit_shas: List[str] = field(default_factory=list)
    login: Optional[str] = None
    source: Optional[AliasSource] = None
    is_bot: bool = False
    existing_manual_member_id: Optional[uuid.UUID] = None


def resolve_identities(
    commits: List[RawCommitData],
    sha_to_login: Dict[str, str],
    existing_manual_assignments: Optional[Dict[Tuple[str, str], Tuple[Optional[str], Optional[uuid.UUID]]]] = None
) -> Dict[Tuple[str, str], ResolvedAlias]:
    """
    Pure identity resolution function:
    1) Groups commits by (lower(email), lower(name)).
    2) Preserves existing manual assignments.
    3) Resolves logins in order:
       a) noreply email -> login (source=noreply)
       b) API match (most common login for its commit shas) -> login (source=api_match)
       c) name match (exact case-insensitive name matching an already-resolved alias) -> login (source=name_match)
    4) Flags bots and excludes them from member creation.
    """
    manual_map = existing_manual_assignments or {}

    # Step 1: Group commits
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for c in commits:
        email_clean = c.author_email.strip()
        name_clean = c.author_name.strip()
        key = (email_clean.lower(), name_clean.lower())

        if key not in grouped:
            grouped[key] = {
                "name": name_clean,
                "email": email_clean,
                "shas": [],
                "count": 0,
            }
        grouped[key]["shas"].append(c.sha)
        grouped[key]["count"] += 1

    resolved: Dict[Tuple[str, str], ResolvedAlias] = {}

    # Step 2: First pass - Manual, Noreply, API match
    for key, data in grouped.items():
        name = data["name"]
        email = data["email"]
        shas = data["shas"]
        count = data["count"]

        # Check existing manual assignment
        if key in manual_map:
            manual_login, manual_member_id = manual_map[key]
            is_bot = is_bot_identity(name, manual_login)
            resolved[key] = ResolvedAlias(
                name=name,
                email=email,
                commit_count=count,
                commit_shas=shas,
                login=manual_login,
                source=AliasSource.manual,
                is_bot=is_bot,
                existing_manual_member_id=manual_member_id
            )
            continue

        # a) Noreply email match
        noreply_login = parse_noreply_email(email)
        if noreply_login:
            is_bot = is_bot_identity(name, noreply_login)
            resolved[key] = ResolvedAlias(
                name=name,
                email=email,
                commit_count=count,
                commit_shas=shas,
                login=noreply_login,
                source=AliasSource.noreply,
                is_bot=is_bot
            )
            continue

        # b) API match: most common login for this alias's commit shas
        matched_logins = [sha_to_login[s] for s in shas if s in sha_to_login and sha_to_login[s]]
        if matched_logins:
            most_common_login = Counter(matched_logins).most_common(1)[0][0]
            is_bot = is_bot_identity(name, most_common_login)
            resolved[key] = ResolvedAlias(
                name=name,
                email=email,
                commit_count=count,
                commit_shas=shas,
                login=most_common_login,
                source=AliasSource.api_match,
                is_bot=is_bot
            )
            continue

        # If still unresolved, initialize as placeholder
        is_bot = is_bot_identity(name, None)
        resolved[key] = ResolvedAlias(
            name=name,
            email=email,
            commit_count=count,
            commit_shas=shas,
            login=None,
            source=None,
            is_bot=is_bot
        )

    # Step 3: Second pass - Name match
    # Build dictionary of lower(name) -> login from resolved non-bot aliases
    name_to_login: Dict[str, str] = {}
    for alias in resolved.values():
        if alias.login and not alias.is_bot:
            name_to_login[alias.name.strip().lower()] = alias.login

    for key, alias in resolved.items():
        if alias.login is None and not alias.is_bot:
            name_clean = alias.name.strip().lower()
            if name_clean in name_to_login:
                alias.login = name_to_login[name_clean]
                alias.source = AliasSource.name_match
                alias.is_bot = is_bot_identity(alias.name, alias.login)

    return resolved


def sync_identities_and_commits_to_db(
    db: Session,
    project_id: uuid.UUID,
    resolved_aliases: Dict[Tuple[str, str], ResolvedAlias],
    commits: List[RawCommitData],
    pr_extra_logins: List[str]
) -> None:
    """
    Synchronizes resolved identities, creates members, attaches aliases,
    stores commits, and updates contributions table in PostgreSQL.
    """
    # 1. Fetch existing members for this project
    existing_members = db.query(Member).filter(Member.project_id == project_id).all()
    member_by_login: Dict[str, Member] = {
        m.github_login.lower(): m for m in existing_members if m.github_login
    }

    # 2. Gather all non-bot logins that should have a Member record
    all_logins: Set[str] = set()
    for alias in resolved_aliases.values():
        if alias.login and not alias.is_bot:
            all_logins.add(alias.login)

    for extra_login in pr_extra_logins:
        if extra_login and not is_bot_identity(extra_login, extra_login):
            all_logins.add(extra_login)

    # 3. Create or find Member for each login
    for login in all_logins:
        login_lower = login.lower()
        if login_lower not in member_by_login:
            # Check if a Provenance user exists with matching username
            matching_user = db.query(User).filter(
                func.lower(User.username) == login_lower
            ).first()

            member = Member(
                project_id=project_id,
                github_login=login,
                display_name=matching_user.display_name if matching_user else None,
                user_id=matching_user.id if matching_user else None
            )
            db.add(member)
            db.flush()
            member_by_login[login_lower] = member
        else:
            # If member exists but user_id is null, attempt to link
            member = member_by_login[login_lower]
            if not member.user_id:
                matching_user = db.query(User).filter(
                    func.lower(User.username) == login_lower
                ).first()
                if matching_user:
                    member.user_id = matching_user.id
                    if not member.display_name:
                        member.display_name = matching_user.display_name
                    db.flush()

    # 4. Upsert AuthorAliases
    alias_db_map: Dict[Tuple[str, str], AuthorAlias] = {}
    existing_aliases = db.query(AuthorAlias).filter(AuthorAlias.project_id == project_id).all()
    existing_alias_map = {
        (a.email.strip().lower(), a.name.strip().lower()): a
        for a in existing_aliases
    }

    for key, resolved_alias in resolved_aliases.items():
        target_member_id = None
        if resolved_alias.login and not resolved_alias.is_bot:
            target_member = member_by_login.get(resolved_alias.login.lower())
            if target_member:
                target_member_id = target_member.id

        if key in existing_alias_map:
            db_alias = existing_alias_map[key]
            db_alias.commit_count = resolved_alias.commit_count
            db_alias.is_bot = resolved_alias.is_bot

            # Preserve manual assignment if it was manually set
            if db_alias.source != AliasSource.manual:
                if resolved_alias.source:
                    db_alias.source = resolved_alias.source
                db_alias.member_id = target_member_id
            alias_db_map[key] = db_alias
        else:
            source = resolved_alias.source or AliasSource.api_match
            db_alias = AuthorAlias(
                project_id=project_id,
                name=resolved_alias.name,
                email=resolved_alias.email,
                member_id=target_member_id,
                source=source,
                is_bot=resolved_alias.is_bot,
                commit_count=resolved_alias.commit_count
            )
            db.add(db_alias)
            db.flush()
            alias_db_map[key] = db_alias

    db.flush()

    # 5. Upsert Commits
    existing_commits = db.query(Commit.sha).filter(Commit.project_id == project_id).all()
    existing_shas = {c[0] for c in existing_commits}

    for c in commits:
        if c.sha in existing_shas:
            continue
        key = (c.author_email.strip().lower(), c.author_name.strip().lower())
        alias = alias_db_map.get(key)

        commit_record = Commit(
            project_id=project_id,
            sha=c.sha,
            author_name=c.author_name,
            author_email=c.author_email,
            authored_at=c.authored_at,
            subject=c.subject,
            additions=c.additions,
            deletions=c.deletions,
            files_changed=c.files_changed,
            parent_count=c.parent_count,
            alias_id=alias.id if alias else None
        )
        db.add(commit_record)

    db.flush()

    # 6. Update contributions table (one row per member with commit count)
    all_current_members = db.query(Member).filter(Member.project_id == project_id).all()
    for member in all_current_members:
        # Sum commit counts of all aliases attached to this member
        member_commit_count = sum(
            a.commit_count for a in member.aliases if not a.is_bot
        )

        # Check existing contribution
        contribution = None
        if member.user_id:
            contribution = db.query(Contribution).filter(
                Contribution.project_id == project_id,
                Contribution.user_id == member.user_id
            ).first()

        if not contribution and member.github_login:
            contribution = db.query(Contribution).filter(
                Contribution.project_id == project_id,
                Contribution.github_login == member.github_login
            ).first()

        if contribution:
            contribution.commit_count = member_commit_count
            if member.user_id:
                contribution.user_id = member.user_id
        else:
            contribution = Contribution(
                project_id=project_id,
                user_id=member.user_id,
                github_login=member.github_login or "unknown",
                commit_count=member_commit_count
            )
            db.add(contribution)

    db.commit()

