import pytest

from root.github import FetchError, parse_commit_url


def test_valid_commit_url():
    assert parse_commit_url("https://github.com/octocat/Hello-World/commit/7fd1a60b01f9") == (
        "octocat", "Hello-World", "7fd1a60b01f9")


@pytest.mark.parametrize("bad", [
    "http://github.com/o/r/commit/abc1234",
    "https://github.com.evil.com/o/r/commit/abc1234",
    "https://evil.com/github.com/o/r/commit/abc1234",
    "https://github.com/o/r/pull/12",
    "https://github.com/o/r/commit/xyz",
    "https://github.com/o/r/commit/abc1234/../../x",
    "not a url",
])
def test_rejects_other_urls(bad):
    with pytest.raises(FetchError):
        parse_commit_url(bad)


@pytest.mark.parametrize("url,kind,diff", [
    ("https://github.com/o/r/commit/abc1234", "commit", "https://github.com/o/r/commit/abc1234.diff"),
    ("https://github.com/o/r/pull/12", "pull", "https://github.com/o/r/pull/12.diff"),
    ("https://github.com/o/r/pull/12/files", "pull", "https://github.com/o/r/pull/12.diff"),
    ("https://github.com/o/r/compare/main...feature/x-1", "compare", "https://github.com/o/r/compare/main...feature/x-1.diff"),
    ("https://github.com/o/r/compare/v1.2...v1.3", "compare", "https://github.com/o/r/compare/v1.2...v1.3.diff"),
])
def test_github_diff_url_accepts_commit_pull_and_compare(url, kind, diff):
    from root.github import github_diff_url
    assert github_diff_url(url) == (kind, diff)


@pytest.mark.parametrize("bad", [
    "https://github.com/o/r/compare/a..b", "https://github.com/o/r/compare/../x...y", "https://github.com/../r/pull/1",
    "https://evil.com/o/r/pull/1", "https://github.com/o/r/pull/abc", "https://github.com.evil.com/o/r/pull/1",
    "https://github.com/o/r/issues/1",
])
def test_github_diff_url_rejects_everything_else(bad):
    from root.github import github_diff_url
    with pytest.raises(FetchError):
        github_diff_url(bad)
