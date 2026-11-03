"""Save commit diffs to data/commits/.
   python -m eval.collect_commits --repo C:\\dev\\proj1 --repo C:\\dev\\proj2 --n 8 [--urls data/commit_urls.txt]"""
import argparse
import subprocess
from pathlib import Path

from root.diff_parser import parse_diff
from root.github import fetch_commit_diff, parse_commit_url
from root.store import data_dir

EXCLUDE = ["*.ipynb", "*.lock", "package-lock.json", "*.min.js", "*.svg", "*.png", "*.jpg", "*.csv", "*.pkl", "*.h5", "*.keras"]


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def usable(diff: str, max_chars=8000, max_hunks=6) -> bool:
    if not diff.strip() or len(diff) > max_chars:
        return False
    try:
        return 1 <= len(parse_diff(diff)) <= max_hunks
    except Exception:
        return False


def collect_repo(repo: str, n: int, out_dir: Path) -> list[Path]:
    name, saved = Path(repo).resolve().name, []
    for sha in _git(repo, "log", "--no-merges", "-n", str(n * 5), "--pretty=%H").split():
        if len(saved) >= n:
            break
        diff = _git(repo, "show", "--format=", "-U3", sha, "--", ".", *[f":(exclude){p}" for p in EXCLUDE])
        if usable(diff):
            path = out_dir / f"{name}_{sha[:7]}.diff"
            path.write_text(diff, encoding="utf-8")
            saved.append(path)
    return saved


def collect_urls(url_file: Path, out_dir: Path) -> list[Path]:
    saved = []
    for line in url_file.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        owner, repo, sha = parse_commit_url(line)
        diff = fetch_commit_diff(line)
        if usable(diff):
            path = out_dir / f"gh-{owner}-{repo}_{sha[:7]}.diff"
            path.write_text(diff, encoding="utf-8")
            saved.append(path)
    return saved


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", default=[])
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--urls", type=Path)
    args = ap.parse_args()
    out = data_dir() / "commits"
    out.mkdir(parents=True, exist_ok=True)
    total = []
    for r in args.repo:
        got = collect_repo(r, args.n, out)
        print(f"{r}: saved {len(got)} usable commits")
        total += got
    if args.urls:
        got = collect_urls(args.urls, out)
        print(f"{args.urls}: saved {len(got)} usable commits")
        total += got
    print(f"Total diffs in {out}: {len(list(out.glob('*.diff')))}")
