"""Compare evaluation rounds and list which cases got fixed or broke.
   python -m eval.compare round0b round1 [round2 ...]"""
import json
import sys

from root.store import data_dir
from .metrics import KINDS


def load(label: str) -> dict:
    return json.loads((data_dir() / "runs" / f"{label}.json").read_text(encoding="utf-8"))


def changed_cases(prev: dict, cur: dict) -> tuple[list[str], list[str]]:
    """(fixed, regressed) case ids between two saved runs; cases with errors are ignored."""
    p = {r["id"]: r.get("ok") for r in prev["results"] if "error" not in r}
    c = {r["id"]: r.get("ok") for r in cur["results"] if "error" not in r}
    both = p.keys() & c.keys()
    return sorted(i for i in both if not p[i] and c[i]), sorted(i for i in both if p[i] and not c[i])


def pct(v) -> str:
    return "-" if v is None else f"{round(v * 100)}%"


def main() -> None:
    labels = sys.argv[1:]
    if len(labels) < 2:
        sys.exit("usage: python -m eval.compare round0b round1 [round2 ...]")
    runs = [load(l) for l in labels]
    print(f"{'':16}" + "".join(f"{l:>12}" for l in labels))
    print(f"{'overall':16}" + "".join(f"{pct(r['summary']['overall_accuracy']):>12}" for r in runs))
    for k in KINDS:
        if any(k in r["summary"]["per_kind"] for r in runs):
            print(f"{k:16}" + "".join(f"{pct(r['summary']['per_kind'].get(k, {}).get('accuracy')):>12}" for r in runs))
    print(f"{'holdout':16}" + "".join(f"{pct(r['summary']['by_split'].get('holdout')):>12}" for r in runs))
    print(f"{'words entered':16}" + "".join(f"{r.get('spoken_words', '-'):>12}" for r in runs))
    for (la, a), (lb, b) in zip(zip(labels, runs), zip(labels[1:], runs[1:])):
        fixed, broke = changed_cases(a, b)
        print(f"\n{la} -> {lb}: fixed {len(fixed)}, regressed {len(broke)}")
        for i in fixed:
            print("  fixed    ", i)
        for i in broke:
            print("  REGRESSED", i)


if __name__ == "__main__":
    main()
