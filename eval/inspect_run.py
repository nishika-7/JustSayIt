"""See what the verifier actually said on each case.
   python -m eval.inspect_run round0 [--kind comment_trap] [--failures]"""
import argparse
import json

from root.store import data_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--kind")
    ap.add_argument("--failures", action="store_true")
    args = ap.parse_args()
    data = json.loads((data_dir() / "runs" / f"{args.label}.json").read_text(encoding="utf-8"))
    shown = 0
    for r in data["results"]:
        failed = r.get("ok") is False or "error" in r
        if (args.kind and r["kind"] != args.kind) or (args.failures and not failed):
            continue
        shown += 1
        print(f"\n=== {r['id']}  [{r['kind']}]  {'FAIL' if failed else 'pass'}")
        if "error" in r:
            print("  error:", r["error"])
            continue
        print("  said:", r["narration"])
        for c in r["claims"]:
            print(f"  - {c['label']:<12} {c['text']}  -- {c['reason']}")
        if r["undeclared"]:
            print("  undeclared hunks:", r["undeclared"])
    print(f"\n{shown} case(s) shown")


if __name__ == "__main__":
    main()
