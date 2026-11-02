import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from root import llm, versions
from improve import rollback
from server.main import create_app
import preflight
from tests.test_improve_server import fake

ROOT = Path(__file__).resolve().parent.parent


def http_for(client):
    def http(method, url, body=None, timeout=60):
        r = client.request(method, "/" + url.split("//", 1)[1].split("/", 1)[1], json=body)
        return r.status_code, r.text
    return http


def levels(rep):
    return {name: level for level, name, _ in rep.rows}


def test_live_checks_pass_on_a_healthy_public_app(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ask_json", fake)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k in ("TEACH_MODE", "MAX_RUNS_PER_IP", "MAX_DIFF_CHARS"):
        monkeypatch.delenv(k, raising=False)
    rep = preflight.Report()
    preflight.live_checks(rep, "http://app.test", http_for(TestClient(create_app())), wait=0)
    lv = levels(rep)
    assert lv["server is up"] == lv["home page loads"] == lv["public mode (TEACH_MODE is off)"] == lv["owner endpoints are hidden"] == "PASS"
    assert lv["real verification works end to end"] == "PASS"
    assert not rep.failed()


def test_live_checks_fail_if_owner_mode_is_on_in_production(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ask_json", fake)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TEACH_MODE", "1")
    rep = preflight.Report()
    preflight.live_checks(rep, "http://app.test", http_for(TestClient(create_app())), verify=False, wait=0)
    lv = levels(rep)
    assert lv["public mode (TEACH_MODE is off)"] == "FAIL" and lv["owner endpoints are hidden"] == "FAIL"


def test_local_checks_run_and_report_prompts(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    rep = preflight.Report()
    preflight.local_checks(rep, ROOT)
    lv = levels(rep)
    assert lv["active prompt files exist"] == "PASS" and lv["MODEL_NAME is set"] == "PASS"


def test_rollback(monkeypatch, tmp_path, capsys):
    shutil.copytree(ROOT / "prompts", tmp_path / "p")
    monkeypatch.setattr(versions, "PROMPT_DIR", tmp_path / "p")
    from improve import loop
    loop.accept_rules("verdict", ["A rule."], tmp_path / "p")
    assert versions.active()["verifier"] == "verifier_v2"
    rollback.main(["verifier", "verifier_v1"])
    assert versions.active()["verifier"] == "verifier_v1"
    try:
        rollback.main(["verifier", "verifier_v9"])
        assert False, "should have exited"
    except SystemExit:
        pass
