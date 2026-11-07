import urllib.parse
from app.config import OAUTH_STATE_COOKIE_NAME, SESSION_COOKIE_NAME, settings


def test_auth_me_unauthorized_without_cookie(client):
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_github_login_redirect_and_cookie(client):
    response = client.get("/auth/github/login", follow_redirects=False)
    assert response.status_code == 307

    location = response.headers.get("location")
    assert location is not None
    assert "https://github.com/login/oauth/authorize" in location

    parsed = urllib.parse.urlparse(location)
    query_params = urllib.parse.parse_qs(parsed.query)

    assert "client_id" in query_params
    assert query_params["client_id"][0] == settings.GITHUB_CLIENT_ID

    assert "scope" in query_params
    assert query_params["scope"][0] == "read:user user:email"

    assert "state" in query_params
    state_in_url = query_params["state"][0]
    assert len(state_in_url) > 0

    assert OAUTH_STATE_COOKIE_NAME in response.cookies
    state_in_cookie = response.cookies.get(OAUTH_STATE_COOKIE_NAME)
    assert state_in_cookie == state_in_url


def test_auth_logout_clears_session(client):
    response = client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # The set-cookie header should instruct deletion
    set_cookie_header = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie_header
