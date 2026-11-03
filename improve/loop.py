"""Idea 1: turn spoken critiques into prompt improvements that you approve."""
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from root import llm, versions

STAGE_KEY = {"verdict": "verifier", "claim splitting": "splitter"}


class Mode(BaseModel):
    name: str
    description: str
    stage: Literal["verdict", "claim splitting"]
    critique_ids: list[int]
    proposed_rule: str


class Modes(BaseModel):
    modes: list[Mode]


def analyze(critiques: list[dict], prompts: dict, prompt_dir: Path | None = None) -> list[Mode]:
    """Group wrong-verdict critiques into failure modes, each with one proposed prompt rule."""
    system = (Path(prompt_dir) if prompt_dir else versions.PROMPT_DIR).joinpath("analyze_v1.md").read_text(encoding="utf-8")
    lines = []
    for i, c in enumerate(critiques):
        line = (f"[{i}] stage={c['stage']} | claim: {c['claim']} | said {c['given_label']}, should be "
                f"{c['correct_label']} | critique: {c['critique'] or '(none given)'}")
        if c.get("evidence"):
            line += "\n    diff lines the verifier looked at:\n" + "\n".join("      " + l for l in c["evidence"].splitlines())
        lines.append(line)
    user = ("CURRENT PROMPTS:\n" + "\n\n".join(f"--- {k} ---\n{v}" for k, v in prompts.items())
            + "\n\nCORRECTIONS:\n" + "\n".join(lines))
    out = llm.ask_json(system, user, Modes)
    modes = []
    for m in out.modes:
        ids = [i for i in m.critique_ids if 0 <= i < len(critiques)]
        if ids and m.proposed_rule.strip():
            modes.append(m.model_copy(update={"critique_ids": ids}))
    return modes


def _next_version(key: str, d: Path) -> str:
    nums = [int(m.group(1)) for p in d.glob(f"{key}_v*.md") if (m := re.fullmatch(rf"{key}_v(\d+)\.md", p.name))]
    return f"{key}_v{max(nums, default=0) + 1}"


def accept_rules(stage: str, rules: list[str], prompt_dir: Path | None = None) -> str:
    """Append approved rules to the active prompt as a new version file and make it active."""
    d = Path(prompt_dir) if prompt_dir else versions.PROMPT_DIR
    key = STAGE_KEY[stage]
    rules = [r.strip() for r in rules if r.strip()]
    if not rules:
        raise ValueError("No rules selected.")
    text = (d / f"{versions.active(d)[key]}.md").read_text(encoding="utf-8").rstrip()
    if "## Learned rules" not in text:
        text += "\n\n## Learned rules"
    text += "".join(f"\n- {r}" for r in rules) + "\n"
    new = _next_version(key, d)
    (d / f"{new}.md").write_text(text, encoding="utf-8")
    versions.set_active(key, new, d)
    return new
