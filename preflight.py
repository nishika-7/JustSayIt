"""Checks before you submit.
   python preflight.py                         checks on this machine
   python preflight.py --url https://your-app.onrender.com [--gh https://github.com/o/r/pull/1] [--no-verify]
Exit code 1 if anything FAILED. WARN means look at it. --url sends one real verification (2 model calls) unless --no-verify."""
import argparse
import importlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


class Report:
    def __init__(self):
        self.rows = []

    def add(self, level, name, detail=""):
        self.rows.append((level, name, detail))
        print(f"[{level:4}] {name}" + (f"  - {detail}" if detail else ""))

    def ok(self, n, d=""): self.add("PASS", n, d)
    def warn(self, n, d=""): self.add("WARN", n, d)
    def fail(self, n, d=""): self.add("FAIL", n, d)
    def check(self, cond, name, detail_ok="", detail_bad=""): (self.ok if cond else self.fail)(name, detail_ok if cond else detail_bad)
    def failed(self): return any(r[0] == "FAIL" for r in self.rows)


def local_checks(rep: Report, root: Path = ROOT) -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
    except ImportError:
        rep.fail("python-dotenv installed", "pip install -r requirements.txt")
        return
    from root import llm, versions
    prov = llm.provider()
    key = "GROQ_API_KEY" if prov == "groq" else "ANTHROPIC_API_KEY"
    rep.ok("model provider", prov)
    rep.check(bool(os.environ.get(key)), f"{key} is set", "", "put it in .env")
    rep.check(bool(os.environ.get("MODEL_NAME")), "MODEL_NAME is set", os.environ.get("MODEL_NAME", ""), "put it in .env")
    try:
        importlib.import_module(prov)
        rep.ok(f"package '{prov}' installed")
    except ImportError:
        rep.fail(f"package '{prov}' installed", "pip install -r requirements.txt")
    active = versions.active(root / "prompts")
    missing = [f"{v}.md" for v in active.values() if not (root / "prompts" / f"{v}.md").exists()]
    rep.check(not missing, "active prompt files exist", " / ".join(active.values()), "missing: " + ", ".join(missing))
    rep.check((root / "data" / "examples" / "sample.diff").exists() and (root / "data" / "examples" / "examples.json").exists(),
              "example data present", "", "data/examples is incomplete")
    runs = sorted((root / "data" / "runs").glob("round*.json"))
    scores = []
    for p in runs:
        d = json.loads(p.read_text(encoding="utf-8"))
        scores.append(f"{d['label']}={round((d['summary']['overall_accuracy'] or 0) * 100)}%")
    if len(runs) >= 2:
        rep.ok(f"{len(runs)} eval rounds saved", ", ".join(scores))
    else:
        rep.warn("fewer than 2 eval rounds saved", "the Results tab needs a before and after")
    if runs:
        last = json.loads(runs[-1].read_text(encoding="utf-8"))
        used = next((r.get("verifier") for r in last["results"] if r.get("verifier")), None)
        if used and used != active["verifier"]:
            rep.warn("latest scored round used a different verifier prompt than the active one", f"scored {used}, active {active['verifier']}")
        else:
            rep.ok("latest round matches the active verifier prompt")
    if os.environ.get("TEACH_MODE") == "1":
        rep.warn("TEACH_MODE=1 here", "fine locally. Never set it on the deployed app.")
    try:
        tracked = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    except Exception:
        rep.warn("git checks skipped", "not a git repo, or git is not installed")
        return
    bad = [f for f in tracked if f == ".env" or f.endswith("secrets.toml") or f.startswith(("data/commits/", "data/cases/variants/"))
           or f in ("data/critiques.jsonl", "data/runs/log.jsonl")]
    rep.check(not bad, "no secrets or raw code tracked by git", "", "tracked: " + ", ".join(bad[:5]))
    rep.check(any(f.startswith("data/runs/round") for f in tracked), "eval round files are committed",
              "", "not committed: the live Results tab will be empty")
    rep.check("prompts/active.json" in tracked, "prompts/active.json is committed", "", "the live app would use the wrong prompts")


def urllib_http(method, url, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "User-Agent": "preflight"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def live_checks(rep: Report, base: str, http=urllib_http, verify=True, gh=None, wait=90) -> None:
    base = base.rstrip("/")
    start = time.time()
    while True:
        status, _ = http("GET", base + "/healthz", None, 30)
        if status == 200 or time.time() - start > wait:
            break
        time.sleep(5)
    rep.check(status == 200, "server is up", f"answered after {time.time() - start:.0f}s", f"/healthz returned {status}")
    if status != 200:
        return
    s, body = http("GET", base + "/", None, 30)
    rep.check(s == 200 and "Say what you changed" in body, "home page loads", "", f"status {s}")
    s, body = http("GET", base + "/api/config", None, 30)
    cfg = json.loads(body) if s == 200 else {}
    rep.check(s == 200 and cfg.get("teach_mode") is False, "public mode (TEACH_MODE is off)", "", "TEACH_MODE is ON: remove it from the host's settings")
    s, _ = http("GET", base + "/api/improve", None, 30)
    rep.check(s == 404, "owner endpoints are hidden", "", f"/api/improve returned {s}")
    s, body = http("GET", base + "/api/examples", None, 30)
    ex = json.loads(body) if s == 200 else {}
    rep.check(bool(ex.get("examples")), "examples load", "", f"status {s}")
    s, body = http("GET", base + "/api/rounds", None, 30)
    rounds = json.loads(body) if s == 200 else []
    (rep.ok if len(rounds) >= 2 else rep.warn)(f"{len(rounds)} eval rounds on the live Results tab",
                                              ", ".join(f"{r['label']}={round((r['overall'] or 0) * 100)}%" for r in rounds))
    if verify and ex.get("examples"):
        t = time.time()
        s, body = http("POST", base + "/api/verify", {"narration": ex["examples"][0]["narration"], "diff": ex["diff"]}, 120)
        if s == 200:
            rows = json.loads(body).get("rows", [])
            rep.check(bool(rows), "real verification works end to end", f"{len(rows)} claims in {time.time() - t:.0f}s", "no claims returned")
        elif s in (429, 503):
            rep.warn("verification was refused", f"{s}: {json.loads(body).get('detail', body)[:120]}")
        else:
            rep.fail("real verification works end to end", f"status {s}: {body[:160]}")
    if gh:
        s, body = http("POST", base + "/api/github", {"url": gh}, 60)
        rep.check(s == 200 and bool(json.loads(body).get("diff")), f"GitHub link fetch: {gh}", "", f"status {s}: {body[:140]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--gh", help="a public GitHub commit, pull request or compare link to test through the live app")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args(argv)
    rep = Report()
    if args.url:
        print(f"== Live checks: {args.url}")
        live_checks(rep, args.url, verify=not args.no_verify, gh=args.gh)
    else:
        print("== Project checks")
        local_checks(rep)
    n = {k: sum(r[0] == k for r in rep.rows) for k in ("PASS", "WARN", "FAIL")}
    print(f"\n{n['PASS']} passed, {n['WARN']} warnings, {n['FAIL']} failed")
    return 1 if rep.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
