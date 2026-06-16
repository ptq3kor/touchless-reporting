"""Single entry point to run the entire Touchless Reporting application.

Starts the FastAPI backend (uvicorn on :8000) and the Vite frontend
(dev server on :5173) together, opens the browser, and shuts both down
cleanly on Ctrl+C.

Usage:
    python app.py                 # run backend + frontend
    python app.py --backend-only  # only the API
    python app.py --frontend-only # only the UI
    python app.py --no-browser    # don't auto-open the browser
    python app.py --skip-install  # don't auto-install dependencies
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
BACKEND_REQS = ROOT / "backend" / "requirements.txt"
DB_FILE = ROOT / "touchless_reporting.db"
GENERATE_DB = ROOT / "generate_db.py"
VENV_DIR = ROOT / ".venv"

BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:5173"

IS_WINDOWS = os.name == "nt"

# On Windows, launch children in their own process group so we can deliver
# CTRL_BREAK_EVENT to them on shutdown without killing this launcher.
POPEN_KWARGS = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WINDOWS else {}
)


def log(msg: str) -> None:
    print(f"[app] {msg}", flush=True)


def venv_python() -> Path:
    """Path to the Python interpreter inside the uv-managed venv."""
    if IS_WINDOWS:
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def find_npm() -> str | None:
    """Locate the npm executable (npm.cmd on Windows)."""
    for candidate in ("npm.cmd", "npm") if IS_WINDOWS else ("npm",):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def find_uv() -> str | None:
    return shutil.which("uv.exe") or shutil.which("uv")


def ensure_database(python: str) -> None:
    if DB_FILE.exists():
        return
    log("Database not found. Generating touchless_reporting.db ...")
    subprocess.run([python, str(GENERATE_DB)], cwd=ROOT, check=True)


def ensure_venv(skip_install: bool) -> str:
    """Create the venv with uv (if needed) and install backend deps into it.

    Returns the path to the venv's Python interpreter.
    """
    uv = find_uv()
    if uv is None:
        log("ERROR: uv not found on PATH. Install it from https://docs.astral.sh/uv/")
        raise SystemExit(1)

    if not venv_python().exists():
        log("Creating virtual environment with uv (.venv) ...")
        subprocess.run([uv, "venv", str(VENV_DIR)], cwd=ROOT, check=True)

    python = str(venv_python())

    if not skip_install:
        log("Installing backend dependencies with uv ...")
        subprocess.run(
            [uv, "pip", "install", "--python", python, "-r", str(BACKEND_REQS)],
            cwd=ROOT,
            check=True,
        )

    return python


def ensure_frontend_deps(npm: str, skip_install: bool) -> None:
    if skip_install:
        return
    if (FRONTEND_DIR / "node_modules").exists():
        return
    log("Installing frontend dependencies (npm install) ...")
    subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True)


def start_backend(python: str) -> subprocess.Popen:
    log(f"Starting backend  -> {BACKEND_URL}")
    return subprocess.Popen(
        [
            python,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
        ],
        cwd=ROOT,
        **POPEN_KWARGS,
    )


def start_frontend(npm: str) -> subprocess.Popen:
    log(f"Starting frontend -> {FRONTEND_URL}")
    return subprocess.Popen([npm, "run", "dev"], cwd=FRONTEND_DIR, **POPEN_KWARGS)


def open_browser_when_ready(url: str) -> None:
    """Open the browser shortly after launch, in a background thread."""

    def _open() -> None:
        time.sleep(3)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def terminate(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            try:
                if IS_WINDOWS:
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    p.terminate()
            except Exception:
                p.terminate()
    # Give them a moment, then force-kill any stragglers.
    deadline = time.time() + 5
    for p in procs:
        remaining = max(0, deadline - time.time())
        try:
            p.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Touchless Reporting app.")
    parser.add_argument("--backend-only", action="store_true", help="Run only the API.")
    parser.add_argument("--frontend-only", action="store_true", help="Run only the UI.")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser.")
    parser.add_argument(
        "--skip-install", action="store_true", help="Skip dependency installation."
    )
    args = parser.parse_args()

    run_backend = not args.frontend_only
    run_frontend = not args.backend_only

    npm = find_npm()
    if run_frontend and npm is None:
        log("ERROR: npm not found on PATH. Install Node.js or use --backend-only.")
        return 1

    procs: list[subprocess.Popen] = []
    try:
        if run_backend:
            python = ensure_venv(args.skip_install)
            ensure_database(python)
            procs.append(start_backend(python))

        if run_frontend:
            ensure_frontend_deps(npm, args.skip_install)
            procs.append(start_frontend(npm))

        if not args.no_browser:
            open_browser_when_ready(FRONTEND_URL if run_frontend else f"{BACKEND_URL}/docs")

        log("Application running. Press Ctrl+C to stop.")

        # Wait until any child exits (or the user interrupts).
        while True:
            for p in procs:
                code = p.poll()
                if code is not None:
                    log(f"A process exited with code {code}; shutting down.")
                    return code or 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("Shutting down ...")
        return 0
    finally:
        terminate(procs)


if __name__ == "__main__":
    raise SystemExit(main())
