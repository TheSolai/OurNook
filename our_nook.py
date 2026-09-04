#!/usr/bin/env python3
"""
OurNook — Local AI Companion Hub
Entry point. Starts the FastAPI server in a background thread, opens the
pywebview window, and routes the JS frontend to the local server.

Usage: python3 our_nook.py
Bundled: pyinstaller our_nook.spec → OurNook.app / OurNook.exe

PyInstaller notes:
- In a frozen bundle, `sys._MEIPASS` is the temp dir where bundled assets live.
- In dev mode (running from source), assets live next to this file in `dist/` and `src-ui/public/`.
- We use `bundle_path()` to resolve both.
"""
import sys, os, time, subprocess, signal, traceback, platform
from datetime import datetime
from pathlib import Path


# ── Bundle path resolution (works for both dev and PyInstaller) ─────

def bundle_path(*parts: str) -> Path:
    """Resolve a path inside the bundle.

    - In dev (running as .py):    <project>/<parts>
    - Frozen (PyInstaller):       sys._MEIPASS/<parts>
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / Path(*parts)
    return Path(__file__).resolve().parent / Path(*parts)


def user_data_path(*parts: str) -> Path:
    """Resolve a writable path in the user's data dir (never bundled)."""
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        base = home / "Library" / "Application Support" / "OurNook"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))) / "OurNook"
    else:
        base = home / ".local" / "share" / "OurNook"
    p = base / Path(*parts) if parts else base
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── Venv activation (dev only — frozen bundles don't need this) ───

if not getattr(sys, "frozen", False):
    VENV_PYTHON = os.path.expanduser("~/.nook-venv/bin/python3")
    if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
        os.execv(VENV_PYTHON, [VENV_PYTHON, __file__])
        sys.exit(1)


# ── Paths ─────────────────────────────────────────────────────────

API_PORT = 18765
API_URL = f"http://127.0.0.1:{API_PORT}"


# ── Crash log guard ────────────────────────────────────────────────
# If the app ever crashes (uncaught exception in the main thread, or a fatal
# signal like SIGSEGV), dump a full traceback to disk so the user has something
# to send instead of guessing.

def _crash_log_path() -> str:
    """Cross-platform: ~/Library/Application Support/OurNook/ on macOS, etc."""
    p = user_data_path("crash.log")
    return str(p)


def _dump_crash(exc_type, exc_value, exc_tb):
    path = _crash_log_path()
    try:
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n\n{'=' * 70}\n")
            f.write(f"OurNook crash — {datetime.now().isoformat()}\n")
            f.write(f"Python {sys.version.split()[0]}, {platform.system()} {platform.machine()}\n")
            f.write(f"PID {os.getpid()}\n")
            f.write(f"{'=' * 70}\n")
            f.write(tb_text)
        print(f"\n[OurNook] crash logged to {path}\n", file=sys.stderr)
    except Exception as log_err:
        print(f"[OurNook] could not write crash log: {log_err}", file=sys.stderr)


def _excepthook(exc_type, exc_value, exc_tb):
    _dump_crash(exc_type, exc_value, exc_tb)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook


def _signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    try:
        path = _crash_log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n\n{'=' * 70}\n")
            f.write(f"OurNook fatal signal: {sig_name} ({signum}) — {datetime.now().isoformat()}\n")
            f.write(f"Python {sys.version.split()[0]}, {platform.system()} {platform.machine()}\n")
            f.write(f"PID {os.getpid()}\n")
            f.write(f"{'=' * 70}\n")
            if frame is not None:
                f.write("".join(traceback.format_stack(frame)))
        print(f"\n[OurNook] signal {sig_name} logged to {path}\n", file=sys.stderr)
    except Exception:
        pass
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


for sig_num in (signal.SIGTERM, signal.SIGABRT):
    try:
        signal.signal(sig_num, _signal_handler)
    except (ValueError, OSError):
        pass


# ── Start FastAPI server in a background thread (no subprocess) ──
# Why in-process: PyInstaller bundles one Python executable, so spawning a
# subprocess to run `python -m uvicorn` would either fail (no python on PATH)
# or require shipping a second Python binary. Running uvicorn in a daemon
# thread is simpler, faster, and the natural fit for a single-window app.

# Patch the data dir before importing api modules — so they use the right
# platform-correct path (not the bundle's temp _MEIPASS).
os.environ.setdefault("OURNOOK_DATA_DIR", str(user_data_path()))

import threading
import uvicorn
from api import server as api_server

# Configure uvicorn to listen only on localhost (security: no LAN exposure)
config = uvicorn.Config(
    api_server.app,
    host="127.0.0.1",
    port=API_PORT,
    log_level="warning",
    access_log=False,
    # Important: don't write access logs to stderr — they pollute the UI
    log_config={
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
        "handlers": {"default": {"class": "logging.NullHandler"}},
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "WARNING", "propagate": False},
            "uvicorn.error": {"level": "WARNING"},
            "uvicorn.access": {"level": "WARNING"},
        },
    },
)


def _run_server():
    """Run uvicorn in a thread. Silently exits when window closes."""
    try:
        uvicorn.Server(config).run()
    except Exception as e:
        print(f"[OurNook] uvicorn crashed: {e}", file=sys.stderr)
        _dump_crash(type(e), e, e.__traceback__)


# Wait for the port to be free (in case a previous instance is still bound)
def _wait_for_port_free(timeout: float = 2.0) -> bool:
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", API_PORT))
                return True
        except OSError:
            return False  # someone else is on the port — we'll just fail below
    return False


if not _wait_for_port_free():
    print(f"[OurNook] WARNING: port {API_PORT} appears to be in use")

_server_thread = threading.Thread(target=_run_server, name="ournook-api", daemon=True)
_server_thread.start()

# Wait for the server to be ready
import httpx
for _ in range(50):  # up to 5s
    try:
        r = httpx.get(f"{API_URL}/api/ping", timeout=0.5)
        if r.status_code == 200:
            print("[OurNook] API server ready (in-process)")
            break
    except Exception:
        time.sleep(0.1)
else:
    print("[OurNook] WARNING: API server didn't respond within 5s")


# ── pywebview window ───────────────────────────────────────────────

# pywebview on macOS / Windows uses the native WebView. The window must be
# created on the main thread. The JS frontend in the window loads API_URL
# (which is served by the in-process uvicorn above).

import webview

# Resolve the bundled index.html (or the dev index.html)
INDEX_HTML = bundle_path("dist", "index.html")
if not INDEX_HTML.exists():
    # Dev fallback: build first
    print(f"[OurNook] WARNING: {INDEX_HTML} not found. Run `pnpm build` first.")
    INDEX_HTML = bundle_path("index.html")  # in case we copy it to root

window = webview.create_window(
    title="OurNook",
    url=API_URL,
    width=1100,
    height=720,
    min_size=(600, 480),
    resizable=True,
    js_api=None,
    background_color="#0e0d10",  # matches the v0.7 "Dusk" palette — no white flash
)


# ── Start window ──────────────────────────────────────────────────

def on_closed():
    print("[OurNook] Window closed — shutting down")
    try:
        with open(_crash_log_path(), "a", encoding="utf-8") as f:
            f.write(f"\n{datetime.now().isoformat()}  clean shutdown (window closed)\n")
    except Exception:
        pass


# ── Native menu (File / Edit / View / Window / Help) ──────────────
# Only build native menus on platforms that support them (macOS, Windows)
# — Linux GTK3 has them too but our target is Mac + Windows.

def _js_eval(expr: str):
    """Evaluate a JS expression in the main window. Safe wrapper."""
    try:
        return window.evaluate_js(expr)
    except Exception as e:
        print(f"[OurNook] menu js eval error: {e}")
        return None


def _switch_tab(tab: str):
    _js_eval(f"useUIStore.getState().setTab('{tab}')")


def _new_companion():
    _js_eval("useUIStore.getState().openWizard()")


def _edit_active():
    _js_eval("useUIStore.getState().openEditor(useCompanionStore.getState().activeId)")


def _open_cards():
    _switch_tab("cards")


def _open_settings():
    _switch_tab("settings")


def _open_backup():
    _js_eval("useUIStore.getState().openBackup()")


def _import_card():
    _switch_tab("cards")
    _js_eval("window.__cardioWantImport = true; window.dispatchEvent(new CustomEvent('cardio-import'))")


def _export_active():
    # Trigger the export via the frontend — it fetches the URL (which returns a
    # Content-Disposition: attachment response) and saves it to disk through
    # the browser's download flow. Previously this opened a hidden pywebview
    # window just to receive the download, which was a heavy hack for what is
    # a one-line JS fetch.
    _js_eval("window.__ournookTriggerExport && window.__ournookTriggerExport()")


def _reload():
    _js_eval("window.location.reload()")


def _open_models_page():
    _js_eval("window.open('https://ollama.com/library', '_blank')")


def _open_docs():
    _js_eval("window.open('https://github.com/TheSolAI/OurNook', '_blank')")


def _show_about():
    _js_eval("alert('OurNook v0.1.0\\n\\nLocal-first AI companion hub.\\n100% local. 0% telemetry. 0% subscription.')")


from webview import Menu as PyMenu
from webview.menu import MenuAction as PyMenuAction, MenuSeparator as PySeparator

MENU = [
    PyMenu("File", [
        PyMenuAction("New Companion…", _new_companion),
        PyMenuAction("Edit Active Companion…", _edit_active),
        PySeparator(),
        PyMenuAction("Import Card…", _import_card),
        PyMenuAction("Export Active Card…", _export_active),
        PySeparator(),
        PyMenuAction("Open ollama.com Library", _open_models_page),
        PySeparator(),
        PyMenuAction("Backup & Restore…", _open_backup),
        PyMenuAction("Reload", _reload),
    ]),
    PyMenu("Edit", [
        PyMenuAction("Undo", lambda: _js_eval("document.execCommand('undo')")),
        PyMenuAction("Redo", lambda: _js_eval("document.execCommand('redo')")),
        PySeparator(),
        PyMenuAction("Cut", lambda: _js_eval("document.execCommand('cut')")),
        PyMenuAction("Copy", lambda: _js_eval("document.execCommand('copy')")),
        PyMenuAction("Paste", lambda: _js_eval("document.execCommand('paste')")),
        PyMenuAction("Select All", lambda: _js_eval("document.execCommand('selectAll')")),
    ]),
    PyMenu("View", [
        PyMenuAction("Chat", lambda: _switch_tab("chat")),
        PyMenuAction("Memory", lambda: _switch_tab("memory")),
        PyMenuAction("Art", lambda: _switch_tab("art")),
        PyMenuAction("Models", lambda: _switch_tab("models")),
        PyMenuAction("Cards (Import/Export)", lambda: _switch_tab("cards")),
        PyMenuAction("Settings", lambda: _switch_tab("settings")),
    ]),
    PyMenu("Window", [
        PyMenuAction("Minimize", lambda: _js_eval("window.minimize ? window.minimize() : null")),
    ]),
    PyMenu("Help", [
        PyMenuAction("Models Marketplace", _open_models_page),
        PyMenuAction("Documentation", _open_docs),
        PySeparator(),
        PyMenuAction("About OurNook", _show_about),
    ]),
]

try:
    print(f"[OurNook] Menu defined with {len(MENU)} top-level items: {[m.title for m in MENU]}")
except Exception as e:
    print(f"[OurNook] Menu setup failed: {e}")

webview.start(on_closed, menu=MENU)
