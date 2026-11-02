"""Every api(...) call in the page must match a real route and method. (A call without a body is a GET.)"""
import re
from pathlib import Path

from server.main import create_app

HTML = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")


def test_every_call_the_page_makes_matches_a_server_route(monkeypatch):
    monkeypatch.setenv("TEACH_MODE", "1")
    routes = {(r.path, m) for r in create_app().routes if hasattr(r, "methods") for m in r.methods}
    calls = re.findall(r"api\('(/api/[^']+)'(,?)", HTML)
    assert len(calls) >= 8
    for path, comma in calls:
        method = "POST" if comma else "GET"
        assert (path, method) in routes, f"page calls {method} {path} but the server has {sorted(m for p, m in routes if p == path)}"
