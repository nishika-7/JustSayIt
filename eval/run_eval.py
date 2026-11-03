"""Score the verifier on the labelled cases (one at a time, with a pause so free-tier rate limits are not hit).
   python -m eval.run_eval --label round0 [--split all|dev|holdout] [--limit N] [--delay 2]"""
import argparse
import json
import time

from root.store import data_dir, spoken_words
from root.verifier import verify

from .metrics import judge, summarize
from .models import Case


def load_cases(split: str = "all", limit: int | None = None) -> list[Case]:
    lines = (data_dir() / "cases" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [Case.model_validate_json(l) for l in lines if l.strip()]
    if split != "all":
        cases = [c for c in cases if c.split == split]
    if limit and limit < len(cases):
        cases = cases[:: max(1, len(cases) // limit)][:limit]  # spread across commits
    return cases


def run_one(case: Case) -> dict:
    base = {"id": case.id, "kind": case.kind, "split": case.split}
    diff = (data_dir() / (case.diff_file or f"commits/{case.commit}.diff")).read_text(encoding="utf-8")
    try:
        r = verify(case.narration, diff)
    except Exception as e:
        return {**base, "error": f"{type(e).__name__}: {e}"}
    by_id = {v.claim_id: v for v in r.verdicts}
    labels = [v.label for v in r.verdicts]
    return {**base, **judge(case.model_dump(), labels, r.undeclared_hunk_ids), "narration": case.narration,
            "claims": [{"text": c.text, "label": by_id[c.id].label if c.id in by_id else "unverified",
                        "reason": by_id[c.id].reason if c.id in by_id else ""} for c in r.claims],
            "labels": labels, "undeclared": r.undeclared_hunk_ids, "warnings": r.warnings,
            "splitter": r.splitter_version, "verifier": r.verifier_version}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--split", default="all", choices=["all", "dev", "holdout"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--delay", type=float, default=2.0, help="Seconds to sleep between cases to avoid rate limits")
    args = ap.parse_args()
    cases = load_cases(args.split, args.limit)
    print(f"Running {len(cases)} cases (about {2 * len(cases)} model calls) with a {args.delay}s delay...")
    results = []
    for i, case in enumerate(cases):
        results.append(run_one(case))
        if i < len(cases) - 1:
            time.sleep(args.delay)
    summary = summarize(results)
    out = data_dir() / "runs" / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"label": args.label, "ts": time.time(), "spoken_words": spoken_words(), "summary": summary, "results": results}, indent=1),
                   encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for r in results:
        if "error" in r:
            print("ERROR", r["id"], r["error"])
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
