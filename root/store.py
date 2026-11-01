"""Owner-mode storage for the improvement loop (idea 1): every run, and every spoken critique."""
import json
import os
import time
import uuid
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parent.parent / "data")


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def log_run(narration: str, diff_text: str, result) -> str:
    run_id = uuid.uuid4().hex[:8]
    _append(data_dir() / "runs" / "log.jsonl",
            {"run_id": run_id, "ts": time.time(), "narration": narration, "diff": diff_text, "result": result.model_dump()})
    return run_id


def add_critique(run_id, claim_id, claim, given_label, correct_label, stage, critique, verifier_version, splitter_version) -> None:
    _append(data_dir() / "critiques.jsonl", {
        "run_id": run_id, "claim_id": claim_id, "claim": claim, "given_label": given_label,
        "correct_label": correct_label, "was_right": given_label == correct_label, "stage": stage,
        "critique": critique, "verifier_version": verifier_version, "splitter_version": splitter_version, "ts": time.time(),
    })


def _example_narrations() -> set:
    path = Path(__file__).resolve().parent.parent / "data" / "examples" / "examples.json"
    return {e["narration"] for e in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else set()


def spoken_words(until_ts: float | None = None) -> int:
    """Words you entered in owner mode up to a time: distinct descriptions + critique texts.
    Built-in example descriptions are skipped. Typed words count too, so this can overstate dictation."""
    cut = float("inf") if until_ts is None else until_ts
    seen, total = _example_narrations(), 0
    for r in _read(data_dir() / "runs" / "log.jsonl"):
        if r["ts"] <= cut and r["narration"] not in seen:
            seen.add(r["narration"])
            total += len(r["narration"].split())
    return total + sum(len(c["critique"].split()) for c in load_critiques() if c["ts"] <= cut)


def run_evidence(run_id: str, claim_id: str, limit: int = 700) -> str:
    """The diff lines the verifier cited for one claim in a logged run (or the start of the diff if it cited none)."""
    from .diff_parser import parse_diff
    for r in _read(data_dir() / "runs" / "log.jsonl"):
        if r["run_id"] == run_id:
            v = next((v for v in r["result"]["verdicts"] if v["claim_id"] == claim_id), None)
            hunks = {h.id: h for h in parse_diff(r["diff"])}
            cited = "\n".join(hunks[i].text for i in (v["evidence_hunk_ids"] if v else []) if i in hunks)
            return (cited or r["diff"])[:limit]
    return ""


def load_critiques() -> list[dict]:
    return _read(data_dir() / "critiques.jsonl")
