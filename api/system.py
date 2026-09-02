"""
System-level operations for OurNook: Ollama detection, launch, and model pull.

This is the "hold your hand" module — it lets the UI detect what's installed,
launch the Ollama app, and run `ollama pull` as a tracked subprocess with
progress reporting.
"""
import os
import re
import sys
import json
import shutil
import asyncio
import platform
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional
from . import ollama as ollama_mod


# ── System detection ─────────────────────────────────────────────

def _ollama_cli_path() -> Optional[str]:
    """Locate the ollama CLI on this system."""
    return shutil.which("ollama")


def _ollama_app_path() -> Optional[str]:
    """Locate the Ollama desktop app (for launching it)."""
    system = platform.system()
    if system == "Darwin":
        candidate = Path("/Applications/Ollama.app")
        if candidate.exists():
            return str(candidate)
        # Check homebrew install
        home = Path.home()
        for c in [home / "Applications" / "Ollama.app"]:
            if c.exists():
                return str(c)
    elif system == "Windows":
        # Check well-known install locations
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "Ollama.exe",
            Path("C:/Program Files/Ollama/Ollama.exe"),
            Path("C:/Program Files (x86)/Ollama/Ollama.exe"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
    return None


def _ollama_version() -> Optional[str]:
    """Run `ollama --version` and return the version string."""
    p = _ollama_cli_path()
    if not p:
        return None
    try:
        r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
        # Output looks like: "ollama version is 0.33.1"
        out = (r.stdout or r.stderr or "").strip()
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        return m.group(1) if m else out or None
    except Exception:
        return None


def get_system_status() -> dict:
    """Full system status — used by the Models onboarding UI.

    Returns:
        {
          "ollama_installed": bool,   # ollama CLI on PATH OR app present
          "ollama_running": bool,     # API responding on localhost:11434
          "ollama_version": str|None, # "0.33.1" or None
          "ollama_path": str|None,    # path to CLI binary
          "ollama_app_path": str|None, # path to desktop app (for launching)
          "platform": "darwin" | "windows" | "linux",
          "models_total": int,
          "models_installed": [name, ...],
          "has_chat_model": bool,       # any model that can be used for chat
          "has_embed_model": bool,      # nomic-embed-text / similar
          "has_image_model": bool,      # x/z-image-turbo / x/flux2-klein / etc.
          "setup_complete": bool,       # ready to chat
        }
    """
    cli = _ollama_cli_path()
    app = _ollama_app_path()

    # Health check
    health = ollama_mod.check_ollama()
    running = bool(health.get("healthy"))

    # Model inventory
    installed_names: list[str] = []
    if running:
        try:
            installed_names = [m["name"] for m in ollama_mod.list_models()]
        except Exception:
            pass

    chat_keywords = ("llama", "qwen", "mistral", "phi", "gemma", "deepseek", "dolphin",
                     "falcon", "command", "vicuna", "wizard", "orca", "openchat", "gpt-oss",
                     "functiongemma", "muse", "mero", "qwen3.5", "qwen2.5", "qwen36fable",
                     "glm", "hf.co")
    embed_keywords = ("embed", "nomic", "mxbai", "bge", "e5")
    image_keywords = ("z-image", "flux", "sdxl", "dalle", "playground")

    has_chat = any(any(k in n for k in chat_keywords) and not any(ek in n for ek in embed_keywords + image_keywords)
                   for n in installed_names)
    has_embed = any(any(k in n for k in embed_keywords) for n in installed_names)
    has_image = any(any(k in n for k in image_keywords) for n in installed_names)

    return {
        "ollama_installed": bool(cli or app),
        "ollama_running": running,
        "ollama_version": _ollama_version(),
        "ollama_path": cli,
        "ollama_app_path": app,
        "platform": {"Darwin": "darwin", "Windows": "windows", "Linux": "linux"}.get(platform.system(), "linux"),
        "models_total": len(installed_names),
        "models_installed": installed_names,
        "has_chat_model": has_chat,
        "has_embed_model": has_embed,
        "has_image_model": has_image,
        "setup_complete": running and has_chat,
    }


def launch_ollama_app() -> dict:
    """Open the Ollama desktop app (which starts the server in the background).

    On macOS:  `open -a Ollama`
    On Windows: launch Ollama.exe
    On Linux: returns an error (Linux users usually run `ollama serve` themselves)
    """
    app = _ollama_app_path()
    system = platform.system()
    try:
        if system == "Darwin":
            if not app:
                return {"ok": False, "error": "Ollama.app not found in /Applications. Install from ollama.com/download."}
            subprocess.Popen(["open", "-a", app])
            return {"ok": True, "method": "open -a Ollama"}
        elif system == "Windows":
            if not app:
                return {"ok": False, "error": "Ollama.exe not found. Install from ollama.com/download."}
            # Windows: use os.startfile or subprocess
            os.startfile(app)  # type: ignore[attr-defined]
            return {"ok": True, "method": "os.startfile"}
        else:
            return {"ok": False, "error": "On Linux, run `ollama serve` in a terminal to start the server."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Model pull jobs ──────────────────────────────────────────────

class PullJob:
    """A tracked `ollama pull` subprocess."""
    def __init__(self, model: str):
        self.id = str(uuid.uuid4())
        self.model = model
        self.status = "starting"  # starting | pulling | done | error | cancelled
        self.progress_pct = 0
        self.bytes_done = 0
        self.bytes_total = 0
        self.layers: list[dict] = []  # per-layer status
        self.error: Optional[str] = None
        self.log: list[str] = []  # last 200 lines of output
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._cancelled = False
        self.started_at = time.time()
        self.finished_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "model": self.model,
            "status": self.status,
            "progress_pct": round(self.progress_pct, 1),
            "bytes_done": self.bytes_done,
            "bytes_total": self.bytes_total,
            "layers": self.layers,
            "error": self.error,
            "log_tail": self.log[-20:],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": (self.finished_at or time.time()) - self.started_at,
        }


# In-memory job store
_JOBS: dict[str, PullJob] = {}
_JOBS_LOCK = threading.Lock()


# ollama pull output looks like:
#   pulling manifest...
#   pulling [██████████]  1234 / 5678 MB  45%
#   pulling sha256:abc...
#   verifying sha256 digest...
#   writing manifest...
#   removing any unused layers...
#   success
LAYER_RE = re.compile(r"^pulling\s+([0-9a-f]{12})\.\.\.\s+([0-9]+)%\s*$|"
                      r"^pulling\s+([0-9a-f]{12})\s*\|\s*([█\s]+)\|\s*([\d.]+)\s*(\w+)\s*/\s*([\d.]+)\s*(\w+)\s+(\d+)%\s*$|"
                      r"^pulling\s+([0-9a-f]{12})\s*\|\s*([\d.]+)\s*(\w+)\s+(\d+)%\s*$")
PCT_RE = re.compile(r"(\d+)%")
SIZE_RE = re.compile(r"([\d.]+)\s*(GB|MB|KB|B)")


def _parse_pull_output(line: str, job: PullJob):
    """Parse a single line of `ollama pull` output and update job state."""
    line = line.strip()
    if not line:
        return

    job.log.append(line)

    # Layer-level progress: "pulling sha256:abc123def456... 45%"
    if line.startswith("pulling sha256:") or line.startswith("pulling "):
        m = PCT_RE.search(line)
        if m:
            pct = int(m.group(1))
            # Track the latest layer's progress (o/p-p rolling)
            if job.layers and job.layers[-1].get("status") != "done":
                job.layers[-1]["pct"] = pct
            # Update overall progress as average of layers
            if job.layers:
                job.progress_pct = sum(l.get("pct", 0) for l in job.layers) / len(job.layers)

    elif line.startswith("verifying") or line.startswith("writing manifest"):
        if job.layers:
            job.layers[-1]["status"] = "done"

    elif "success" in line.lower():
        job.status = "done"
        job.progress_pct = 100
        job.finished_at = time.time()

    elif line.startswith("error"):
        job.status = "error"
        job.error = line
        job.finished_at = time.time()

    # Track new layer starts
    digest_m = re.search(r"(sha256:[0-9a-f]{12,})", line)
    if digest_m and "pulling" in line and "100%" not in line:
        digest = digest_m.group(1)
        if not any(l["digest"] == digest for l in job.layers):
            job.layers.append({"digest": digest, "pct": 0, "status": "pulling"})


def _run_pull(job: PullJob):
    """Background thread: spawn `ollama pull` and stream output."""
    ollama_bin = _ollama_cli_path()
    if not ollama_bin:
        job.status = "error"
        job.error = "ollama CLI not found on PATH. Install from ollama.com/download."
        job.finished_at = time.time()
        return

    try:
        # If a job was already created for this model and is still running, refuse
        # (the UI should poll the existing one)
        proc = subprocess.Popen(
            [ollama_bin, "pull", job.model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        job._proc = proc
        job.status = "pulling"

        assert proc.stdout is not None
        for line in proc.stdout:
            if job._cancelled:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    pass
                job.status = "cancelled"
                job.finished_at = time.time()
                return
            _parse_pull_output(line, job)

        proc.wait()
        # If user cancelled mid-stream, the cancellation path above already returned.
        if job._cancelled:
            job.status = "cancelled"
            job.finished_at = job.finished_at or time.time()
            return
        if proc.returncode == 0 and job.status == "pulling":
            # No "success" line was parsed — set it now
            job.status = "done"
            job.progress_pct = 100
        elif job.status not in ("done", "error", "cancelled"):
            job.status = "error"
            job.error = f"ollama pull exited with code {proc.returncode}"
        job.finished_at = time.time()

    except FileNotFoundError:
        if not job._cancelled:
            job.status = "error"
            job.error = "ollama CLI not found. Install from ollama.com/download."
        else:
            job.status = "cancelled"
        job.finished_at = time.time()
    except Exception as e:
        if not job._cancelled:
            job.status = "error"
            job.error = str(e)
        else:
            job.status = "cancelled"
        job.finished_at = time.time()


def start_pull(model: str) -> dict:
    """Spawn a background `ollama pull` job. Returns the job id and current state."""
    model = (model or "").strip()
    if not model or not re.match(r"^[a-zA-Z0-9._/:@\-]+$", model):
        return {"ok": False, "error": f"Invalid model name: {model!r}"}

    # If already pulled, return early
    try:
        installed = {m["name"] for m in ollama_mod.list_models()}
        if model in installed:
            return {"ok": True, "already_installed": True, "model": model}
    except Exception:
        pass  # ollama not running — proceed with pull, server will be started

    job = PullJob(model)
    with _JOBS_LOCK:
        _JOBS[job.id] = job
    t = threading.Thread(target=_run_pull, args=(job,), daemon=True)
    job._thread = t
    t.start()
    return {"ok": True, "job_id": job.id, "model": model}


def get_pull_status(job_id: str) -> Optional[dict]:
    """Poll a pull job. Returns None if job_id is unknown."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        return None
    return job.to_dict()


def cancel_pull(job_id: str) -> dict:
    """Cancel a running pull."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        return {"ok": False, "error": "Unknown job"}
    if job.status in ("done", "error", "cancelled"):
        return {"ok": True, "already_finished": True}
    job._cancelled = True
    try:
        if job._proc and job._proc.poll() is None:
            job._proc.terminate()
    except Exception:
        pass
    return {"ok": True, "cancelling": True}


def list_jobs() -> list[dict]:
    """Return all pull jobs (most recent first)."""
    with _JOBS_LOCK:
        jobs = list(_JOBS.values())
    jobs.sort(key=lambda j: j.started_at, reverse=True)
    return [j.to_dict() for j in jobs]


def cleanup_finished_jobs(older_than_s: int = 300) -> int:
    """Drop finished jobs older than N seconds. Returns the number removed."""
    now = time.time()
    removed = 0
    with _JOBS_LOCK:
        stale = [jid for jid, j in _JOBS.items()
                 if j.finished_at and (now - j.finished_at) > older_than_s]
        for jid in stale:
            del _JOBS[jid]
            removed += 1
    return removed
