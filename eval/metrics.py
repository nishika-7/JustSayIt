KINDS = ["clean", "omission", "false_claim", "contradiction", "comment_trap", "partial_claim"]


def judge(case: dict, labels: list[str], undeclared: list[str]) -> dict:
    """Did the verifier get this case right? Also records whether it flagged a problem at all."""
    flagged = any(l != "supported" for l in labels)
    problem = flagged or bool(undeclared)
    kind = case["kind"]
    if kind == "clean":
        ok = not problem
    elif kind == "omission":
        ok = set(case["gold_undeclared"]) <= set(undeclared) and not flagged
    else:  # false_claim, contradiction
        ok = flagged
    exact = {"false_claim": "unsupported", "contradiction": "contradicted"}.get(kind)
    return {"ok": ok, "predicted_problem": problem, "exact_label": (exact in labels) if exact else None}


def _acc(rs):
    return round(sum(r["ok"] for r in rs) / len(rs), 3) if rs else None


def summarize(results: list[dict]) -> dict:
    good = [r for r in results if "error" not in r]
    per_kind = {}
    for k in KINDS:
        rs = [r for r in good if r["kind"] == k]
        if rs:
            per_kind[k] = {"n": len(rs), "accuracy": _acc(rs)}
    tp = sum(r["kind"] != "clean" and r["predicted_problem"] for r in good)
    fn = sum(r["kind"] != "clean" and not r["predicted_problem"] for r in good)
    fp = sum(r["kind"] == "clean" and r["predicted_problem"] for r in good)
    clean = sum(r["kind"] == "clean" for r in good)
    prec = round(tp / (tp + fp), 3) if tp + fp else None
    rec = round(tp / (tp + fn), 3) if tp + fn else None
    f1 = round(2 * prec * rec / (prec + rec), 3) if prec and rec else None
    return {
        "n": len(results), "errors": len(results) - len(good), "overall_accuracy": _acc(good), "per_kind": per_kind,
        "problem_detection": {"precision": prec, "recall": rec, "f1": f1,
                              "false_alarm_rate": round(fp / clean, 3) if clean else None},
        "by_split": {s: _acc([r for r in good if r["split"] == s]) for s in ("dev", "holdout")},
    }
