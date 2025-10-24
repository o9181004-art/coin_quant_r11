import os, sys, logging
from pathlib import Path

def _project_root():
    p = Path(__file__).resolve()
    for _ in range(8):
        if (p/"pyproject.toml").exists() or (p/"src"/"coin_quant").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent

ROOT = _project_root()
sys.path.insert(0, str(ROOT/"src"))

os.environ.setdefault("UI_MODE", "classic")
os.environ.setdefault("COIN_QUANT_ROOT", str(ROOT))
os.environ.setdefault("MONITORING_BACKEND", "file")
os.environ.setdefault("HEALTH_DIR", str(ROOT/"shared_data"/"health"))

logging.basicConfig(level=logging.INFO)

target = ROOT / "app_old.py"
if not target.exists():
    raise SystemExit(f"[FATAL] app_old.py not found: {target}")

code = compile(target.read_text(encoding="utf-8"), str(target), "exec")
globals_dict = {
    "__name__": "__main__",
    "__file__": str(target),
    "Path": Path,
    "os": os,
    "sys": sys,
    "logging": logging
}
exec(code, globals_dict)
