"""Tests the code around the LLM using a fake LLM. No API key needed."""
from pathlib import Path

from root import llm, verifier
from root.models import Claim, ClaimList, Verdict, VerifierOutput

DIFF = (Path(__file__).parent / "sample.diff").read_text(encoding="utf-8")


def fake_ask_json(system, user, model_cls, retries=1):
    if model_cls is ClaimList:
        return ClaimList(claims=[Claim(id="c1", text="added retry logic to login")])
    return VerifierOutput(
        verdicts=[Verdict(claim_id="c1", label="supported", evidence_hunk_ids=["h1"], reason="loop with retries")]
    )


def test_undeclared_hunks_are_computed_in_code(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", fake_ask_json)
    result = verifier.verify("I added retry logic to login.", DIFF)
    assert result.undeclared_hunk_ids == ["h2"]
    assert result.warnings == []


def test_sanity_checks_flag_bad_llm_output():
    hunks = verifier.parse_diff(DIFF)
    claims = [Claim(id="c1", text="a"), Claim(id="c2", text="b")]
    verdicts = [
        Verdict(claim_id="c1", label="supported", evidence_hunk_ids=[], reason="x"),
        Verdict(claim_id="c9", label="unsupported", evidence_hunk_ids=["h7"], reason="y"),
    ]
    warnings = verifier.check_verdicts(claims, hunks, verdicts)
    assert "no verdict for claim c2" in warnings
    assert "verdict for unknown claim c9" in warnings
    assert "c9 cites unknown hunk h7" in warnings
    assert "c1 is supported but cites no evidence" in warnings
