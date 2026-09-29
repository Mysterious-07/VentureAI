"""VentureAI Diagnostic Utility (READ-ONLY). Run: python backend/scripts/diagnose.py"""
from __future__ import annotations
import importlib
import os
import sys
import traceback
from pathlib import Path

def _find_backend_dir():
    cwd = Path.cwd().resolve()
    if (cwd / "app" / "main.py").exists():
        return cwd
    if (cwd / "backend" / "app" / "main.py").exists():
        return cwd / "backend"
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "app" / "main.py").exists() and parent.name == "backend":
            return parent
    return None

BACKEND_DIR = _find_backend_dir()
if BACKEND_DIR is not None and str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv
    if BACKEND_DIR is not None:
        load_dotenv(BACKEND_DIR / ".env", override=False)
except Exception:
    pass

RESULTS = []
FAILURES = []

def record(section, label, passed):
    RESULTS.append((section, label, "PASS" if passed else "FAIL"))
    if not passed:
        FAILURES.append(f"{section}: {label}")
    return passed

def tag(passed):
    return "PASS" if passed else "FAIL"

print("========================================")
print("VENTUREAI DIAGNOSTIC REPORT")
print("========================================")
print()
print("Python:")
py_version = sys.version.replace("\n", " ")
print(f"  Python {sys.version.split()[0]} ({py_version[:120]})")
in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
venv_path = os.environ.get("VIRTUAL_ENV", "")
record("Python", f"Python {sys.version.split()[0]}", True)
if venv_path:
    record("Python", f"Venv active ({venv_path})", True)
    print(f"  [PASS] Virtual environment: {venv_path}")
elif in_venv:
    record("Python", f"Venv active ({sys.prefix})", True)
    print(f"  [PASS] Virtual environment: {sys.prefix}")
else:
    RESULTS.append(("Python", "Virtual environment (not detected)", "FAIL"))
    print("  [FAIL] Virtual environment not detected")
print()
print("Dependencies:")
PACKAGES = [
    ("fastapi", "FastAPI"),
    ("uvicorn", "Uvicorn"),
    ("sqlalchemy", "SQLAlchemy"),
    ("pydantic", "Pydantic"),
    ("pydantic_settings", "Pydantic Settings"),
    ("jose", "Python-JOSE"),
    ("passlib", "Passlib"),
    ("bcrypt", "Bcrypt"),
    ("multipart", "Python-Multipart"),
    ("dotenv", "Python-Dotenv"),
    ("alembic", "Alembic"),
    ("google.generativeai", "Gemini SDK"),
    ("langgraph", "LangGraph"),
    ("langchain_google_genai", "LangChain Google GenAI"),
    ("pptx", "python-pptx"),
    ("pytest", "Pytest"),
]
for mod_name, label in PACKAGES:
    try:
        importlib.import_module(mod_name)
        record("Dependencies", label, True)
        print(f"  [PASS] {label}")
    except Exception as e:
        record("Dependencies", f"{label} ({type(e).__name__})", False)
        print(f"  [FAIL] {label} ({type(e).__name__})")
print()
print("Environment:")
ENV_VARS = ["DATABASE_URL","JWT_SECRET_KEY","JWT_ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES","REFRESH_TOKEN_EXPIRE_DAYS",
    "COOKIE_SECURE","CORS_ORIGINS","GEMINI_API_KEY"]
try:
    from app.config import settings as _settings
    settings_obj = _settings
except Exception:
    settings_obj = None
    print("  [NOTE] app.config import failed; using os.environ only")
def _env_value(name):
    v = os.environ.get(name)
    if v is not None:
        return v
    if settings_obj is not None and hasattr(settings_obj, name):
        try:
            val = getattr(settings_obj, name)
            return "" if val is None else str(val)
        except Exception:
            return ""
    return ""
ENV_STATUS = {}
for name in ENV_VARS:
    val = _env_value(name)
    configured = bool(val and val.strip())
    ENV_STATUS[name] = configured
    record("Environment", f"{name} configured", configured)
    print(f"  [{tag(configured)}] {name} {'configured' if configured else 'MISSING'}")
print()
print("FastAPI:")
try:
    from app.main import app as fastapi_app
    ok = fastapi_app is not None and hasattr(fastapi_app, "routes")
    record("FastAPI", "Application import", ok)
    print(f"  [{tag(ok)}] Application import")
    if ok:
        print(f"         routes: {len(fastapi_app.routes)}")
except Exception as e:
    record("FastAPI", f"Application import ({type(e).__name__})", False)
    print(f"  [FAIL] Application import ({type(e).__name__})")
print()
print("Database:")
if not ENV_STATUS.get("DATABASE_URL", False):
    RESULTS.append(("Database","PostgreSQL (SKIPPED, no DATABASE_URL)","SKIPPED"))
    print("  [SKIPPED] PostgreSQL (DATABASE_URL not configured)")
else:
    try:
        from sqlalchemy import create_engine, text
        db_url = _env_value("DATABASE_URL")
        engine = create_engine(db_url, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        record("Database", "PostgreSQL connection", True)
        print("  [PASS] PostgreSQL connection")
    except Exception as e:
        record("Database", f"PostgreSQL ({type(e).__name__})", False)
        print(f"  [FAIL] PostgreSQL ({type(e).__name__}: {str(e)[:200]})")
print()
print("Gemini:")
if not ENV_STATUS.get("GEMINI_API_KEY", False):
    RESULTS.append(("Gemini","API request (SKIPPED, no key)","SKIPPED"))
    print("  [SKIPPED] Gemini API (GEMINI_API_KEY not configured)")
else:
    gem_model = "gemini-flash-latest"
    try:
        nm = importlib.import_module("app.idea_validation.graph.nodes")
        cands = getattr(nm, "MODEL_CANDIDATES", None)
        if cands:
            gem_model = cands[0]
    except Exception:
        pass
    print(f"         model: {gem_model}")
    try:
        import google.generativeai as genai
        genai.configure(api_key=_env_value("GEMINI_API_KEY"))
        m = genai.GenerativeModel(gem_model)
        r = m.generate_content("Reply with the word OK.")
        cand_ok = bool(getattr(r, "candidates", None))
        print(f"         candidate returned: {'YES' if cand_ok else 'NO'}")
        finish = "unknown"
        try:
            if cand_ok:
                finish = str(getattr(r.candidates[0], "finish_reason", "unknown"))
        except Exception:
            pass
        print(f"         finish reason: {finish}")
        has_text = False
        preview = ""
        try:
            for cand in (getattr(r, "candidates", None) or []):
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) if content else None
                for p in (parts or []):
                    t = getattr(p, "text", "")
                    if t and t.strip():
                        has_text = True
                        if not preview:
                            preview = t.strip()[:80]
                        break
                if has_text:
                    break
        except Exception:
            has_text = False
        print(f"         text part returned: {'YES' if has_text else 'NO'}")
        if has_text:
            print(f"         preview: {preview}")
            record("Gemini", "Gemini API request", True)
            print("  [PASS] Gemini API request")
        else:
            record("Gemini", f"API no text Part (finish={finish})", False)
            print(f"  [FAIL] Gemini API (no text Part; finish={finish})")
    except Exception as e:
        record("Gemini", f"API request ({type(e).__name__})", False)
        print(f"  [FAIL] Gemini API ({type(e).__name__}: {str(e)[:200]})")
print()
print("PPTX:")
try:
    from pptx import Presentation  # noqa: F401
    record("PPTX", "python-pptx", True)
    print("  [PASS] python-pptx")
except Exception as e:
    record("PPTX", f"python-pptx ({type(e).__name__})", False)
    print(f"  [FAIL] python-pptx ({type(e).__name__})")
print()
print("Application Modules:")
MODS = [("app","App package"),("app.config","Config"),("app.main","Main"),
    ("app.auth","Auth"),("app.idea_validation","Idea Validation"),
    ("app.bmc","BMC"),("app.business_plan","Business Plan"),
    ("app.pitch_deck","Pitch Deck"),("app.chat","Chat")]
for mod_name, label in MODS:
    try:
        importlib.import_module(mod_name)
        record("Application Modules", label, True)
        print(f"  [PASS] {label}")
    except Exception as e:
        record("Application Modules", f"{label} ({type(e).__name__})", False)
        print(f"  [FAIL] {label} ({type(e).__name__})")
print()
print("========================================")
print("FINAL STATUS")
print("========================================")
fails = [r for r in RESULTS if r[2] == "FAIL"]
skips = [r for r in RESULTS if r[2] == "SKIPPED"]
print(f"Passed: {sum(1 for r in RESULTS if r[2]=='PASS')}/{len(RESULTS)}")
if skips:
    print(f"Skipped: {len(skips)}")
if fails:
    print("Failures:")
    for s, lab, _ in fails:
        print(f"  - {s}: {lab}")
    print("READY FOR NEXT TEST: NO")
else:
    if skips:
        print("All executed checks passed; some live checks skipped.")
        print("READY FOR NEXT TEST: NO")
    else:
        print("All checks passed.")
        print("READY FOR NEXT TEST: YES")

