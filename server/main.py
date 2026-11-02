import json
import os
import traceback
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from root import llm, versions
from root.diff_parser import parse_diff
from root.github import FetchError, fetch_github_diff
from root.guards import check_inputs, max_diff_chars
from root.store import add_critique, data_dir, load_critiques, log_run, run_evidence
from root.verifier import load_prompt, verify
from improve import loop

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "data" / "examples"


class VerifyIn(BaseModel):
    narration: str
    diff: str


class GithubIn(BaseModel):
    url: str


class CritiqueIn(BaseModel):
    run_id: str
    claim_id: str
    claim: str
    given_label: str
    correct_label: str
    stage: str
    critique: str = ""
    verifier_version: str = ""
    splitter_version: str = ""


class AcceptIn(BaseModel):
    stage: str
    rules: list[str]


def payload(result, hunks, run_id: str) -> dict:
    by_id = {v.claim_id: v for v in result.verdicts}
    hb = {h.id: h for h in hunks}
    rows = []
    for c in result.claims:
        v = by_id.get(c.id)
        rows.append({
            "id": c.id, "text": c.text, "label": v.label if v else "unverified", "reason": v.reason if v else "",
            "evidence": [{"id": i, "file": hb[i].file} for i in (v.evidence_hunk_ids if v else []) if i in hb],
        })
    n = Counter(v.label for v in result.verdicts)
    return {
        "rows": rows, "run_id": run_id, "warnings": result.warnings,
        "counts": {k: n[k] for k in ("supported", "unsupported", "contradicted")},
        "undeclared": [{"id": i, "file": hb[i].file, "header": hb[i].header, "text": hb[i].text}
                       for i in result.undeclared_hunk_ids if i in hb],
        "versions": {"splitter": result.splitter_version, "verifier": result.verifier_version},
    }


def create_app() -> FastAPI:
    teach = os.environ.get("TEACH_MODE") == "1"   # owner mode: never enable on the public app
    max_ip = int(os.environ.get("MAX_RUNS_PER_IP", "8"))
    max_global = int(os.environ.get("MAX_RUNS_GLOBAL", "300"))
    used = {"global": 0, "ip": defaultdict(int)}   # in memory: resets when the server restarts
    app = FastAPI(title="Say what you changed")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    @app.get("/api/config")
    def config():
        return {"teach_mode": teach, "max_diff_chars": max_diff_chars()}

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/examples")
    def examples():
        return {"diff": (EX / "sample.diff").read_text(encoding="utf-8"),
                "examples": json.loads((EX / "examples.json").read_text(encoding="utf-8"))}

    @app.post("/api/github")
    def github(body: GithubIn):
        try:
            return {"diff": fetch_github_diff(body.url)}
        except FetchError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/verify")
    def verify_endpoint(body: VerifyIn, request: Request):
        problem = check_inputs(body.diff, body.narration)
        if problem:
            raise HTTPException(400, problem)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        if used["ip"][ip] >= max_ip:
            raise HTTPException(429, "You've used all your checks for now. Please try again later.")
        if used["global"] >= max_global:
            raise HTTPException(429, "The demo has hit its usage limit for now. Please try again later.")
        try:
            result = verify(body.narration, body.diff)
        except Exception as e:
            traceback.print_exc()
            if llm.is_busy(e):
                raise HTTPException(503, "The AI service is busy right now. Please try again in a few seconds.")
            detail = f" ({type(e).__name__}: {e})" if os.environ.get("SHOW_ERRORS") == "1" else f" ({type(e).__name__})"
            raise HTTPException(500, "Something went wrong while checking. Please try again in a moment." + detail)
        used["ip"][ip] += 1
        used["global"] += 1
        run_id = log_run(body.narration, body.diff, result) if teach else ""
        return payload(result, parse_diff(body.diff), run_id)

    @app.get("/api/rounds")
    def rounds():
        out = []
        for p in sorted((data_dir() / "runs").glob("round*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            s = d["summary"]
            out.append({"label": d["label"], "overall": s["overall_accuracy"], "per_kind": s["per_kind"],
                        "detection": s["problem_detection"], "spoken_words": d.get("spoken_words"), "by_split": s["by_split"], "n": s["n"],
                        "verifier": next((r["verifier"] for r in d["results"] if r.get("verifier")), "")})
        return out

    if teach:
        @app.post("/api/critique")
        def critique(body: CritiqueIn):
            add_critique(body.run_id, body.claim_id, body.claim, body.given_label, body.correct_label,
                         body.stage, body.critique.strip(), body.verifier_version, body.splitter_version)
            return {"ok": True}

        @app.get("/api/improve")
        def improve_state():
            cs = load_critiques()
            return {"critiques": len(cs), "wrong": sum(not c["was_right"] for c in cs),
                    "words": sum(len(c["critique"].split()) for c in cs),
                    "versions": versions.list_versions(), "active": versions.active()}

        @app.post("/api/improve/propose")
        def propose():
            cs = [{**c, "evidence": run_evidence(c["run_id"], c["claim_id"])} for c in load_critiques() if not c["was_right"]]
            if not cs:
                raise HTTPException(400, "Nothing to learn from yet. In a Teach form, pick the label it SHOULD have said (different from the current one) and save.")
            try:
                prompts = {k: load_prompt(v) for k, v in versions.active().items()}
                modes = loop.analyze(cs, prompts)
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(500, f"Could not analyze the critiques ({type(e).__name__}: {e})")
            return {"modes": [{**m.model_dump(), "count": len(m.critique_ids)} for m in modes]}

        @app.post("/api/improve/accept")
        def accept(body: AcceptIn):
            if body.stage not in loop.STAGE_KEY:
                raise HTTPException(400, "Unknown stage.")
            try:
                new = loop.accept_rules(body.stage, body.rules)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"new_version": new, "active": versions.active()}

    return app


app = create_app()
