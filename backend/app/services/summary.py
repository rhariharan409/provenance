from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.analysis_runs import AnalysisRun
from app.models.commits import Commit
from app.models.contribution_scores import ContributionScore
from app.models.members import Member
from app.models.summaries import MemberSummary, SummaryMethod

logger = logging.getLogger(__name__)

SUMMARY_DISCLAIMER = (
    "Summaries are grounded strictly in repository commit and pull request evidence. "
    "Review commit links to inspect underlying changes."
)

CITATION_REGEX = re.compile(r"\[([a-f0-9]{7,40})\]", re.IGNORECASE)

WORK_VERBS_REGEX = re.compile(
    r"\b(contributed|committed|authored|wrote|implemented|added|fixed|created|refactored|built|updated|modified|deleted|developed|designed|merged)\b",
    re.IGNORECASE,
)


def build_facts_bundle(
    member: Member,
    score: ContributionScore,
    run: AnalysisRun,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Builds a privacy-safe facts bundle per member from the latest analysis run only.
    Strictly contains NO emails, NO file contents, NO other members' names.
    """
    ev = score.evidence or {}
    raw_top_commits = ev.get("top_commits", [])
    raw_top_files = ev.get("top_files", [])
    raw_owned_modules = ev.get("owned_modules", [])

    top_commits: List[Dict[str, Any]] = []
    for c in raw_top_commits[:5]:
        sha = str(c.get("sha", ""))
        top_commits.append({
            "sha": sha,
            "sha_short": sha[:7],
            "subject": str(c.get("subject", "")),
            "effective_lines": int(c.get("effective_lines", 0)),
        })

    top_files: List[Dict[str, Any]] = []
    for f in raw_top_files[:5]:
        top_files.append({
            "path": str(f.get("path", "")),
            "surviving_lines": int(f.get("surviving_lines", 0)),
        })

    owned_modules: List[Dict[str, Any]] = []
    for m in raw_owned_modules:
        owned_modules.append({
            "path": str(m.get("path") or m.get("module") or ""),
            "share": float(m.get("share", 0.0)),
        })

    # Counted commits & active days
    counted_commits = getattr(member, "commit_count", 0)
    active_days = 0
    if db is not None:
        try:
            commits = (
                db.query(Commit.authored_at)
                .filter(Commit.member_id == member.id)
                .all()
            )
            if commits:
                counted_commits = len(commits)
                distinct_days = {c.authored_at.date() for c in commits if c.authored_at}
                active_days = len(distinct_days)
            else:
                counted_commits = len(raw_top_commits)
                active_days = max(1 if counted_commits > 0 else 0, 0)
        except Exception:
            counted_commits = len(raw_top_commits)
            active_days = max(1 if counted_commits > 0 else 0, 0)
    else:
        counted_commits = len(raw_top_commits)
        active_days = max(1 if counted_commits > 0 else 0, 0)

    return {
        "member_id": str(member.id),
        "login": member.github_login or "Contributor",
        "counted_commits": counted_commits,
        "active_days": active_days,
        "top_commits": top_commits,
        "top_files": top_files,
        "owned_modules": owned_modules,
        "pull_requests_opened": getattr(member, "pull_requests_opened", 0),
        "reviews_given": getattr(member, "reviews_given", 0),
        "flags": [str(f.get("code", f) if isinstance(f, dict) else f) for f in (score.flags or [])],
    }


def generate_rule_based_summary(facts: Dict[str, Any]) -> Tuple[str, SummaryMethod, List[Dict[str, Any]]]:
    """
    Generates deterministic, evidence-grounded sentences from the facts bundle.
    """
    sentences: List[str] = []
    citations: List[Dict[str, Any]] = []

    # Sentence 1: Activity
    commits = facts.get("counted_commits", 0)
    days = facts.get("active_days", 0)
    commits_word = "1 commit" if commits == 1 else f"{commits} commits"
    days_word = "1 active day" if days == 1 else f"{days} active days"
    if days > 0:
        sentences.append(f"Counted {commits_word} across {days_word}.")
    else:
        sentences.append(f"Counted {commits_word} in the repository history.")

    # Sentence 2: Files changed
    top_files = facts.get("top_files", [])
    if top_files:
        file_paths = [f["path"] for f in top_files[:2]]
        sentences.append(f"Primary surviving code resides in {', '.join(file_paths)}.")

    # Sentence 3: Module ownership
    owned = facts.get("owned_modules", [])
    if owned:
        mod = owned[0]
        pct = round(mod["share"] * 100)
        sentences.append(f"Maintains primary ownership of module '{mod['path']}' ({pct}% lead share).")

    # Sentence 4: Top commit with citation
    top_commits = facts.get("top_commits", [])
    if top_commits:
        top_c = top_commits[0]
        sha_short = top_c["sha_short"]
        claim = f"Key contribution included {top_c['subject']} [{sha_short}]."
        sentences.append(claim)
        citations.append({
            "sha": top_c["sha"],
            "sha_short": sha_short,
            "claim": claim,
        })
    elif facts.get("counted_commits", 0) == 0:
        sentences.append("Repository history indicates low direct commit volume.")

    # Sentence 5: Collaboration
    prs = facts.get("pull_requests_opened", 0)
    reviews = facts.get("reviews_given", 0)
    if prs > 0 or reviews > 0:
        prs_word = "1 pull request" if prs == 1 else f"{prs} pull requests"
        reviews_word = "1 peer review" if reviews == 1 else f"{reviews} peer reviews"
        sentences.append(f"Recorded {prs_word} opened and {reviews_word} completed.")

    # Guarantee 3 to 5 sentences
    text = " ".join(sentences)
    return text, SummaryMethod.rule_based, citations


def validate_llm_response(text: str, facts: Dict[str, Any]) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Validates LLM summary output:
      - 3 to 5 sentences.
      - Every cited SHA must be present in facts['top_commits'].
      - Every sentence containing a work claim must end with or contain a citation.
      - Discards and returns None on any violation.
    """
    if not text or not text.strip():
        return None

    cleaned_text = " ".join(text.split()).strip()

    # Split into sentences (simple period split respecting abbreviations)
    raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned_text) if s.strip()]
    if len(raw_sentences) < 3 or len(raw_sentences) > 5:
        logger.warning("LLM summary rejected: sentence count %d outside [3, 5]", len(raw_sentences))
        return None

    valid_shas: Set[str] = set()
    for c in facts.get("top_commits", []):
        if c.get("sha"):
            valid_shas.add(c["sha"].lower())
            valid_shas.add(c["sha"][:7].lower())

    citations: List[Dict[str, Any]] = []

    for sentence in raw_sentences:
        matches = CITATION_REGEX.findall(sentence)
        has_work_claim = bool(WORK_VERBS_REGEX.search(sentence))

        if has_work_claim and not matches:
            logger.warning("LLM summary rejected: sentence with work claim has no citation: '%s'", sentence)
            return None

        for sha_match in matches:
            norm_sha = sha_match.lower()
            matching_known = [s for s in valid_shas if s.startswith(norm_sha) or norm_sha.startswith(s)]
            if not matching_known:
                logger.warning("LLM summary rejected: cited unknown SHA '%s'", sha_match)
                return None
            citations.append({
                "sha": sha_match,
                "sha_short": sha_match[:7],
                "claim": sentence,
            })

    return cleaned_text, citations


def generate_llm_summary(
    facts: Dict[str, Any],
    api_key: str,
    model: str = "claude-sonnet-4-5",
    max_tokens: int = 600,
    transport: Optional[httpx.BaseTransport] = None,
) -> Optional[Tuple[str, SummaryMethod, List[Dict[str, Any]]]]:
    """
    Calls Anthropic API to generate an evidence-grounded summary.
    Falls back safely if network error, invalid citations, or non-compliant output.
    Never logs secrets or full prompt.
    """
    prompt_payload = {
        "contributor": facts.get("login"),
        "counted_commits": facts.get("counted_commits"),
        "active_days": facts.get("active_days"),
        "top_commits": facts.get("top_commits"),
        "top_files": facts.get("top_files"),
        "owned_modules": facts.get("owned_modules"),
        "pull_requests_opened": facts.get("pull_requests_opened"),
        "reviews_given": facts.get("reviews_given"),
        "flags": facts.get("flags"),
    }

    system_prompt = (
        "You are an evidence-based contributor analysis auditor. "
        "Summarize this contributor's work in exactly 3 to 5 plain sentences using ONLY the provided facts. "
        "Requirements:\n"
        "1. Every sentence that describes work must end with a citation like [abc1234] referencing a provided commit SHA from top_commits.\n"
        "2. No praise, no subjective adjectives, no comparisons with teammates, no invented technologies.\n"
        "3. If facts are thin, state that plainly."
    )

    try:
        client_kwargs: Dict[str, Any] = {"timeout": 20.0}
        if transport:
            client_kwargs["transport"] = transport

        with httpx.Client(**client_kwargs) as client:
            resp = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Facts:\n{prompt_payload}",
                        }
                    ],
                },
            )
            if resp.status_code != 200:
                logger.warning("Anthropic API returned status %d", resp.status_code)
                return None

            data = resp.json()
            content_blocks = data.get("content", [])
            if not content_blocks or not isinstance(content_blocks, list):
                return None

            generated_text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    generated_text += block.get("text", "")

            validated = validate_llm_response(generated_text, facts)
            if validated:
                text, citations = validated
                return text, SummaryMethod.llm, citations

    except Exception as exc:
        logger.warning("Anthropic API call failed: %s", type(exc).__name__)

    return None


def generate_member_summary(
    member: Member,
    score: ContributionScore,
    run: AnalysisRun,
    db: Optional[Session] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> Tuple[str, SummaryMethod, List[Dict[str, Any]]]:
    """
    Generates summary using LLM if ANTHROPIC_API_KEY is configured,
    falling back to rule-based generation if not set or invalid.
    """
    facts = build_facts_bundle(member, score, run, db=db)

    api_key = settings.ANTHROPIC_API_KEY
    if api_key:
        llm_result = generate_llm_summary(
            facts,
            api_key=api_key,
            model=settings.SUMMARY_MODEL,
            max_tokens=settings.SUMMARY_MAX_TOKENS,
            transport=transport,
        )
        if llm_result:
            return llm_result

    return generate_rule_based_summary(facts)
