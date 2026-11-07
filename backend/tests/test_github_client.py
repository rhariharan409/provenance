import json
import httpx
import pytest
from app.config import settings
from app.services.github_client import GitHubClient, RepoAccessError


def test_github_client_pagination():
    def mock_handler(request: httpx.Request):
        url = str(request.url)
        if "/commits" in url:
            if "page=1" in url:
                return httpx.Response(
                    200,
                    json=[
                        {"sha": "sha1", "author": {"login": "user1"}},
                        {"sha": "sha2", "author": {"login": "user2"}},
                    ],
                )
            elif "page=2" in url:
                return httpx.Response(
                    200,
                    json=[
                        {"sha": "sha3", "author": {"login": "user3"}},
                    ],
                )
            else:
                return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = GitHubClient(transport=httpx.MockTransport(mock_handler))
    commits_map, warnings = client.list_commits("owner", "repo", token="mock", max_commits=10, per_page=2)

    assert len(commits_map) == 3
    assert commits_map["sha1"] == "user1"
    assert commits_map["sha2"] == "user2"
    assert commits_map["sha3"] == "user3"


def test_github_client_rate_limit_warning_path():
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0"},
            json={"message": "API rate limit exceeded for user."},
        )

    client = GitHubClient(transport=httpx.MockTransport(mock_handler))
    commits_map, warnings = client.list_commits("owner", "repo", token=None, max_commits=50)

    # Must stop gracefully and return warnings rather than failing or raising
    assert commits_map == {}
    assert any("rate limit" in w.lower() for w in warnings)


def test_github_client_app_not_installed_404():
    settings.GITHUB_APP_SLUG = "provenance-app"

    def mock_handler(request: httpx.Request):
        return httpx.Response(404, json={"message": "Not Found"})

    client = GitHubClient(transport=httpx.MockTransport(mock_handler))

    with pytest.raises(RepoAccessError) as exc_info:
        client.verify_and_get_metadata("owner", "repo", "testuser", token=None)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "app_not_installed"
    assert exc_info.value.install_url == "https://github.com/apps/provenance-app/installations/new"


def test_github_client_private_repo_access_denied_fail_closed():
    def mock_handler(request: httpx.Request):
        url = str(request.url)
        if url.endswith("/repos/secret-org/secret-repo"):
            return httpx.Response(
                200,
                json={
                    "name": "secret-repo",
                    "private": True,
                    "owner": {"login": "secret-org"},
                },
            )
        if "/collaborators/" in url:
            # User is NOT a collaborator
            return httpx.Response(404, json={"message": "Not a collaborator"})
        return httpx.Response(404)

    client = GitHubClient(transport=httpx.MockTransport(mock_handler))

    with pytest.raises(RepoAccessError) as exc_info:
        client.verify_and_get_metadata("secret-org", "secret-repo", "outsider_user", token="tok")

    assert exc_info.value.status_code == 403
    assert "access denied" in exc_info.value.message.lower()


def test_github_client_private_repo_access_allowed_for_collaborator():
    def mock_handler(request: httpx.Request):
        url = str(request.url)
        if url.endswith("/repos/secret-org/secret-repo"):
            return httpx.Response(
                200,
                json={
                    "name": "secret-repo",
                    "private": True,
                    "default_branch": "main",
                    "owner": {"login": "secret-org"},
                },
            )
        if "/collaborators/insider_user" in url:
            # GitHub returns 204 No Content for valid collaborator
            return httpx.Response(204)
        return httpx.Response(404)

    client = GitHubClient(transport=httpx.MockTransport(mock_handler))
    meta, warnings = client.verify_and_get_metadata("secret-org", "secret-repo", "insider_user", token="tok")

    assert meta["name"] == "secret-repo"
    assert meta["private"] is True
