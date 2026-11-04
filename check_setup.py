"""Run this first if something fails.  Usage: python check_setup.py [--call]   (for a full check use: python preflight.py)"""
import importlib
import os
import sys

print("Python in use:", sys.executable)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    sys.exit("MISSING python-dotenv. Fix: python -m pip install -r requirements.txt")
from root import llm

prov = llm.provider()
bad = []
for mod in ["fastapi", "uvicorn", "pydantic", "unidiff", prov]:
    try:
        importlib.import_module(mod)
        print(f"  ok       {mod}")
    except ImportError:
        print(f"  MISSING  {mod}")
        bad.append(mod)
for mod in ["streamlit", "pandas"]:
    try:
        importlib.import_module(mod)
        print(f"  ok       {mod} (only for the Streamlit fallback)")
    except ImportError:
        print(f"  absent   {mod} (only needed for the Streamlit fallback)")
if bad:
    sys.exit("\nFix: activate your venv, then: python -m pip install -r requirements.txt")
for var in ["GROQ_API_KEY" if prov == "groq" else "ANTHROPIC_API_KEY", "MODEL_NAME"]:
    print(f"  {'set    ' if os.environ.get(var) else 'NOT SET'}  {var}")
if "--call" in sys.argv:
    print("Model replied:", llm._call("Reply with the single word OK.", "ping")[:40])
