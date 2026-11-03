"""Turn saved diffs into labelled test cases.  python -m eval.build_cases
Set CASEGEN_MODEL to a different model than MODEL_NAME if you can: it makes the test data less circular."""
import argparse
import hashlib
import json
import os
import time

from root import llm
from root.diff_parser import parse_diff
from root.store import data_dir
from root.verifier import format_hunks, load_prompt

from .models import GoldClaim, GoldClaims
from .mutate import make_comment_trap, make_cases


def split_of(commit: str) -> str:
    return "dev" if int(hashlib.sha1(commit.encode()).hexdigest(), 16) % 10 < 7 else "holdout"


def gold_claims(diff_path, cache_dir, delay: float = 0) -> list[GoldClaim] | None:
    cache = cache_dir / f"{diff_path.stem}.json"
    if cache.exists():
        return GoldClaims.model_validate_json(cache.read_text(encoding="utf-8")).claims
    hunks = parse_diff(diff_path.read_text(encoding="utf-8"))
    out = llm.ask_json(load_prompt("casegen_v1"), "DIFF HUNKS:\n" + format_hunks(hunks), GoldClaims,
                       model=os.environ.get("CASEGEN_MODEL") or None)
    time.sleep(delay)  # only reached when the model was actually called (cached commits return earlier)
    ids = {h.id for h in hunks}
    covered = {i for c in out.claims for i in c.hunk_ids}
    if not out.claims or any(not set(c.hunk_ids) <= ids or not c.hunk_ids for c in out.claims) or covered != ids:
        return None  # claims cite unknown hunks or leave one uncovered: not trustworthy as gold
    cache.write_text(out.model_dump_json(indent=1), encoding="utf-8")
    return out.claims


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=2.0, help="seconds to wait after each new model call")
    args = ap.parse_args()
    root = data_dir()
    cache_dir = root / "cases" / "gold"
    cache_dir.mkdir(parents=True, exist_ok=True)
    gold, skipped = {}, []
    for p in sorted((root / "commits").glob("*.diff")):
        claims = gold_claims(p, cache_dir, args.delay)
        (gold.__setitem__(p.stem, claims) if claims else skipped.append(p.stem))
    cases = []
    for stem, claims in gold.items():
        text = (root / "commits" / f"{stem}.diff").read_text(encoding="utf-8")
        hunks = parse_diff(text)
        hunk_ids = [h.id for h in hunks]
        others = [c for s, cs in gold.items() if s != stem for c in cs]
        other_repo = [c for s, cs in gold.items() if s.split("_")[0] != stem.split("_")[0] for c in cs]
        cases += make_cases(stem, split_of(stem), claims, hunk_ids, other_repo or others, seed=stem,
                            files=sorted({h.file for h in hunks}))
        added = [i + 1 for i, h in enumerate(hunks) if any(l.strip() for l in h.added)]
        trap = make_comment_trap(stem, split_of(stem), claims, added, text, seed=stem)
        if trap:
            case, variant = trap
            (root / case.diff_file).parent.mkdir(parents=True, exist_ok=True)
            (root / case.diff_file).write_text(variant, encoding="utf-8")
            cases.append(case)
    out = root / "cases" / "cases.jsonl"
    out.write_text("\n".join(c.model_dump_json() for c in cases) + "\n", encoding="utf-8")
    kinds = {}
    for c in cases:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    print(f"{len(cases)} cases from {len(gold)} commits -> {out}\nby kind: {json.dumps(kinds)}")
    if skipped:
        print(f"skipped (model's claims were not trustworthy): {skipped}")


if __name__ == "__main__":
    main()
