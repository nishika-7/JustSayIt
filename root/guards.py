"""Input checks that run before any LLM call, so bad input never costs an API request."""
import os

from .diff_parser import parse_diff

MAX_DIFF_CHARS = 30_000
MIN_NARRATION_WORDS = 3
MAX_NARRATION_WORDS = 400


def max_diff_chars() -> int:
    return int(os.environ.get("MAX_DIFF_CHARS") or MAX_DIFF_CHARS)


def check_inputs(diff_text: str, narration: str) -> str | None:
    """Return a friendly error message, or None if the inputs are fine."""
    if not diff_text.strip():
        return "Paste a git diff, load an example, or fetch a public GitHub commit first."
    if len(diff_text) > max_diff_chars():
        return f"That diff is too large for the demo (limit {max_diff_chars():,} characters). Try a smaller change."
    words = len(narration.split())
    if words < MIN_NARRATION_WORDS:
        return "Say what you changed first: click the narration box and talk, or type a sentence."
    if words > MAX_NARRATION_WORDS:
        return f"The description is too long ({words} words). Keep it under {MAX_NARRATION_WORDS}."
    try:
        hunks = parse_diff(diff_text)
    except Exception:
        return "That doesn't look like a git diff."
    if not hunks:
        return "No code changes found in that diff."
    return None
