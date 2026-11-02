"""Collect -> build cases -> run eval, end to end, with a fake LLM and a throwaway git repo."""
import json
import os
import re
import shutil
import subprocess

import pytest

from root import llm
from root.models import ClaimList, Claim, Verdict, VerifierOutput
from eval import build_cases, collect_commits, run_eval
from eval.models import GoldClaim, GoldClaims

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, env=ENV)


def make_repo(tmp_path):
    repo = tmp_path / "demo"
    repo.mkdir()
    git(repo, "init", "-q")
    body = [f"line {i}\n" for i in range(60)]
    (repo / "a.py").write_text("".join(body))
    git(repo, "add", "."); git(repo, "commit", "-qm", "init")
    for n in range(3):  # each commit edits two distant places -> two hunks
        body[2] = f"edit {n} top\n"; body[50] = f"edit {n} bottom\n"
        (repo / "a.py").write_text("".join(body))
        (repo / "nb.ipynb").write_text(f'{{"n": {n}}}')
        git(repo, "add", "."); git(repo, "commit", "-qm", f"change {n}")
    return repo


def fake(system, user, model_cls, retries=1, model=None):
    if model_cls is GoldClaims:
        ids = re.findall(r"^\[(h\d+)\]", user, re.M)
        return GoldClaims(claims=[GoldClaim(text=f"I added code in part {i}.", hunk_ids=[i]) for i in ids])
    if model_cls is ClaimList:
        sents = [s.strip() for s in user.split("NARRATION:\n")[1].split(".") if s.strip()]
        return ClaimList(claims=[Claim(id=f"c{i + 1}", text=s) for i, s in enumerate(sents)])
    ids = re.findall(r"^(c\d+):", user, re.M)
    return VerifierOutput(verdicts=[Verdict(claim_id=i, label="supported", evidence_hunk_ids=["h1"], reason="ok") for i in ids])


def test_collect_skips_notebooks_and_saves_usable_diffs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    out = tmp_path / "data" / "commits"; out.mkdir(parents=True)
    saved = collect_commits.collect_repo(str(make_repo(tmp_path)), 5, out)
    assert len(saved) >= 3
    assert all("nb.ipynb" not in p.read_text() for p in saved)


def test_full_pipeline_with_fake_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(llm, "ask_json", fake)
    out = tmp_path / "data" / "commits"; out.mkdir(parents=True)
    collect_commits.collect_repo(str(make_repo(tmp_path)), 5, out)
    monkeypatch.setattr("sys.argv", ["build_cases", "--delay", "0"])
    build_cases.main()
    cases = run_eval.load_cases()
    assert {c.kind for c in cases} >= {"clean", "omission", "false_claim", "comment_trap", "partial_claim"}
    trap = next(c for c in cases if c.kind == "comment_trap")
    assert (tmp_path / "data" / trap.diff_file).exists()
    assert {c.split for c in cases} <= {"dev", "holdout"}
    monkeypatch.setattr("sys.argv", ["run_eval", "--label", "t0", "--delay", "0"])
    run_eval.main()
    data = json.loads((tmp_path / "data" / "runs" / "t0.json").read_text())
    assert data["summary"]["errors"] == 0 and data["summary"]["n"] == len(cases)
    assert all("diff" not in r for r in data["results"])  # no raw code in saved results
