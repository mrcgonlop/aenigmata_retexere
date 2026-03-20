"""Start the aenigmata development stack.

Launches:
  • FastAPI backend  (uvicorn)  on http://localhost:8000
  • Vite frontend dev server    on http://localhost:5173

Usage:
    # With the aenigmata conda environment active:
    python scripts/start.py

    # Or without activating the environment:
    conda run -n aenigmata python scripts/start.py

Press Ctrl+C to stop both servers.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "src" / "frontend"

# ── Locate executables ────────────────────────────────────────────────────────

def _find_exe(name: str) -> str:
    """Find an executable adjacent to the current Python interpreter, falling
    back to searching PATH.  Handles Windows (.exe / .cmd) automatically."""
    scripts_dir = Path(sys.executable).parent       # conda env Scripts/ or bin/
    for candidate_name in ([f"{name}.exe", name] if sys.platform == "win32" else [name]):
        candidate = scripts_dir / candidate_name
        if candidate.exists():
            return str(candidate)
    return name     # hope it's on PATH


def _npm() -> str:
    """Return the correct npm executable name for this platform."""
    return "npm.cmd" if sys.platform == "win32" else "npm"


# ── Launch ────────────────────────────────────────────────────────────────────

def main() -> None:
    uvicorn = _find_exe("uvicorn")
    npm     = _npm()

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    print("╔══════════════════════════════════════════╗")
    print("║          aenigmata — dev stack           ║")
    print("╠══════════════════════════════════════════╣")
    print("║  Backend:   http://localhost:8000        ║")
    print("║  Frontend:  http://localhost:5173        ║")
    print("║  API docs:  http://localhost:8000/docs   ║")
    print("╚══════════════════════════════════════════╝")
    print()

    # ── Start uvicorn ─────────────────────────────────────────────────────────
    api_proc = subprocess.Popen(
        [uvicorn, "src.api.main:app", "--reload", "--port", "8000"],
        cwd=str(ROOT),
        env=env,
    )

    # ── Start Vite ────────────────────────────────────────────────────────────
    frontend_proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(FRONTEND_DIR),
        env=env,
    )

    print("Both servers starting… opening browser in 3 seconds.")
    print("Press Ctrl+C to stop.\n")

    time.sleep(3.0)
    webbrowser.open("http://localhost:5173")

    # ── Wait until killed ─────────────────────────────────────────────────────
    try:
        api_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down…")
    finally:
        for proc in (api_proc, frontend_proc):
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        print("Done.")


if __name__ == "__main__":
    main()
