from eval.metrics import judge, summarize
from eval.models import GoldClaim
from eval.mutate import flip_verb, make_cases

CLAIMS = [GoldClaim(text="I added retry logic to login", hunk_ids=["h1"]),
          GoldClaim(text="I removed the None check from refresh_token", hunk_ids=["h2"])]
FOREIGN = [GoldClaim(text="I added a rate limiter", hunk_ids=["h1"])]


def test_flip_verb():
    assert flip_verb("I added retry logic") == "I removed retry logic"
    assert flip_verb("Removed the check") == "Added the check"
    assert flip_verb("I renamed a variable") is None


def test_make_cases_produces_all_kinds_with_gold_labels():
    cases = {c.kind: c for c in make_cases("c1", "dev", CLAIMS, ["h1", "h2"], FOREIGN, seed="c1")}
    assert set(cases) == {"clean", "omission", "false_claim", "contradiction"}
    assert len(cases["omission"].gold_undeclared) == 1
    assert "rate limiter" in cases["false_claim"].narration
    assert "removed retry" in cases["contradiction"].narration or "added the None" in cases["contradiction"].narration


def test_make_cases_is_deterministic():
    a = make_cases("c1", "dev", CLAIMS, ["h1", "h2"], FOREIGN, seed="c1")
    b = make_cases("c1", "dev", CLAIMS, ["h1", "h2"], FOREIGN, seed="c1")
    assert [c.model_dump() for c in a] == [c.model_dump() for c in b]


def test_single_hunk_commit_has_no_omission_case():
    kinds = {c.kind for c in make_cases("c2", "dev", CLAIMS[:1], ["h1"], FOREIGN, seed="c2")}
    assert "omission" not in kinds


def test_judge_each_kind():
    assert judge({"kind": "clean"}, ["supported"], [])["ok"]
    assert not judge({"kind": "clean"}, ["supported"], ["h2"])["ok"]            # false alarm on undeclared
    assert judge({"kind": "omission", "gold_undeclared": ["h2"]}, ["supported"], ["h2"])["ok"]
    assert not judge({"kind": "omission", "gold_undeclared": ["h2"]}, ["unsupported"], ["h2"])["ok"]
    assert judge({"kind": "false_claim"}, ["supported", "unsupported"], [])["ok"]
    assert not judge({"kind": "contradiction"}, ["supported"], [])["ok"]
    assert judge({"kind": "contradiction"}, ["unsupported"], [])["exact_label"] is False


def test_summarize_counts_errors_separately():
    rs = [{"kind": "clean", "split": "dev", "ok": True, "predicted_problem": False},
          {"kind": "false_claim", "split": "holdout", "ok": False, "predicted_problem": False},
          {"id": "x", "kind": "clean", "split": "dev", "error": "boom"}]
    s = summarize(rs)
    assert s["errors"] == 1 and s["overall_accuracy"] == 0.5
    assert s["problem_detection"]["recall"] == 0.0 and s["problem_detection"]["false_alarm_rate"] == 0.0


def test_comment_out_hunk_keeps_diff_valid_and_only_touches_added_lines():
    from pathlib import Path
    from root.diff_parser import parse_diff
    from eval.mutate import comment_out_hunk
    diff = (Path(__file__).parent / "sample.diff").read_text(encoding="utf-8")
    out = comment_out_hunk(diff, 1)
    assert out is not None and "+    # session = None" in out and "+            # time.sleep(2 ** attempt)" in out
    assert "-    session = create_session(user)" in out          # removed lines untouched
    h_old, h_new = parse_diff(diff), parse_diff(out)
    assert [len(h.added) for h in h_old] == [len(h.added) for h in h_new]
    assert h_new[1].text == h_old[1].text                         # other hunk unchanged
    assert comment_out_hunk(diff, 2) is None                      # hunk 2 only removes lines
    assert comment_out_hunk(diff.replace("auth/login.py", "notes.xyz"), 1) is None   # unknown file type


def test_make_comment_trap_and_partial_claim():
    from pathlib import Path
    from eval.mutate import make_comment_trap
    diff = (Path(__file__).parent / "sample.diff").read_text(encoding="utf-8")
    case, variant = make_comment_trap("c1", "dev", CLAIMS, [1], diff, seed="c1")
    assert case.kind == "comment_trap" and case.diff_file.endswith("c1__comment.diff") and variant != diff
    assert make_comment_trap("c1", "dev", CLAIMS, [2], diff, seed="c1") is None
    kinds = {c.kind for c in make_cases("c1", "dev", CLAIMS, ["h1", "h2"], FOREIGN, "c1", files=["auth/login.py"])}
    assert "partial_claim" in kinds
    kinds = {c.kind for c in make_cases("c1", "dev", CLAIMS, ["h1", "h2"], FOREIGN, "c1", files=["auth/login.py", "tests/test_login.py"])}
    assert "partial_claim" not in kinds


def test_judge_new_kinds():
    assert judge({"kind": "comment_trap"}, ["supported", "unsupported"], [])["ok"]
    assert not judge({"kind": "partial_claim"}, ["supported"], [])["ok"]
