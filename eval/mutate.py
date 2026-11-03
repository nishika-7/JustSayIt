"""Turn correct claims into labelled test cases. The errors are injected by code, so those labels are certain."""
import os
import random
import re

from .models import Case, GoldClaim

_FLIP = {"added": "removed", "removed": "added", "increased": "decreased", "decreased": "increased",
         "enabled": "disabled", "disabled": "enabled"}
_FLIP_RE = re.compile(r"\b(" + "|".join(_FLIP) + r")\b", re.I)


def flip_verb(text: str) -> str | None:
    m = _FLIP_RE.search(text)
    if not m:
        return None
    word = m.group(1)
    new = _FLIP[word.lower()]
    new = new.capitalize() if word[0].isupper() else new
    return text[: m.start()] + new + text[m.end():]


def join_claims(texts: list[str]) -> str:
    return " ".join(t.strip() if t.strip()[-1:] in ".!?" else t.strip() + "." for t in texts)


def make_cases(commit: str, split: str, claims: list[GoldClaim], hunk_ids: list[str],
               foreign: list[GoldClaim], seed: str, files: list[str] | None = None) -> list[Case]:
    rng = random.Random(seed)
    texts = [c.text for c in claims]
    base = dict(commit=commit, split=split)
    cases = [Case(id=f"{commit}:clean", kind="clean", narration=join_claims(texts), **base)]

    if len(hunk_ids) >= 2:  # omission: drop every claim that mentions one hunk
        h = rng.choice(hunk_ids)
        kept = [c for c in claims if h not in c.hunk_ids]
        covered = {i for c in kept for i in c.hunk_ids}
        missing = [x for x in hunk_ids if x not in covered]
        if kept and missing:
            cases.append(Case(id=f"{commit}:omission", kind="omission", gold_undeclared=missing,
                              narration=join_claims([c.text for c in kept]), **base))

    if foreign:  # false claim: a claim that belongs to a different commit
        extra = rng.choice(foreign).text
        mixed = texts[:]
        mixed.insert(rng.randint(0, len(mixed)), extra)
        cases.append(Case(id=f"{commit}:false_claim", kind="false_claim", narration=join_claims(mixed), **base))

    flippable = [i for i, t in enumerate(texts) if flip_verb(t)]
    if flippable:  # contradiction: flip a verb (added <-> removed, ...)
        i = rng.choice(flippable)
        flipped = texts[:]
        flipped[i] = flip_verb(flipped[i])
        cases.append(Case(id=f"{commit}:contradiction", kind="contradiction", narration=join_claims(flipped), **base))
    # partial claim: a true claim plus a tail about tests that the diff never touches
    if files is not None and texts and not any(re.search(r"test|doc|readme|\.md$", f, re.I) for f in files):
        partial = texts[:]
        i = rng.randrange(len(partial))
        partial[i] = partial[i].rstrip(" .") + " and also updated the unit tests"
        cases.append(Case(id=f"{commit}:partial_claim", kind="partial_claim", narration=join_claims(partial), **base))
    return cases


_MARK = {".py": "#", ".sh": "#", ".rb": "#", ".yml": "#", ".yaml": "#", ".toml": "#", ".js": "//", ".jsx": "//",
         ".ts": "//", ".tsx": "//", ".java": "//", ".c": "//", ".cpp": "//", ".h": "//", ".go": "//", ".rs": "//",
         ".cs": "//", ".kt": "//", ".php": "//", ".swift": "//"}


def comment_out_hunk(diff_text: str, hunk_no: int) -> str | None:
    """Turn the added lines of one hunk (1-based, same numbering as h1, h2...) into comments. Line counts stay the same."""
    out, path, n, changed = [], "", 0, False
    for line in diff_text.split("\n"):
        if line.startswith("+++ "):
            path = line[4:].strip()
        elif line.startswith("@@"):
            n += 1
        elif n == hunk_no and line.startswith("+") and line[1:].strip():
            mark = _MARK.get(os.path.splitext(path)[1].lower())
            if mark is None:
                return None
            body = line[1:]
            line = f"+{body[: len(body) - len(body.lstrip())]}{mark} {body.lstrip()}"
            changed = True
        out.append(line)
    return "\n".join(out) if changed else None


def make_comment_trap(commit: str, split: str, claims: list[GoldClaim], added_hunks: list[int],
                      diff_text: str, seed: str):
    """Same correct description, but the diff only has the new code as comments. Returns (case, modified diff) or None."""
    rng = random.Random(seed + ":comment_trap")
    for no in rng.sample(added_hunks, len(added_hunks)):
        variant = comment_out_hunk(diff_text, no)
        if variant:
            case = Case(id=f"{commit}:comment_trap", commit=commit, split=split, kind="comment_trap",
                        narration=join_claims([c.text for c in claims]),
                        diff_file=f"cases/variants/{commit}__comment.diff")
            return case, variant
    return None
