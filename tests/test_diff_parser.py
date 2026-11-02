from pathlib import Path

from root.diff_parser import parse_diff

DIFF = (Path(__file__).parent / "sample.diff").read_text(encoding="utf-8")


def test_two_hunks_with_stable_ids():
    hunks = parse_diff(DIFF)
    assert [h.id for h in hunks] == ["h1", "h2"]
    assert all(h.file == "auth/login.py" for h in hunks)


def test_function_context_is_captured():
    hunks = parse_diff(DIFF)
    assert "login" in hunks[0].header
    assert "refresh_token" in hunks[1].header


def test_added_and_removed_lines():
    h1, h2 = parse_diff(DIFF)
    assert len(h1.added) == 7 and len(h1.removed) == 1
    assert len(h2.added) == 0 and len(h2.removed) == 2
    assert any("time.sleep" in line for line in h1.added)
