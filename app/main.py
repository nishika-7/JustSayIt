import json
import os
import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `core` imports work locally and on Streamlit Cloud

import pandas as pd
import streamlit as st

from root.diff_parser import parse_diff
from root.github import FetchError, fetch_commit_diff
from root.guards import check_inputs
from root.store import add_critique, load_critiques, log_run
from root.verifier import verify

st.set_page_config(page_title="Say what you changed", page_icon="🎙️", layout="wide")

# Streamlit Cloud secrets -> environment variables used by core/llm.py
for _key in ("LLM_PROVIDER", "GROQ_API_KEY", "MAX_DIFF_CHARS", "ANTHROPIC_API_KEY", "MODEL_NAME", "MAX_RUNS_PER_SESSION", "MAX_RUNS_GLOBAL", "TEACH_MODE", "SHOW_ERRORS"):
    if not os.environ.get(_key):
        try:
            os.environ[_key] = str(st.secrets[_key])
        except Exception:
            pass

EX_DIR = ROOT / "data" / "examples"
SAMPLE_DIFF = (EX_DIR / "sample.diff").read_text(encoding="utf-8")
EXAMPLES = json.loads((EX_DIR / "examples.json").read_text(encoding="utf-8"))
MAX_RUNS_SESSION = int(os.environ.get("MAX_RUNS_PER_SESSION", "6"))
MAX_RUNS_GLOBAL = int(os.environ.get("MAX_RUNS_GLOBAL", "300"))
TEACH_MODE = os.environ.get("TEACH_MODE") == "1"   # owner mode: save runs + critiques (never on the public app)
SHOW_ERRORS = os.environ.get("SHOW_ERRORS") == "1"
LABELS = {"supported": "✅ supported", "unsupported": "⚠️ unsupported", "contradicted": "❌ contradicted"}


@st.cache_resource
def global_usage() -> dict:
    return {"runs": 0}  # shared by all visitors; protects the API key


def load_example(i: int) -> None:
    st.session_state.diff = SAMPLE_DIFF
    st.session_state.narration = EXAMPLES[i]["narration"]
    st.session_state.result = None


def fetch_github() -> None:
    try:
        st.session_state.diff = fetch_commit_diff(st.session_state.gh_url)
        st.session_state.result = None
        st.session_state.gh_error = ""
    except FetchError as e:
        st.session_state.gh_error = str(e)


def show_result(result, hunks) -> None:
    by_id = {v.claim_id: v for v in result.verdicts}
    hunk_by_id = {h.id: h for h in hunks}
    rows = []
    for c in result.claims:
        v = by_id.get(c.id)
        cited = [f"{hid} ({hunk_by_id[hid].file})" for hid in (v.evidence_hunk_ids if v else []) if hid in hunk_by_id]
        rows.append({
            "Claim": c.text,
            "Verdict": LABELS[v.label] if v else "no verdict",
            "Evidence": ", ".join(cited) or "-",
            "Reason": v.reason if v else "",
        })
    counts = Counter(v.label for v in result.verdicts)
    st.subheader("Result")
    st.write(
        f"{len(result.claims)} claims checked: {counts['supported']} supported, "
        f"{counts['unsupported']} unsupported, {counts['contradicted']} contradicted."
    )
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    if result.undeclared_hunk_ids:
        st.subheader("Changes you didn't mention")
        for hid in result.undeclared_hunk_ids:
            h = hunk_by_id.get(hid)
            if h:
                with st.expander(f"{h.file} {h.header}"):
                    st.code(h.text, language="diff")
    else:
        st.success("Every change in the diff is covered by what you said.")
    if result.warnings:
        with st.expander("Checker warnings"):
            for w in result.warnings:
                st.write(w)


def show_teach(result) -> None:
    st.subheader("Teach it")
    st.caption("Fix wrong verdicts. In the critique box, hold your Flow key and say: Wrong because ... Should have ...")
    labels = ["supported", "unsupported", "contradicted"]
    rid = st.session_state.run_id
    by_id = {v.claim_id: v for v in result.verdicts}
    for c in result.claims:
        v = by_id.get(c.id)
        if not v:
            continue
        st.markdown(f"**{c.id}** {c.text} -> {LABELS[v.label]}")
        a, b = st.columns(2)
        correct = a.selectbox("Should have been", labels, index=labels.index(v.label), key=f"fb_label_{rid}_{c.id}")
        stage = b.selectbox("Problem is in", ["verdict", "claim splitting"], key=f"fb_stage_{rid}_{c.id}")
        text = st.text_area("Critique", key=f"fb_text_{rid}_{c.id}", height=70, placeholder="Wrong because ... Should have ...")
        if st.button("Save", key=f"fb_save_{rid}_{c.id}"):
            add_critique(rid, c.id, c.text, v.label, correct, stage, text.strip(), result.verifier_version, result.splitter_version)
            st.success("Saved.")


def run_verification() -> None:
    problem = check_inputs(st.session_state.diff, st.session_state.narration)
    if problem:
        st.error(problem)
    elif st.session_state.runs >= MAX_RUNS_SESSION:
        st.warning("You've used all your checks for this session. Reload the page to start a new one.")
    elif global_usage()["runs"] >= MAX_RUNS_GLOBAL:
        st.warning("The demo has hit its usage limit for now. Please try again later.")
    else:
        with st.spinner("Checking each claim against the diff..."):
            try:
                result = verify(st.session_state.narration, st.session_state.diff)
            except Exception as e:
                st.session_state.result = None
                traceback.print_exc()  # full details in the terminal
                st.error("Something went wrong while checking. Please try again in a moment.")
                st.caption(f"({type(e).__name__}: {e})" if SHOW_ERRORS else f"({type(e).__name__})")
                return
        st.session_state.hunks = parse_diff(st.session_state.diff)
        st.session_state.result = result
        st.session_state.run_id = log_run(st.session_state.narration, st.session_state.diff, result) if TEACH_MODE else ""
        st.session_state.runs += 1
        global_usage()["runs"] += 1


if "diff" not in st.session_state:
    st.session_state.update(
        diff=SAMPLE_DIFF, narration=EXAMPLES[0]["narration"],
        result=None, hunks=[], runs=0, gh_url="", gh_error="", run_id="",
    )

with st.sidebar:
    st.header("Try it in a minute")
    st.markdown(
        "1. Load an example, paste your own diff, or fetch a public GitHub commit.\n"
        "2. Click the description box, hold your Wispr Flow key and describe the change.\n"
        "3. Press **Verify**."
    )
    st.metric("Words in description", len(st.session_state.narration.split()))
    st.caption(f"Checks left this session: {max(MAX_RUNS_SESSION - st.session_state.runs, 0)}")
    if TEACH_MODE:
        st.caption("Owner mode: runs and critiques are saved to the data folder.")
        st.metric("Critique words saved", sum(len(c["critique"].split()) for c in load_critiques()))

st.title("Say what you changed")
st.caption("Dictate your commit or PR description. Every claim is checked against the real diff.")

st.write("**Load an example:**")
cols = st.columns(len(EXAMPLES))
for i, ex in enumerate(EXAMPLES):
    cols[i].button(ex["title"], key=f"ex{i}", on_click=load_example, args=(i,))

left, right = st.columns(2)
with left:
    st.subheader("1. The change")
    st.text_area("Git diff", key="diff", height=340, label_visibility="collapsed")
    c1, c2 = st.columns([4, 1])
    c1.text_input("Or a public GitHub commit URL", key="gh_url", placeholder="https://github.com/owner/repo/commit/abc1234")
    c2.write("")
    c2.write("")
    c2.button("Fetch", key="fetch", on_click=fetch_github)
    if st.session_state.gh_error:
        st.error(st.session_state.gh_error)
with right:
    st.subheader("2. Say what you changed")
    st.text_area("Description", key="narration", height=340, label_visibility="collapsed",
                 placeholder="Click here, hold your Flow key and describe the change...")
    st.caption("After talking, click outside the box (or press Ctrl+Enter) so the text registers.")

if st.button("Verify", type="primary", key="verify"):
    run_verification()

if st.session_state.result is not None:
    show_result(st.session_state.result, st.session_state.hunks)
    if TEACH_MODE:
        show_teach(st.session_state.result)
