from pathlib import Path

from . import llm, versions
from .diff_parser import parse_diff
from .models import Claim, ClaimList, Hunk, Result, Verdict, VerifierOutput

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def split_claims(narration: str, prompt: str = "splitter_v1") -> list[Claim]:
    out = llm.ask_json(load_prompt(prompt), f"NARRATION:\n{narration}", ClaimList)
    return out.claims


def format_hunks(hunks: list[Hunk]) -> str:
    return "\n\n".join(f"[{h.id}] {h.file} {h.header}\n{h.text}" for h in hunks)


def verify_claims(claims: list[Claim], hunks: list[Hunk], prompt: str = "verifier_v1") -> list[Verdict]:
    user = (
        "DIFF HUNKS:\n" + format_hunks(hunks)
        + "\n\nCLAIMS:\n" + "\n".join(f"{c.id}: {c.text}" for c in claims)
    )
    return llm.ask_json(load_prompt(prompt), user, VerifierOutput).verdicts


def check_verdicts(claims: list[Claim], hunks: list[Hunk], verdicts: list[Verdict]) -> list[str]:
    """Plain-code sanity checks on what the LLM returned."""
    warnings: list[str] = []
    claim_ids = {c.id for c in claims}
    hunk_ids = {h.id for h in hunks}
    judged = {v.claim_id for v in verdicts}
    for cid in sorted(claim_ids - judged):
        warnings.append(f"no verdict for claim {cid}")
    for v in verdicts:
        if v.claim_id not in claim_ids:
            warnings.append(f"verdict for unknown claim {v.claim_id}")
        for hid in v.evidence_hunk_ids:
            if hid not in hunk_ids:
                warnings.append(f"{v.claim_id} cites unknown hunk {hid}")
        if v.label in ("supported", "contradicted") and not v.evidence_hunk_ids:
            warnings.append(f"{v.claim_id} is {v.label} but cites no evidence")
    return warnings


def find_undeclared(hunks: list[Hunk], verdicts: list[Verdict]) -> list[str]:
    cited = {hid for v in verdicts for hid in v.evidence_hunk_ids}
    return [h.id for h in hunks if h.id not in cited]


def verify(narration: str, diff_text: str, splitter: str | None = None, verifier: str | None = None) -> Result:
    active = versions.active()
    splitter, verifier = splitter or active["splitter"], verifier or active["verifier"]
    hunks = parse_diff(diff_text)
    claims = split_claims(narration, splitter)
    verdicts = verify_claims(claims, hunks, verifier)
    return Result(
        claims=claims,
        verdicts=verdicts,
        undeclared_hunk_ids=find_undeclared(hunks, verdicts),
        warnings=check_verdicts(claims, hunks, verdicts),
        splitter_version=splitter,
        verifier_version=verifier,
    )
