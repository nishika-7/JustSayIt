"""Runs the Streamlit app headlessly with a fake LLM. No API key or browser needed."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from root import llm
from root.models import Claim, ClaimList, Verdict, VerifierOutput

APP = str(Path(__file__).resolve().parent.parent / "app" / "main.py")


def fake_ask_json(system, user, model_cls, retries=1):
    if model_cls is ClaimList:
        return ClaimList(claims=[Claim(id="c1", text="added retry logic to login")])
    return VerifierOutput(verdicts=[Verdict(claim_id="c1", label="supported", evidence_hunk_ids=["h1"], reason="loop with retries")])


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    st.cache_resource.clear()
    monkeypatch.setattr(llm, "ask_json", fake_ask_json)


def new_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=30).run()


def test_loads_with_first_example_prefilled():
    at = new_app()
    assert not at.exception
    assert "def login" in at.text_area(key="diff").value
    assert at.text_area(key="narration").value


def test_verify_shows_table_and_unmentioned_change():
    at = new_app()
    at.button(key="verify").click().run()
    assert not at.exception and not at.error
    assert len(at.dataframe) == 1
    assert at.dataframe[0].value.iloc[0]["Verdict"] == "✅ supported"
    assert len(at.expander) == 1  # the hunk the description didn't mention


def test_empty_description_shows_error_not_crash():
    at = new_app()
    at.text_area(key="narration").set_value("").run()
    at.button(key="verify").click().run()
    assert not at.exception
    assert len(at.error) == 1


def test_session_limit(monkeypatch):
    monkeypatch.setenv("MAX_RUNS_PER_SESSION", "1")
    at = new_app()
    at.button(key="verify").click().run()
    at.button(key="verify").click().run()
    assert not at.exception
    assert len(at.warning) == 1


def test_public_mode_saves_nothing_and_has_no_teach_panel(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    at = new_app()
    at.button(key="verify").click().run()
    assert not at.exception
    assert not (tmp_path / "runs").exists()
    assert "Teach it" not in [s.value for s in at.subheader]


def test_owner_mode_logs_run_and_saves_critique(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TEACH_MODE", "1")
    at = new_app()
    at.button(key="verify").click().run()
    assert not at.exception
    rid = at.session_state["run_id"]
    assert (tmp_path / "runs" / "log.jsonl").exists()
    at.selectbox(key=f"fb_label_{rid}_c1").select("unsupported")
    at.text_area(key=f"fb_text_{rid}_c1").set_value("Wrong because it only found a comment. Should have said unsupported.")
    at.button(key=f"fb_save_{rid}_c1").click().run()
    assert not at.exception
    from core.store import load_critiques
    (rec,) = load_critiques()
    assert rec["correct_label"] == "unsupported" and rec["run_id"] == rid and rec["verifier_version"] == "verifier_v1"
