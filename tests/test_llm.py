import pytest
from pydantic import BaseModel

from root import llm


class Rate(Exception):
    status_code = 429


def test_retries_when_busy_then_succeeds(monkeypatch):
    calls = []

    def once(system, user, model):
        calls.append(1)
        if len(calls) < 3:
            raise Rate()
        return "ok"
    monkeypatch.setattr(llm, "_call_once", once)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm._call("s", "u") == "ok" and len(calls) == 3


def test_gives_up_after_three_tries_and_does_not_retry_other_errors(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    n = []
    monkeypatch.setattr(llm, "_call_once", lambda s, u, m: n.append(1) or (_ for _ in ()).throw(Rate()))
    with pytest.raises(Rate):
        llm._call("s", "u")
    assert len(n) == 3
    n.clear()
    monkeypatch.setattr(llm, "_call_once", lambda s, u, m: n.append(1) or (_ for _ in ()).throw(KeyError("MODEL_NAME")))
    with pytest.raises(KeyError):
        llm._call("s", "u")
    assert len(n) == 1


def test_extract_json_handles_think_blocks_fences_and_chatter():
    assert llm._extract_json('<think>hmm {x}</think>\nSure! ```json\n{"a": 1}\n``` hope that helps') == '{"a": 1}'
    assert llm._extract_json('{"a": 1}') == '{"a": 1}'


def test_ask_json_recovers_from_a_first_bad_reply(monkeypatch):
    class M(BaseModel):
        a: int
    replies = iter(["not json at all", 'Here you go: {"a": 5}'])
    monkeypatch.setattr(llm, "_call", lambda s, u, m=None: next(replies))
    assert llm.ask_json("s", "u", M).a == 5


def test_provider_choice(monkeypatch):
    for k in ("LLM_PROVIDER", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert llm.provider() == "anthropic"
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert llm.provider() == "groq"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert llm.provider() == "anthropic"
