from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import jwt
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class RepoAccessError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 404,
        code: Optional[str] = None,
        install_url: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.install_url = install_url


@dataclass
class AuthResolution:
    token: Optional[str] = None
    installation_id: Optional[int] = None
    warnings: List[str] = field(default_factory=list)


class GitHubClient:
    def __init__(
        self,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 15.0
    ):
        self.transport = transport
        self.timeout = timeout
        self.base_url = "https://api.github.com"

    def _create_client(self, token: Optional[str] = None) -> httpx.Client:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Provenance-Repo-Collector",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return httpx.Client(
            transport=self.transport,
            timeout=self.timeout,
            headers=headers
        )

    def _generate_app_jwt(self) -> Optional[str]:
        """
        Generates an RS256 JWT for GitHub App authentication (valid 9 minutes).
        Never logs or exposes the private key.
        """
        if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY_PATH:
            return None

        key_path = Path(settings.GITHUB_APP_PRIVATE_KEY_PATH)
        if not key_path.is_file():
            return None

        try:
            private_key = key_path.read_text(encoding="utf-8")
            now = datetime.now(timezone.utc)
            payload = {
                "iat": int((now - timedelta(seconds=60)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": str(settings.GITHUB_APP_ID),
            }
            return jwt.encode(payload, private_key, algorithm="RS256")
        except Exception:
            return None

    def resolve_auth(self, owner: str, repo: str) -> AuthResolution:
        """
        Resolves authentication for a repository in order:
        1) GitHub App (if configured & installed on the repo) -> installation token
        2) GITHUB_API_TOKEN (if configured)
        3) Unauthenticated (low rate limit, records warning)
        """
        warnings: List[str] = []

        # 1. GitHub App
        app_jwt = self._generate_app_jwt()
        if app_jwt:
            try:
                with httpx.Client(
                    transport=self.transport,
                    timeout=self.timeout,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {app_jwt}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    }
                ) as app_client:
                    inst_resp = app_client.get(f"{self.base_url}/repos/{owner}/{repo}/installation")
                    if inst_resp.status_code == 200:
                        inst_id = inst_resp.json().get("id")
                        if inst_id:
                            token_resp = app_client.post(
                                f"{self.base_url}/app/installations/{inst_id}/access_tokens",
                                json={
                                    "repositories": [repo],
                                    "permissions": {
                                        "contents": "read",
                                        "pull_requests": "read"
                                    }
                                }
                            )
                            if token_resp.status_code == 201:
                                token = token_resp.json().get("token")
                                return AuthResolution(token=token, installation_id=inst_id, warnings=warnings)
            except Exception:
                pass

        # 2. GITHUB_API_TOKEN
        if settings.GITHUB_API_TOKEN:
            return AuthResolution(token=settings.GITHUB_API_TOKEN, warnings=warnings)

        # 3. Unauthenticated
        warnings.append("Unauthenticated GitHub API access: rate limits may be restricted.")
        return AuthResolution(token=None, warnings=warnings)

    def _check_rate_limit(self, resp: httpx.Response, warnings: List[str]) -> bool:
        """
        Returns True if we hit a rate limit (and records a warning).
        Also inspects X-RateLimit-Remaining to warn proactively.
        """
        remaining = resp.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            try:
                if int(remaining) < 5:
                    msg = f"GitHub API rate limit remaining is low ({remaining})."
                    if msg not in warnings:
                        warnings.append(msg)
            except ValueError:
                pass

        if resp.status_code in (403, 429):
            text_lower = resp.text.lower()
            if "rate limit" in text_lower or "secondary rate limit" in text_lower:
                msg = "GitHub API rate limit reached. Partial data collected."
                if msg not in warnings:
                    warnings.append(msg)
                return True
        return False

    def verify_and_get_metadata(
        self,
        owner: str,
        repo: str,
        submitting_username: str,
        token: Optional[str]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Verifies repo reachability and enforces the fail-closed private repo access rule.
        Returns (metadata_dict, warnings).
        Raises RepoAccessError on failure.
        """
        warnings: List[str] = []
        install_url = (
            f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new"
            if settings.GITHUB_APP_SLUG
            else None
        )

        with self._create_client(token) as client:
            resp = client.get(f"{self.base_url}/repos/{owner}/{repo}")

            if self._check_rate_limit(resp, warnings):
                raise RepoAccessError("GitHub API rate limit reached.", status_code=429)

            if resp.status_code in (404, 403):
                code = "app_not_installed" if (install_url and resp.status_code == 404) else "not_found"
                status_code = 409 if (install_url and code == "app_not_installed") else 404
                raise RepoAccessError(
                    message="Repository not found or private.",
                    status_code=status_code,
                    code=code,
                    install_url=install_url
                )

            if resp.status_code != 200:
                raise RepoAccessError(
                    message="Failed to retrieve repository metadata from GitHub.",
                    status_code=resp.status_code
                )

            data = resp.json()
            is_private = bool(data.get("private", False))

            # PRIVATE REPO ACCESS CHECK (fail closed)
            if is_private:
                owner_login = data.get("owner", {}).get("login", "")
                is_owner = (
                    submitting_username.lower() == owner.lower() or
                    submitting_username.lower() == owner_login.lower()
                )

                if not is_owner:
                    # Check collaborator status via GET /repos/{owner}/{repo}/collaborators/{username}
                    collab_resp = client.get(
                        f"{self.base_url}/repos/{owner}/{repo}/collaborators/{submitting_username}"
                    )
                    self._check_rate_limit(collab_resp, warnings)

                    if collab_resp.status_code != 204:
                        raise RepoAccessError(
                            message="Access denied: You do not have collaborator access to this private repository.",
                            status_code=403,
                            code="forbidden"
                        )

            return data, warnings

    def get_approximate_commit_count(
        self,
        owner: str,
        repo: str,
        token: Optional[str] = None
    ) -> Optional[int]:
        """
        Requests commits with per_page=1 and reads the Link header's last page number,
        or falls back to null.
        """
        try:
            with self._create_client(token) as client:
                resp = client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/commits",
                    params={"per_page": 1}
                )
                if resp.status_code == 200:
                    link_header = resp.headers.get("Link") or resp.headers.get("link")
                    if link_header:
                        match = re.search(r'[?&]page=(\d+)[^>]*>;\s*rel="last"', link_header)
                        if match:
                            return int(match.group(1))
                    items = resp.json()
                    if isinstance(items, list):
                        return len(items)
        except Exception as e:
            logger.debug("Failed to get commit count via Link header for %s/%s: %s", owner, repo, e)
        return None

    def list_commits(
        self,
        owner: str,
        repo: str,
        token: Optional[str],
        max_commits: int,
        per_page: int = 100
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Lists commits via GitHub API to map sha -> author_login.
        Returns (sha_to_login_dict, warnings).
        """
        sha_to_login: Dict[str, str] = {}
        warnings: List[str] = []
        page = 1

        with self._create_client(token) as client:
            while len(sha_to_login) < max_commits:
                resp = client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/commits",
                    params={"per_page": per_page, "page": page}
                )

                if self._check_rate_limit(resp, warnings):
                    break

                if resp.status_code != 200:
                    break

                items = resp.json()
                if not items or not isinstance(items, list):
                    break

                for item in items:
                    sha = item.get("sha")
                    author_obj = item.get("author")
                    if sha and author_obj and author_obj.get("login"):
                        sha_to_login[sha] = author_obj["login"]

                    if len(sha_to_login) >= max_commits:
                        break

                if len(items) < per_page:
                    break
                page += 1

        return sha_to_login, warnings

    def list_pull_requests_and_reviews_graphql(
        self,
        owner: str,
        repo: str,
        token: str,
        max_prs: int,
    ) -> Optional[Tuple[List[Dict[str, Any]], List[str]]]:
        """
        Attempts to fetch pull requests and their reviews in a single GraphQL query.
        Returns (prs, warnings) on success, or None to fall back to REST.
        """
        if not token:
            return None

        query = """
        query GetPullRequestsAndReviews($owner: String!, $name: String!, $cursor: String, $pageSize: Int!) {
          repository(owner: $owner, name: $name) {
            pullRequests(first: $pageSize, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                number
                title
                author {
                  login
                }
                state
                merged
                createdAt
                mergedAt
                reviews(first: 100) {
                  nodes {
                    author {
                      login
                    }
                    state
                    submittedAt
                  }
                }
              }
            }
          }
        }
        """

        prs: List[Dict[str, Any]] = []
        warnings: List[str] = []
        cursor: Optional[str] = None

        try:
            with self._create_client(token) as client:
                while len(prs) < max_prs:
                    page_size = min(100, max_prs - len(prs))
                    payload = {
                        "query": query,
                        "variables": {
                            "owner": owner,
                            "name": repo,
                            "cursor": cursor,
                            "pageSize": page_size,
                        },
                    }
                    resp = client.post("https://api.github.com/graphql", json=payload)
                    if self._check_rate_limit(resp, warnings):
                        break

                    if resp.status_code != 200:
                        logger.debug("GraphQL query returned status %d: %s", resp.status_code, resp.text[:200])
                        return None

                    data = resp.json()
                    if data.get("errors") or not data.get("data", {}).get("repository"):
                        logger.debug("GraphQL returned errors or empty repository: %s", data.get("errors"))
                        return None

                    repo_data = data["data"]["repository"]
                    pr_conn = repo_data.get("pullRequests") or {}
                    nodes = pr_conn.get("nodes") or []
                    if not nodes:
                        break

                    for node in nodes:
                        pr_num = node.get("number")
                        pr_title = node.get("title", "")
                        author_obj = node.get("author") or {}
                        pr_author = author_obj.get("login")
                        pr_state = (node.get("state") or "CLOSED").lower()
                        is_merged = bool(node.get("merged", False))
                        pr_created_at = node.get("createdAt")
                        pr_merged_at = node.get("mergedAt")

                        reviews_list: List[Dict[str, Any]] = []
                        rev_nodes = (node.get("reviews") or {}).get("nodes") or []
                        for r in rev_nodes:
                            r_author = (r.get("author") or {}).get("login")
                            if r_author:
                                reviews_list.append({
                                    "reviewer_login": r_author,
                                    "state": r.get("state", "COMMENTED"),
                                    "submitted_at": r.get("submittedAt"),
                                })

                        prs.append({
                            "number": pr_num,
                            "title": pr_title,
                            "author_login": pr_author,
                            "state": pr_state,
                            "merged": is_merged,
                            "created_at": pr_created_at,
                            "merged_at": pr_merged_at,
                            "reviews": reviews_list,
                        })

                        if len(prs) >= max_prs:
                            break

                    page_info = pr_conn.get("pageInfo") or {}
                    if not page_info.get("hasNextPage"):
                        break
                    cursor = page_info.get("endCursor")

            return prs, warnings
        except Exception as e:
            logger.debug("GraphQL PR fetch failed, falling back to REST: %s", e)
            return None

    def list_pull_requests_and_reviews(
        self,
        owner: str,
        repo: str,
        token: Optional[str],
        max_prs: int
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Lists pull requests and their reviews.
        Prefers GraphQL query when token is available; falls back to concurrent REST requests.
        Returns (list_of_pr_dicts, warnings).
        """
        if token:
            gql_res = self.list_pull_requests_and_reviews_graphql(owner, repo, token, max_prs)
            if gql_res is not None:
                return gql_res

        prs: List[Dict[str, Any]] = []
        warnings: List[str] = []
        page = 1
        per_page = 100

        with self._create_client(token) as client:
            while len(prs) < max_prs:
                resp = client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls",
                    params={"state": "all", "per_page": per_page, "page": page}
                )

                if self._check_rate_limit(resp, warnings):
                    break

                if resp.status_code != 200:
                    break

                items = resp.json()
                if not items or not isinstance(items, list):
                    break

                batch_prs = []
                for item in items:
                    pr_num = item.get("number")
                    pr_title = item.get("title", "")
                    pr_author = item.get("user", {}).get("login") if item.get("user") else None
                    pr_state = item.get("state", "closed")
                    is_merged = bool(item.get("merged_at") is not None)
                    pr_created_at = item.get("created_at")
                    pr_merged_at = item.get("merged_at")

                    batch_prs.append({
                        "number": pr_num,
                        "title": pr_title,
                        "author_login": pr_author,
                        "state": pr_state,
                        "merged": is_merged,
                        "created_at": pr_created_at,
                        "merged_at": pr_merged_at,
                        "reviews": [],
                    })
                    if len(prs) + len(batch_prs) >= max_prs:
                        break

                # Fetch reviews concurrently for batch_prs using bounded pool
                def fetch_reviews(pr_n: Optional[int]) -> List[Dict[str, Any]]:
                    if not pr_n:
                        return []
                    try:
                        with self._create_client(token) as sub_client:
                            rev_resp = sub_client.get(f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_n}/reviews")
                            self._check_rate_limit(rev_resp, warnings)
                            if rev_resp.status_code == 200:
                                rev_items = rev_resp.json()
                                if isinstance(rev_items, list):
                                    revs = []
                                    for r in rev_items:
                                        rev_user = r.get("user", {}).get("login") if r.get("user") else None
                                        if rev_user:
                                            revs.append({
                                                "reviewer_login": rev_user,
                                                "state": r.get("state", "COMMENTED"),
                                                "submitted_at": r.get("submitted_at")
                                            })
                                    return revs
                    except Exception:
                        pass
                    return []

                workers = min(settings.GITHUB_CONCURRENCY, len(batch_prs)) if batch_prs else 1
                with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                    future_to_idx = {
                        pool.submit(fetch_reviews, p["number"]): idx
                        for idx, p in enumerate(batch_prs)
                    }
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            batch_prs[idx]["reviews"] = future.result()
                        except Exception:
                            batch_prs[idx]["reviews"] = []

                prs.extend(batch_prs)
                if len(items) < per_page or len(prs) >= max_prs:
                    break
                page += 1

        return prs, warnings
