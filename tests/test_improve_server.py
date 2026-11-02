import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from root import llm, versions
from root.models import Claim, ClaimList, Verdict, VerifierOutput
from improve import loop
from improve.loop import Mode, Modes
from server.main import create_app

ROOT = Path(__file__).resolve().parent.parent
DIFF = (ROOT / "tests" / "sample.diff").read_text(encoding="utf-8")


def fake(system, user, model_cls, retries=1, model=None):
    if model_cls is ClaimList:
        return ClaimList(claims=[Claim(id="c1", text="added retry logic to login")])
    if model_cls is Modes:
        return Modes(modes=[Mode(name="Fooled by comments", description="Counts comments as code.", stage="verdict",
                                 critique_ids=[0, 7], proposed_rule="Ignore code comments when deciding if behavior was added.")])
    return VerifierOutput(verdicts=[Verdict(claim_id="c1", label="supported", evidence_hunk_ids=["h1"], reason="loop")])


def make_client(monkeypatch, tmp_path, **env):
    monkeypatch.setattr(llm, "ask_json", fake)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    for k in ("TEACH_MODE", "MAX_RUNS_PER_IP", "MAX_DIFF_CHARS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return TestClient(create_app())


def test_page_examples_and_verify(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path)
    assert c.get("/").status_code == 200 and "Say what you changed" in c.get("/").text
    ex = c.get("/api/examples").json()
    r = c.post("/api/verify", json={"narration": ex["examples"][0]["narration"], "diff": ex["diff"]}).json()
    assert r["rows"][0]["label"] == "supported" and r["counts"]["supported"] == 1
    assert [h["id"] for h in r["undeclared"]] == ["h2"] and r["run_id"] == ""
    assert not (tmp_path / "data" / "runs" / "log.jsonl").exists()


def test_bad_input_and_rate_limit(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path, MAX_RUNS_PER_IP="1")
    assert c.post("/api/verify", json={"narration": "", "diff": DIFF}).status_code == 400
    ok = {"narration": "I added retry logic to login.", "diff": DIFF}
    assert c.post("/api/verify", json=ok).status_code == 200
    assert c.post("/api/verify", json=ok).status_code == 429


def test_owner_endpoints_hidden_in_public_mode(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path)
    assert c.get("/api/config").json() == {"teach_mode": False, "max_diff_chars": 30000}
    assert c.get("/api/improve").status_code == 404
    assert c.post("/api/improve/accept", json={"stage": "verdict", "rules": ["x"]}).status_code == 404


def test_owner_loop_end_to_end(monkeypatch, tmp_path):
    prompts = tmp_path / "prompts"
    shutil.copytree(ROOT / "prompts", prompts)
    monkeypatch.setattr(versions, "PROMPT_DIR", prompts)
    c = make_client(monkeypatch, tmp_path, TEACH_MODE="1")
    r = c.post("/api/verify", json={"narration": "I added retry logic to login.", "diff": DIFF}).json()
    assert r["run_id"]
    body = {"run_id": r["run_id"], "claim_id": "c1", "claim": "added retry", "given_label": "supported",
            "correct_label": "unsupported", "stage": "verdict", "critique": "Wrong because only a comment. Should have said unsupported."}
    assert c.post("/api/critique", json=body).status_code == 200
    st = c.get("/api/improve").json()
    assert st["critiques"] == 1 and st["wrong"] == 1 and st["words"] > 5
    modes = c.post("/api/improve/propose").json()["modes"]
    assert modes[0]["critique_ids"] == [0] and modes[0]["count"] == 1   # out-of-range id 7 was dropped
    acc = c.post("/api/improve/accept", json={"stage": "verdict", "rules": [modes[0]["proposed_rule"]]}).json()
    assert acc["new_version"] == "verifier_v2" and acc["active"]["verifier"] == "verifier_v2"
    assert "Ignore code comments" in (prompts / "verifier_v2.md").read_text()
    assert json.loads((prompts / "active.json").read_text())["verifier"] == "verifier_v2"


def test_rules_accumulate_in_one_section(tmp_path):
    shutil.copytree(ROOT / "prompts", tmp_path / "p")
    d = tmp_path / "p"
    assert loop.accept_rules("verdict", ["Rule one."], d) == "verifier_v2"
    assert loop.accept_rules("verdict", ["Rule two."], d) == "verifier_v3"
    text = (d / "verifier_v3.md").read_text()
    assert text.count("## Learned rules") == 1 and "Rule one." in text and "Rule two." in text
    assert loop.accept_rules("claim splitting", ["Split on 'and'."], d) == "splitter_v2"


def test_rounds_endpoint_reads_saved_runs(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path)
    runs = tmp_path / "data" / "runs"
    runs.mkdir(parents=True)
    summary = {"overall_accuracy": 0.6, "per_kind": {"clean": {"n": 5, "accuracy": 0.8}}, "problem_detection": {},
               "by_split": {"dev": 0.6, "holdout": 0.5}, "n": 20}
    (runs / "round0.json").write_text(json.dumps({"label": "round0", "summary": summary, "results": [{"verifier": "verifier_v1"}]}))
    (runs / "log.jsonl").write_text("{}\n")
    out = c.get("/api/rounds").json()
    assert len(out) == 1 and out[0]["label"] == "round0" and out[0]["verifier"] == "verifier_v1"


def test_github_endpoint_accepts_any_supported_link_and_reports_errors(monkeypatch, tmp_path):
    import server.main as sm
    from root.github import FetchError
    c = make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(sm, "fetch_github_diff", lambda url: "DIFF:" + url)
    assert c.post("/api/github", json={"url": "https://github.com/o/r/pull/3"}).json() == {"diff": "DIFF:https://github.com/o/r/pull/3"}

    def boom(url):
        raise FetchError("nope")
    monkeypatch.setattr(sm, "fetch_github_diff", boom)
    r = c.post("/api/github", json={"url": "x"})
    assert r.status_code == 400 and r.json()["detail"] == "nope"


def test_rounds_include_spoken_words(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path)
    runs = tmp_path / "data" / "runs"
    runs.mkdir(parents=True)
    s = {"overall_accuracy": 0.7, "per_kind": {}, "problem_detection": {}, "by_split": {}, "n": 10}
    (runs / "round1.json").write_text(json.dumps({"label": "round1", "spoken_words": 420, "summary": s, "results": []}))
    assert c.get("/api/rounds").json()[0]["spoken_words"] == 420


def test_healthz_and_friendly_busy_message(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path)
    assert c.get("/healthz").json() == {"ok": True}

    class Busy(Exception):
        status_code = 429

    def busy(*a, **k):
        raise Busy()
    monkeypatch.setattr(llm, "ask_json", busy)
    r = c.post("/api/verify", json={"narration": "I added retry logic to login.", "diff": DIFF})
    assert r.status_code == 503 and "busy" in r.json()["detail"]


def test_diff_limit_is_configurable(monkeypatch, tmp_path):
    c = make_client(monkeypatch, tmp_path, MAX_DIFF_CHARS="100")
    assert c.get("/api/config").json()["max_diff_chars"] == 100
    r = c.post("/api/verify", json={"narration": "I added retry logic to login.", "diff": DIFF})
    assert r.status_code == 400 and "too large" in r.json()["detail"]
