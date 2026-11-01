"""All model calls live here. Provider: LLM_PROVIDER=groq|anthropic (default: groq if GROQ_API_KEY is set, else anthropic)."""
import os
import re
import time

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()


def provider() -> str:
    p = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if p in ("groq", "anthropic"):
        return p
    return "groq" if os.environ.get("GROQ_API_KEY") else "anthropic"


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a reply: drop <think> blocks, code fences and chatter around it."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text


def is_busy(e: Exception) -> bool:
    """Rate limit or temporary provider trouble: worth retrying, and not the user's fault."""
    name = type(e).__name__.lower()
    return getattr(e, "status_code", None) in (429, 500, 502, 503, 529) or "ratelimit" in name or "overload" in name


def _call_once(system: str, user: str, model: str | None) -> str:
    name = model or os.environ["MODEL_NAME"]
    if provider() == "groq":
        from groq import Groq  # imported lazily so tests run without the SDK or a key

        resp = Groq().chat.completions.create(
            model=name, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return resp.choices[0].message.content or ""
    from anthropic import Anthropic

    resp = Anthropic().messages.create(model=name, max_tokens=2000, system=system,
                                       messages=[{"role": "user", "content": user}])
    return resp.content[0].text


def _call(system: str, user: str, model: str | None = None, tries: int = 3) -> str:
    for i in range(tries):
        try:
            return _call_once(system, user, model)
        except Exception as e:
            if not is_busy(e) or i == tries - 1:
                raise
            time.sleep(4 * (i + 1))   # back off, then try again


def ask_json(system: str, user: str, model_cls: type[BaseModel], retries: int = 1, model: str | None = None):
    prompt, last_err = user, None
    for _ in range(retries + 1):
        text = _call(system, prompt, model)
        try:
            return model_cls.model_validate_json(_extract_json(text))
        except ValidationError as e:
            last_err = e
            prompt = (user + "\n\nYour previous reply was not valid JSON for the schema:\n" + str(e)[:500]
                      + "\nReply with valid JSON only.")
    raise ValueError(f"Model did not return valid JSON: {last_err}")
