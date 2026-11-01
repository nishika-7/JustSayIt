"""Fetch the diff of a public GitHub commit, pull request or compare range. Only github.com links are accepted."""
import re
import urllib.error
import urllib.request

_REF = r"[\w/~^:-]+(?:\.[\w/~^:-]+)*"   # branch, tag or sha; single dots only (no ".."), so paths cannot escape
COMMIT_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/commit/([0-9a-fA-F]{7,40})/?$")
PULL_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)(?:/(?:files|commits))?/?$")
COMPARE_URL = re.compile(rf"^https://github\.com/([\w.-]+)/([\w.-]+)/compare/({_REF})\.\.\.({_REF})/?$")
MAX_BYTES = 200_000
HELP = ("Use a public GitHub link like https://github.com/owner/repo/commit/abc1234, "
        ".../pull/12 or .../compare/main...feature")


class FetchError(Exception):
    pass


def _clean(owner: str, repo: str) -> None:
    if set(owner) <= {"."} or set(repo) <= {"."}:
        raise FetchError(HELP)


def parse_commit_url(url: str) -> tuple[str, str, str]:
    m = COMMIT_URL.match(url.strip())
    if not m:
        raise FetchError(HELP)
    _clean(m.group(1), m.group(2))
    return m.group(1), m.group(2), m.group(3)


def github_diff_url(url: str) -> tuple[str, str]:
    """Return (kind, .diff URL) for a public commit, pull request or compare link."""
    u = url.strip()
    for kind, rx in (("commit", COMMIT_URL), ("pull", PULL_URL), ("compare", COMPARE_URL)):
        m = rx.match(u)
        if m:
            owner, repo = m.group(1), m.group(2)
            _clean(owner, repo)
            if kind == "commit":
                tail = f"commit/{m.group(3)}"
            elif kind == "pull":
                tail = f"pull/{m.group(3)}"
            else:
                tail = f"compare/{m.group(3)}...{m.group(4)}"
            return kind, f"https://github.com/{owner}/{repo}/{tail}.diff"
    raise FetchError(HELP)


def _download(diff_url: str, timeout: int) -> str:
    req = urllib.request.Request(diff_url, headers={"User-Agent": "say-what-you-changed"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise FetchError(f"GitHub returned {e.code}. Is the repo public and the link correct?")
    except (urllib.error.URLError, TimeoutError):
        raise FetchError("Could not reach GitHub. Try again, or paste the diff instead.")
    if len(data) > MAX_BYTES:
        raise FetchError("That change is too large for the demo. Try a smaller one.")
    return data.decode("utf-8", errors="replace")


def fetch_commit_diff(url: str, timeout: int = 10) -> str:
    owner, repo, sha = parse_commit_url(url)
    return _download(f"https://github.com/{owner}/{repo}/commit/{sha}.diff", timeout)


def fetch_github_diff(url: str, timeout: int = 10) -> str:
    return _download(github_diff_url(url)[1], timeout)
