import pytest
from app.services.collector import validate_and_parse_github_url


def test_url_validation_accepts_valid_forms():
    valid_urls = [
        "https://github.com/torvalds/linux",
        "https://github.com/torvalds/linux.git",
        "https://github.com/torvalds/linux/",
        "https://github.com/torvalds/linux.git/",
        "https://github.com/user.name/repo-name",
        "https://github.com/user_123/repo_456.git",
        "https://github.com/facebook/react.git",
    ]
    for url in valid_urls:
        owner, repo, canonical = validate_and_parse_github_url(url)
        assert owner
        assert repo
        assert canonical.startswith("https://github.com/")
        assert canonical.endswith(".git")


def test_url_validation_rejects_other_hosts():
    invalid_hosts = [
        "https://gitlab.com/owner/repo",
        "https://bitbucket.org/owner/repo",
        "https://evilgithub.com/owner/repo",
        "https://github.com.attacker.com/owner/repo",
        "http://github.com/owner/repo",
    ]
    for url in invalid_hosts:
        with pytest.raises(ValueError):
            validate_and_parse_github_url(url)


def test_url_validation_rejects_ssh_and_file_urls():
    invalid_protocols = [
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "file:///tmp/repo",
        "file://c:/repos/repo",
    ]
    for url in invalid_protocols:
        with pytest.raises(ValueError):
            validate_and_parse_github_url(url)


def test_url_validation_rejects_hyphen_prefixes():
    hyphen_urls = [
        "https://github.com/-owner/repo",
        "https://github.com/owner/-repo",
        "https://github.com/-owner/-repo",
    ]
    for url in hyphen_urls:
        with pytest.raises(ValueError):
            validate_and_parse_github_url(url)


def test_url_validation_rejects_extra_path_segments_and_query_strings():
    invalid_paths = [
        "https://github.com/owner/repo/pulls/1",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner/repo?ref=main",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner/repo.git?token=secret",
    ]
    for url in invalid_paths:
        with pytest.raises(ValueError):
            validate_and_parse_github_url(url)


def test_url_validation_rejects_empty_and_non_strings():
    with pytest.raises(ValueError):
        validate_and_parse_github_url("")
    with pytest.raises(ValueError):
        validate_and_parse_github_url(None)  # type: ignore
