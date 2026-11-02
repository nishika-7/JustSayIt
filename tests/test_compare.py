from eval.compare import changed_cases


def run(*pairs):
    return {"results": [{"id": i, "ok": ok} for i, ok in pairs]}


def test_fixed_and_regressed_cases_are_listed():
    prev = run(("a", False), ("b", True), ("c", True), ("d", False))
    cur = run(("a", True), ("b", False), ("c", True), ("e", True))
    assert changed_cases(prev, cur) == (["a"], ["b"])


def test_cases_with_errors_are_ignored():
    prev = {"results": [{"id": "a", "error": "429"}, {"id": "b", "ok": False}]}
    cur = {"results": [{"id": "a", "ok": True}, {"id": "b", "error": "429"}]}
    assert changed_cases(prev, cur) == ([], [])
