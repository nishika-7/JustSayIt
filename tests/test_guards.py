from pathlib import Path

from root.guards import MAX_DIFF_CHARS, check_inputs

DIFF = (Path(__file__).parent / "sample.diff").read_text(encoding="utf-8")


def test_valid_inputs_pass():
    assert check_inputs(DIFF, "I added retry logic to login.") is None


def test_empty_and_short_inputs():
    assert check_inputs("", "I changed login") is not None
    assert check_inputs(DIFF, "") is not None
    assert check_inputs(DIFF, "ok") is not None


def test_too_large_diff():
    assert "too large" in check_inputs("x" * (MAX_DIFF_CHARS + 1), "I changed a lot of things")


def test_non_diff_text_is_rejected():
    assert check_inputs("hello this is not a diff at all", "I changed some things") is not None
