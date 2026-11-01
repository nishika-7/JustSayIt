from unidiff import PatchSet

from .models import Hunk


def parse_diff(diff_text: str) -> list[Hunk]:
    """Turn a unified git diff into a flat list of hunks with stable ids."""
    patch = PatchSet(diff_text)
    hunks: list[Hunk] = []
    for patched_file in patch:
        for h in patched_file:
            hunks.append(
                Hunk(
                    id=f"h{len(hunks) + 1}",
                    file=patched_file.path,
                    header=(h.section_header or "").strip(),
                    added=[l.value.rstrip("\n") for l in h if l.is_added],
                    removed=[l.value.rstrip("\n") for l in h if l.is_removed],
                    text=str(h),
                )
            )
    return hunks
