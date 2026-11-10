"""Smoke test with the real LLM. Usage: python try_verify.py [--runs 3]"""
import argparse
import json
from pathlib import Path

from root.verifier import verify

ROOT = Path(__file__).parent
DIFF = (ROOT / "tests" / "sample.diff").read_text(encoding="utf-8")
CASES = json.loads((ROOT / "tests" / "narrations.json").read_text(encoding="utf-8"))


def meets(expect: dict, result) -> bool:
    labels = [v.label for v in result.verdicts]
    ok = True
    if expect.get("all_supported"):
        ok &= bool(labels) and all(l == "supported" for l in labels)
    if expect.get("any_not_supported"):
        ok &= any(l != "supported" for l in labels)
    if expect.get("undeclared_empty"):
        ok &= not result.undeclared_hunk_ids
    for hid in expect.get("undeclared_includes", []):
        ok &= hid in result.undeclared_hunk_ids
    return ok


def show(result) -> None:
    by_id = {v.claim_id: v for v in result.verdicts}
    for c in result.claims:
        v = by_id.get(c.id)
        if v:
            print(f"  {c.id} [{v.label:<12}] {c.text}\n       evidence={v.evidence_hunk_ids} - {v.reason}")
        else:
            print(f"  {c.id} [NO VERDICT ] {c.text}")
    print(f"  undeclared hunks: {result.undeclared_hunk_ids or 'none'}")
    for w in result.warnings:
        print(f"  WARNING: {w}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="repeat each case to see LLM variation")
    args = ap.parse_args()
    for case in CASES:
        passes = 0
        print(f"\n=== {case['name']} ===\n{case['narration']}")
        for i in range(args.runs):
            result = verify(case["narration"], DIFF)
            passed = meets(case["expect"], result)
            passes += passed
            print(f"-- run {i + 1}: {'PASS' if passed else 'FAIL'}")
            show(result)
        print(f"==> {case['name']}: {passes}/{args.runs} passed")
