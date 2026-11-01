import json
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT = {"splitter": "splitter_v1", "verifier": "verifier_v1"}


def _dir(prompt_dir) -> Path:
    return Path(prompt_dir) if prompt_dir else PROMPT_DIR


def active(prompt_dir=None) -> dict:
    """Prompt version used by each stage (prompts/active.json)."""
    path = _dir(prompt_dir) / "active.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(DEFAULT)


def set_active(key: str, version: str, prompt_dir=None) -> None:
    d = _dir(prompt_dir)
    data = active(d)
    data[key] = version
    (d / "active.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def list_versions(prompt_dir=None) -> dict:
    d = _dir(prompt_dir)
    return {k: sorted((p.stem for p in d.glob(f"{k}_v*.md")), key=lambda s: (len(s), s)) for k in ("splitter", "verifier")}
