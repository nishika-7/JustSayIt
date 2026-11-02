from root import versions
from root.models import Result
from root.store import add_critique, load_critiques, log_run


def test_run_and_critique_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = Result(claims=[], verdicts=[], undeclared_hunk_ids=[], warnings=[], verifier_version="verifier_v1")
    rid = log_run("I added retry logic.", "diff text", result)
    add_critique(rid, "c1", "added retry", "supported", "unsupported", "verdict", "Wrong because comment only.", "verifier_v1", "splitter_v1")
    (rec,) = load_critiques()
    assert rec["run_id"] == rid and rec["was_right"] is False and rec["correct_label"] == "unsupported"
    assert (tmp_path / "runs" / "log.jsonl").exists()


def test_default_active_versions():
    assert versions.active() == {"splitter": "splitter_v1", "verifier": "verifier_v1"}


def test_spoken_words_counts_distinct_descriptions_and_critiques_but_not_examples(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from root.store import spoken_words
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = Result(claims=[], verdicts=[], undeclared_hunk_ids=[], warnings=[])
    example = json.loads((Path(__file__).resolve().parent.parent / "data" / "examples" / "examples.json").read_text())[0]["narration"]
    log_run("one two three", "d", result)
    log_run("one two three", "d", result)      # re-verifying the same text must not double count
    log_run(example, "d", result)              # built-in example text is not something you entered
    add_critique("r", "c1", "x", "supported", "unsupported", "verdict", "a b c d", "verifier_v1", "splitter_v1")
    assert spoken_words() == 7
    assert spoken_words(until_ts=0) == 0


def test_run_evidence_returns_cited_hunk_or_falls_back_to_diff(tmp_path, monkeypatch):
    from pathlib import Path
    from root.models import Verdict
    from root.store import run_evidence
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    diff = (Path(__file__).parent / "sample.diff").read_text(encoding="utf-8")
    cited = Result(claims=[], verdicts=[Verdict(claim_id="c1", label="supported", evidence_hunk_ids=["h2"], reason="x")],
                   undeclared_hunk_ids=[], warnings=[])
    none = Result(claims=[], verdicts=[Verdict(claim_id="c1", label="unsupported", evidence_hunk_ids=[], reason="x")],
                  undeclared_hunk_ids=[], warnings=[])
    a, b = log_run("n", diff, cited), log_run("n2", diff, none)
    assert "refresh_token" in run_evidence(a, "c1") and "attempt" not in run_evidence(a, "c1")
    assert run_evidence(b, "c1").startswith("diff --git")
    assert run_evidence("nope", "c1") == ""
