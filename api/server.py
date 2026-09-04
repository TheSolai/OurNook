"""
FastAPI server for OurNook.
Serves all REST endpoints at http://127.0.0.1:18765/api/
"""
import sys, os, re, json, datetime
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
from . import db, ollama, cards, system


# ── Bundle path resolution (works for dev and PyInstaller) ─────────
# In dev (running as .py):  <project>/dist, <project>/src-ui/public
# Frozen (PyInstaller):      sys._MEIPASS/dist, sys._MEIPASS/src-ui-public
def _bundle_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / Path(*parts)
    return Path(__file__).resolve().parent.parent / Path(*parts)


# These are the asset dirs we serve from. PyInstaller bundles them as data
# files; in dev they live at <project>/dist and <project>/src-ui/public.
DIST_DIR = _bundle_path("dist")
PUBLIC_DIR = _bundle_path("src-ui-public")


# ── Helpers used by the migration below and the create_companion_full endpoint ──

def _extract_tagline(soul: str) -> str:
    """Extract a clean tagline from the soul — the first non-empty line after
    the `# Title` heading, with leading/trailing bold/italic markdown stripped.

    This is what the chat header shows as the companion's "personality" line,
    so it must be readable, not a raw markdown soup. Falls back to the first
    non-empty line of the soul if no `# Title` is found, and to "" if the soul
    is empty.
    """
    if not soul:
        return ""
    lines = soul.split("\n")
    saw_title = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            saw_title = True
            continue
        if saw_title:
            # Strip leading/trailing ** for bold and * for italic
            cleaned = stripped.strip().strip("*").strip()
            return cleaned[:280]  # cap so chat header doesn't wrap ugly
    # No "# Title" found — use the first non-empty line, cleaned
    for line in lines:
        stripped = line.strip().strip("*").strip()
        if stripped:
            return stripped[:280]
    return ""


def _migrate_legacy_personalities():
    """One-time backfill: rewrite the personality field of any companion whose
    stored value is the raw first 200 chars of the soul (the old buggy format)
    to the clean extracted tagline. Safe to run on every startup; only rewrites
    rows where the personality *starts with* the soul's first 200 chars (i.e.
    the legacy format)."""
    conn = db.get_db()
    rows = conn.execute(
        "SELECT id, name, personality, soul_path FROM companions WHERE soul_path IS NOT NULL"
    ).fetchall()
    migrated = 0
    for r in rows:
        soul_path = r["soul_path"]
        if not soul_path or not os.path.exists(soul_path):
            continue
        try:
            with open(soul_path) as f:
                soul = f.read()
        except OSError:
            continue
        # If the stored personality starts with the soul's first 200 chars,
        # it's the legacy buggy format.
        legacy_prefix = soul[:200]
        if r["personality"] and r["personality"].startswith(legacy_prefix):
            new_tagline = _extract_tagline(soul)
            if new_tagline and new_tagline != r["personality"]:
                conn.execute(
                    "UPDATE companions SET personality = ? WHERE id = ?",
                    (new_tagline, r["id"]),
                )
                migrated += 1
    if migrated:
        conn.commit()
    conn.close()
    return migrated


# Init DB on import
db.init_db()
# Backfill the personality field of any companion created before the
# tagline-extraction fix. Safe to run on every startup.
try:
    n = _migrate_legacy_personalities()
    if n:
        print(f"[startup] migrated {n} legacy personality field(s)", file=sys.stderr)
except Exception as e:
    print(f"[startup] legacy personality migration failed: {e}", file=sys.stderr)

app = FastAPI(title="OurNook API", version="0.5.2")

# CORS — allow pywebview's local file:// origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────

class CreateCompanionData(BaseModel):
    name: str
    avatar_path: Optional[str] = None
    backstory: str = ""
    personality: str = ""
    voice_config: Optional[str] = None
    memory_mode: str = "hybrid"
    model_name: str = "qwen3:14b"
    relationship_type: str = "friend"

class SendMessageData(BaseModel):
    companionId: str
    text: str

class AddMemoryData(BaseModel):
    companionId: str
    factText: str
    category: Optional[str] = None
    importance: float = 5  # float allows int; clamped to 1-10 in db layer

class UpdateMemoryData(BaseModel):
    id: str
    factText: str
    category: Optional[str] = None
    importance: float = 5  # float allows int; clamped to 1-10 in db layer

class AvatarInteractData(BaseModel):
    companionId: str
    interaction: str

class SaveSummaryData(BaseModel):
    companionId: str
    summary: str
    emotionalTone: Optional[str] = None
    relationshipState: Optional[str] = None

class AddDiaryData(BaseModel):
    companionId: str
    content: str
    moodTag: Optional[str] = None

class ImageGenData(BaseModel):
    companionId: str
    prompt: str
    model: Optional[str] = None
    size: Optional[str] = None
    seed: Optional[int] = None
    negativePrompt: Optional[str] = None
    steps: Optional[int] = None

class SoulInputsData(BaseModel):
    identity: dict
    archetype: str
    ocean: dict
    quiz_answers: list
    freeform_notes: Optional[str] = None
    voice: dict

class QuizAnswer(BaseModel):
    question_id: str
    value: int

# ── Backup / Restore ───────────────────────────────────────────────

BACKUP_DIR = db.DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

@app.get("/api/backups")
def list_backups():
    """List all backup files."""
    import glob
    files = []
    for p in BACKUP_DIR.glob("ournook-backup-*.zip"):
        stat = p.stat()
        files.append({
            "path": str(p),
            "name": p.name,
            "bytes": stat.st_size,
            "modified": int(stat.st_mtime * 1000),
        })
    files.sort(key=lambda f: f["modified"], reverse=True)
    return files

@app.post("/api/backups/companion/{companion_id}")
def backup_companion(companion_id: str):
    """Backup a single companion."""
    import zipfile, datetime, shutil
    companion = db.get_companion(companion_id)
    if not companion:
        raise HTTPException(404, "Companion not found")
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = BACKUP_DIR / f"ournook-backup-{companion['name']}-{ts}.zip"
    # Atomic write: write to a temp file first, then rename. If we crash
    # mid-write, the previous backup (or nothing) survives — never a half-zip.
    tmp_fname = fname.with_suffix(fname.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp_fname, "w", zipfile.ZIP_DEFLATED) as zf:
            # DB export
            import json
            conn = db.get_db()
            rows = conn.execute(
                "SELECT * FROM messages WHERE companion_id=?", (companion_id,)
            ).fetchall()
            msgs = [dict(r) for r in rows]
            rows2 = conn.execute(
                "SELECT * FROM semantic_memories WHERE companion_id=?", (companion_id,)
            ).fetchall()
            mems = [dict(r) for r in rows2]
            rows3 = conn.execute(
                "SELECT * FROM diary_entries WHERE companion_id=?", (companion_id,)
            ).fetchall()
            diary = [dict(r) for r in rows3]
            rows4 = conn.execute(
                "SELECT * FROM session_summaries WHERE companion_id=?", (companion_id,)
            ).fetchall()
            sums = [dict(r) for r in rows4]
            rows5 = conn.execute(
                "SELECT * FROM art_entries WHERE companion_id=?", (companion_id,)
            ).fetchall()
            art = [dict(r) for r in rows5]
            conn.close()
            zf.writestr("companion.json", json.dumps(companion, default=str))
            zf.writestr("messages.json", json.dumps(msgs, default=str))
            zf.writestr("memories.json", json.dumps(mems, default=str))
            zf.writestr("diary.json", json.dumps(diary, default=str))
            zf.writestr("summaries.json", json.dumps(sums, default=str))
            zf.writestr("art.json", json.dumps(art, default=str))
            # Soul file
            soul_path = companion.get("soul_path", "")
            if soul_path and os.path.exists(soul_path):
                with open(soul_path) as f:
                    zf.writestr("soul.md", f.read())
            # Avatar
            avatar = companion.get("avatar_path", "")
            if avatar and os.path.exists(avatar):
                with open(avatar, "rb") as f:
                    zf.writestr("avatar.png", f.read())
        # Atomic rename — temp is now the real file (after with closes the zip)
        os.replace(tmp_fname, fname)
    except Exception:
        # Clean up the temp file on failure
        try:
            if os.path.exists(tmp_fname):
                os.unlink(tmp_fname)
        except OSError:
            pass
        raise
    return {"path": str(fname), "bytes": fname.stat().st_size}

@app.post("/api/backups/all")
def backup_all():
    """Backup all companions."""
    import zipfile, datetime, json
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = BACKUP_DIR / f"ournook-backup-all-{ts}.zip"
    # Atomic write (same pattern as single-companion backup above)
    tmp_fname = fname.with_suffix(fname.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp_fname, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "version": "0.5.2", "type": "full", "companion_count": len(companions),
                "timestamp": ts,
            }, default=str))
            for c in companions:
                cid = c["id"]
                conn = db.get_db()
                rows = conn.execute("SELECT * FROM messages WHERE companion_id=?", (cid,)).fetchall()
                mems = conn.execute("SELECT * FROM semantic_memories WHERE companion_id=?", (cid,)).fetchall()
                diary = conn.execute("SELECT * FROM diary_entries WHERE companion_id=?", (cid,)).fetchall()
                sums = conn.execute("SELECT * FROM session_summaries WHERE companion_id=?", (cid,)).fetchall()
                art = conn.execute("SELECT * FROM art_entries WHERE companion_id=?", (cid,)).fetchall()
                conn.close()
                zf.writestr(f"{cid}/companion.json", json.dumps(c, default=str))
                zf.writestr(f"{cid}/messages.json", json.dumps([dict(r) for r in rows], default=str))
                zf.writestr(f"{cid}/memories.json", json.dumps([dict(r) for r in mems], default=str))
                zf.writestr(f"{cid}/diary.json", json.dumps([dict(r) for r in diary], default=str))
                zf.writestr(f"{cid}/summaries.json", json.dumps([dict(r) for r in sums], default=str))
                zf.writestr(f"{cid}/art.json", json.dumps([dict(r) for r in art], default=str))
                soul_path = c.get("soul_path", "")
                if soul_path and os.path.exists(soul_path):
                    with open(soul_path) as f:
                        zf.writestr(f"{cid}/soul.md", f.read())
                avatar = c.get("avatar_path", "")
                if avatar and os.path.exists(avatar):
                    with open(avatar, "rb") as f:
                        zf.writestr(f"{cid}/avatar.png", f.read())
        os.replace(tmp_fname, fname)
    except Exception:
        try:
            if os.path.exists(tmp_fname):
                os.unlink(tmp_fname)
        except OSError:
            pass
        raise
    return {"path": str(fname), "bytes": fname.stat().st_size, "companion_count": len(companions)}

@app.post("/api/backups/restore")
def restore_backup(data: dict):
    """Restore from a backup zip file."""
    import zipfile, json
    path = data.get("path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(400, "Backup file not found")
    imported = []
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        if "manifest.json" in names:
            # Full backup — restore all companions
            for name in names:
                if name.startswith("_") or "/" not in name:
                    continue
                cid_dir = name.split("/")[0]
                if f"{cid_dir}/companion.json" in names:
                    comp_data = json.loads(zf.read(f"{cid_dir}/companion.json"))
                    existing = db.get_companion(cid_dir)
                    if existing:
                        db.delete_companion(cid_dir)
                    new_c = db.create_companion({
                        "name": comp_data.get("name", "Imported"),
                        "avatar_path": None,
                        "backstory": comp_data.get("backstory", ""),
                        "personality": comp_data.get("personality", ""),
                        "voice_config": comp_data.get("voice_config"),
                        "memory_mode": comp_data.get("memory_mode", "hybrid"),
                        "model_name": comp_data.get("model_name", "qwen3:14b"),
                        "relationship_type": comp_data.get("relationship_type", "friend"),
                    })
                    # Restore soul
                    soul_name = f"{cid_dir}/soul.md"
                    if soul_name in names:
                        ollama.write_soul_md(new_c["id"], zf.read(soul_name).decode())
                    imported.append(new_c["id"])
        elif "companion.json" in names:
            # Single companion backup
            comp_data = json.loads(zf.read("companion.json"))
            new_c = db.create_companion({
                "name": comp_data.get("name", "Imported"),
                "avatar_path": None,
                "backstory": comp_data.get("backstory", ""),
                "personality": comp_data.get("personality", ""),
                "voice_config": comp_data.get("voice_config"),
                "memory_mode": comp_data.get("memory_mode", "hybrid"),
                "model_name": comp_data.get("model_name", "qwen3:14b"),
                "relationship_type": comp_data.get("relationship_type", "friend"),
            })
            soul_name = "soul.md"
            if soul_name in names:
                ollama.write_soul_md(new_c["id"], zf.read(soul_name).decode())
            imported.append(new_c["id"])
    return {"new_companion_ids": imported, "skipped": 0}

# ── Character card import / export (SillyTavern format) ────────

@app.post("/api/companions/import-file")
async def import_card_file(file: UploadFile = File(...)):
    """Import a SillyTavern card file. Accepts .json or .png."""
    try:
        content = await file.read()
        if not content:
            raise HTTPException(400, "Empty file")
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "File too large (50MB max)")
        new_c = cards.import_companion_from_file(file.filename or "card.json", content)
        return {"ok": True, "companion": new_c, "name": new_c["name"]}
    except HTTPException:
        raise  # let FastAPI handle it
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Import failed: {e}")

@app.post("/api/companions/import-paste")
def import_card_paste(data: dict):
    """Import a SillyTavern card from a pasted JSON string (no file upload)."""
    raw = data.get("json", "").strip()
    if not raw:
        raise HTTPException(400, "Empty card JSON")
    try:
        new_c = cards.import_companion_from_file("pasted.json", raw.encode("utf-8"))
        return {"ok": True, "companion": new_c, "name": new_c["name"]}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Import failed: {e}")

@app.get("/api/companions/{cid}/export")
def export_card(cid: str, format: str = "json"):
    """Export a companion as a SillyTavern-compatible character card.

    format=json → returns application/json download
    format=png  → returns image/png with the card embedded in a tEXt chunk
                  (uses the companion's avatar as the base image; falls back to a generated one)
    """
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    try:
        card = cards.companion_to_card(cid)
    except Exception as e:
        raise HTTPException(500, f"Could not build card: {e}")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", c["name"]).strip("_") or "companion"
    payload = json.dumps(card, ensure_ascii=False, indent=2)

    if format == "png":
        # Start with the existing avatar if it's a real PNG, else use a 1x1 transparent placeholder
        from .cards import PNG_MAGIC, embed_json_in_png
        base_png: bytes | None = None
        ap = c.get("avatar_path")
        if ap and Path(ap).exists() and ap.endswith(".png"):
            data = Path(ap).read_bytes()
            if data.startswith(PNG_MAGIC):
                base_png = data
        if base_png is None:
            # Valid 1x1 transparent PNG (generated and verified)
            base_png = bytes.fromhex(
                "89504e470d0a1a0a"          # PNG sig
                "0000000d49484452"            # IHDR len=13 + type
                "00000001000000010806000000"  # IHDR data (1x1 8-bit RGBA)
                "1f15c489"                    # IHDR CRC
                "0000000b49444154"            # IDAT len=11 + type
                "789c636000020000050001"      # IDAT data (zlib-compressed transparent pixel)
                "7a5eab3f"                    # IDAT CRC
                "0000000049454e44"            # IEND len=0 + type
                "ae426082"                    # IEND CRC
            )
        try:
            png_bytes = embed_json_in_png(base_png, payload)
        except Exception as e:
            raise HTTPException(500, f"PNG embed failed: {e}")
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.png"'},
        )

    # JSON
    return Response(
        content=payload.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.json"'},
    )

@app.get("/api/companions/{cid}/card-preview")
def preview_card(cid: str):
    """Return the card JSON (no download headers) for previewing before export."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    try:
        return cards.companion_to_card(cid)
    except Exception as e:
        raise HTTPException(500, str(e))

class OceanTraits(BaseModel):
    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float

# ── App Info ──────────────────────────────────────────────────────

@app.get("/api/ping")
def ping():
    return {"ok": True}


# Track when the server started, for uptime reporting
import time as _time
_SERVER_START_TIME = _time.time()


@app.get("/api/heartbeat")
def heartbeat():
    """Liveness + uptime + version. Lightweight — safe to poll.
    The UI can use this to detect when the API is down and show a clear
    'API server is offline' banner instead of a hanging spinner."""
    import platform, datetime, os
    return {
        "ok": True,
        "name": "OurNook",
        "version": "0.5.2",
        "platform": platform.system(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "pid": os.getpid(),
        "uptime_s": int(_time.time() - _SERVER_START_TIME),
        "started_at": datetime.datetime.fromtimestamp(_SERVER_START_TIME).isoformat(),
        "now": datetime.datetime.now().isoformat(),
    }


@app.get("/api/app-info")
def app_info():
    import platform, datetime
    return {
        "name": "OurNook",
        "version": "0.5.2",
        "platform": platform.system(),
        "data_dir": str(db.DATA_DIR),
        "started_at": datetime.datetime.now().isoformat(),
    }

# ── Ollama ────────────────────────────────────────────────────────

@app.get("/api/ollama/health")
def check_ollama():
    return ollama.check_ollama()

@app.get("/api/ollama/models")
def list_models():
    return ollama.list_models()

@app.get("/api/ollama/image-models")
def list_image_models():
    return ollama.list_image_models()

# ── Models catalog ────────────────────────────────────────────────

RECOMMENDED_MODELS = [
    # Text/chat models
    {
        "name": "qwen3:14b",
        "category": "chat",
        "label": "Qwen 3 (14B)",
        "description": "Fast, capable reasoning model. Great for conversation, memory, and personality. Our default. Excellent speed-to-quality ratio.",
        "size": "~27GB",
        "ram_needed": "16GB+",
        "gpu": "Recommended (Metal on Mac, CUDA on Windows)",
        "pull_cmd": "ollama pull qwen3:14b",
        "url": "https://ollama.com/library/qwen3",
        "why": "Best default for companions — fast, smart, handles long conversations well.",
        "tags": ["default", "fast", "reasoning"],
    },
    {
        "name": "llama3.3:70b",
        "category": "chat",
        "label": "Llama 3.3 (70B)",
        "description": "Meta's flagship model. Highest quality conversation and reasoning, but very large. Best for high-end hardware.",
        "size": "~40GB",
        "ram_needed": "64GB+",
        "gpu": "Required (Metal/CUDA/ROCm)",
        "pull_cmd": "ollama pull llama3.3:70b",
        "url": "https://ollama.com/library/llama3.3",
        "why": "Top quality responses. Only if you have the RAM.",
        "tags": ["quality", "large"],
    },
    {
        "name": "mistral-nemo:12b",
        "category": "chat",
        "label": "Mistral Nemo (12B)",
        "description": "Balanced model from Mistral AI. Good conversation quality at moderate size. Works well without a GPU.",
        "size": "~24GB",
        "ram_needed": "24GB+",
        "gpu": "Helpful but not required",
        "pull_cmd": "ollama pull mistral-nemo:12b",
        "url": "https://ollama.com/library/mistral-nemo",
        "why": "Good middle ground — solid quality, manageable size.",
        "tags": ["balanced", "no-gpu"],
    },
    {
        "name": "phi4:14b",
        "category": "chat",
        "label": "Phi-4 (14B)",
        "description": "Microsoft's dense model. Impressive reasoning at small size. Excellent for systems with limited VRAM.",
        "size": "~9GB",
        "ram_needed": "12GB+",
        "gpu": "Recommended",
        "pull_cmd": "ollama pull phi4:14b",
        "url": "https://ollama.com/library/phi4",
        "why": "Great if you want quality on a budget GPU.",
        "tags": ["fast", "small-gpu"],
    },
    {
        "name": "deepseek-r1:14b",
        "category": "chat",
        "label": "DeepSeek R1 (14B)",
        "description": "Excellent reasoning and chain-of-thought capabilities. Great for analytical companions who think through problems.",
        "size": "~27GB",
        "ram_needed": "16GB+",
        "gpu": "Recommended",
        "pull_cmd": "ollama pull deepseek-r1:14b",
        "url": "https://ollama.com/library/deepseek-r1",
        "why": "Best for companions who need to reason through complex topics.",
        "tags": ["reasoning", "analytical"],
    },
    {
        "name": "gemma3:12b",
        "category": "chat",
        "label": "Gemma 3 (12B)",
        "description": "Google's open model. Good instruction-following and personality consistency. Newer release.",
        "size": "~8GB",
        "ram_needed": "12GB+",
        "gpu": "Helpful but not required",
        "pull_cmd": "ollama pull gemma3:12b",
        "url": "https://ollama.com/library/gemma3",
        "why": "Good alternative to Phi-4. Google's quality at small size.",
        "tags": ["small", "google"],
    },
    # Embedding models
    {
        "name": "nomic-embed-text",
        "category": "embedding",
        "label": "Nomic Embed Text",
        "description": "Fast, high-quality text embeddings for memory search. Required for semantic memory. Small and fast — keep it installed.",
        "size": "~274MB",
        "ram_needed": "512MB",
        "gpu": "CPU fine",
        "pull_cmd": "ollama pull nomic-embed-text",
        "url": "https://ollama.com/library/nomic-embed-text",
        "why": "Powers memory search. Extracts meaning from conversations.",
        "tags": ["memory", "required"],
    },
    # Image generation
    {
        "name": "x/flux1-schnell",
        "category": "image",
        "label": "FLUX.1 Schnell",
        "description": "Fast, high-quality image generation. Great for avatar and art generation. 4 steps to image.",
        "size": "~12GB",
        "ram_needed": "16GB+ VRAM",
        "gpu": "Required",
        "pull_cmd": "ollama pull x/flux1-schnell",
        "url": "https://ollama.com/library/flux",
        "why": "Best quality image model on Ollama right now.",
        "tags": ["image-gen", "fast"],
    },
    {
        "name": "x/z-image-turbo",
        "category": "image",
        "label": "Zebra Image Turbo",
        "description": "Fast turbocharged image model. Good for quick avatar and art generations. Our default.",
        "size": "~4GB",
        "ram_needed": "8GB+ VRAM",
        "gpu": "Required",
        "pull_cmd": "ollama pull x/z-image-turbo",
        "url": "https://ollama.com/library/z-image",
        "why": "Fast and lightweight. Good for frequent art generation.",
        "tags": ["image-gen", "default", "fast"],
    },
]

@app.get("/api/models/catalog")
def models_catalog():
    """Return recommended models with Ollama install status."""
    installed = {m["name"]: m for m in ollama.list_models()}
    catalog = []
    for model in RECOMMENDED_MODELS:
        m = dict(model)
        name = m["name"]
        m["installed"] = name in installed
        if name in installed:
            m["installed_size"] = installed[name].get("size")
        catalog.append(m)
    return catalog

@app.post("/api/models/pull")
def pull_model(body: dict):
    """Spawn a background `ollama pull` job. Returns the job_id to poll for progress."""
    model = body.get("model", "")
    return system.start_pull(model)


@app.get("/api/models/pull/{job_id}")
def get_pull_status(job_id: str):
    """Poll a pull job. Returns full status including progress_pct and layer breakdown."""
    status = system.get_pull_status(job_id)
    if status is None:
        raise HTTPException(404, f"Unknown job: {job_id}")
    return status


@app.delete("/api/models/pull/{job_id}")
def cancel_pull_endpoint(job_id: str):
    """Cancel a running pull."""
    return system.cancel_pull(job_id)


@app.get("/api/models/pull-jobs")
def list_pull_jobs():
    """List all pull jobs (most recent first). Used to recover UI state on reload."""
    return system.list_jobs()


# ── System (Ollama detect / launch) ──────────────────────────────

@app.get("/api/system/status")
def system_status():
    """Full system status: ollama installed/running/version, what models are present,
    whether the user is set up to chat. Drives the Models onboarding UI."""
    return system.get_system_status()


@app.post("/api/system/launch-ollama")
def launch_ollama_endpoint():
    """Open the Ollama desktop app, which starts the server in the background."""
    return system.launch_ollama_app()


@app.get("/api/system/recommend")
def recommend_models_endpoint():
    """Return the 'starter pack' — the absolute minimum recommended models for someone
    getting started. Used by the onboarding checklist."""
    return {
        "chat": {
            "name": "qwen3:14b",
            "label": "Qwen 3 (14B)",
            "size": "~9GB",
            "ram_needed": "16GB+",
            "why": "Best balance of quality and size for most people. Fast on Apple Silicon and modern GPUs.",
            "fallback_name": "qwen2.5:3b",
            "fallback_label": "Qwen 2.5 (3B) — tiny",
            "fallback_size": "~2GB",
            "fallback_why": "Pick this if your machine is older or has limited RAM.",
        },
        "embedding": {
            "name": "nomic-embed-text",
            "label": "Nomic Embed Text",
            "size": "~274MB",
            "ram_needed": "512MB",
            "why": "Powers memory search. Tiny — always install this.",
        },
    }

# ── Companions ─────────────────────────────────────────────────────

@app.get("/api/companions")
def list_companions():
    return db.list_companions()

@app.get("/api/companions/{cid}")
def get_companion(cid: str):
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    return c

@app.post("/api/companions")
def create_companion(data: CreateCompanionData):
    return db.create_companion(data.model_dump())

@app.delete("/api/companions/{cid}")
def delete_companion(cid: str):
    db.delete_companion(cid)
    return {"ok": True}

class UpdateCompanionData(BaseModel):
    name: Optional[str] = None
    backstory: Optional[str] = None
    personality: Optional[str] = None
    voice_config: Optional[str] = None
    memory_mode: Optional[str] = None
    model_name: Optional[str] = None
    relationship_type: Optional[str] = None

@app.put("/api/companions/{cid}")
def update_companion(cid: str, data: UpdateCompanionData):
    """Update a companion's editable fields. Only supplied keys are changed."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if "name" in fields and not fields["name"].strip():
        raise HTTPException(400, "Name cannot be empty")
    if "model_name" in fields and not fields["model_name"].strip():
        raise HTTPException(400, "Model name cannot be empty")
    return db.update_companion(cid, fields)

class UpdateSoulData(BaseModel):
    soul: str

@app.put("/api/companions/{cid}/soul")
def update_soul(cid: str, data: UpdateSoulData):
    """Replace the companion's soul.md content."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    if not c.get("soul_path"):
        raise HTTPException(400, "This companion has no soul.md")
    Path(c["soul_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(c["soul_path"]).write_text(data.soul)
    db.update_companion(cid, {})  # bumps updated_at
    return {"ok": True, "soul_path": c["soul_path"]}


# ── Enneagram (v0.15) ───────────────────────────────────────────
# Personality framework — 9 types, wings, instincts, health. Drives the
# "create a companion" wizard and the EditCompanion Enneagram panel.
# All endpoints are read-only or thin wrappers over the type data, except
# the soul-synthesis endpoint which generates a soul.md body from a
# (type, wing, instinct, health) tuple.

@app.get("/api/enneagram/types")
def list_enneagram_types():
    """Return the 9 Enneagram types (full profile data, no quiz/soul)."""
    from . import enneagram as en
    return en.TYPES


@app.get("/api/enneagram/quiz")
def get_enneagram_quiz():
    """Return the 9 quiz questions. Each is a pairwise comparison."""
    from . import enneagram_quiz as q
    return q.all_questions()


class EnneagramQuizData(BaseModel):
    answers: list[Optional[str]]


@app.post("/api/enneagram/quiz/score")
def score_enneagram_quiz(data: EnneagramQuizData):
    """Score a quiz and return the dominant type, wing, and confidence."""
    from . import enneagram_quiz as q
    try:
        return q.take_quiz(data.answers)
    except ValueError as e:
        raise HTTPException(400, str(e))


class EnneagramSoulData(BaseModel):
    type: int
    wing: Optional[int] = None
    instinct: Optional[str] = "sp"
    health: Optional[str] = "average"
    name: Optional[str] = None
    extra_context: Optional[str] = None


@app.post("/api/enneagram/build-soul")
def build_soul_from_enneagram(data: EnneagramSoulData):
    """Generate a soul.md body from Enneagram metadata. The wizard
    uses this to pre-fill the soul so the user can edit before saving."""
    from . import enneagram_soul as s
    try:
        return {"soul": s.build_soul(
            type_num=data.type, wing=data.wing,
            instinct=data.instinct, health=data.health,
            name=data.name, extra_context=data.extra_context,
        )}
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


class SetEnneagramData(BaseModel):
    type: int
    wing: Optional[int] = None
    instinct: Optional[str] = "sp"
    health: Optional[str] = "average"


@app.put("/api/companions/{cid}/enneagram")
def set_companion_enneagram(cid: str, data: SetEnneagramData):
    """Set the companion's Enneagram profile. Validates the type, wing,
    instinct, and health before writing."""
    from . import enneagram as en
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    try:
        type_num = data.type
        if type_num not in en.TYPES:
            raise ValueError(f"Invalid type: {type_num}")
        wing = en.validate_wing(type_num, data.wing)
        instinct = en.validate_instinct(data.instinct)
        health = en.validate_health(data.health)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    return db.update_companion(cid, {
        "enneagram_type": type_num,
        "enneagram_wing": wing,
        "enneagram_instinct": instinct,
        "enneagram_health": health,
    })


# ── Memory Categories (v0.15) ────────────────────────────────────

@app.get("/api/memory/categories")
def list_memory_categories():
    """Return the canonical memory categories (id, name, description,
    examples) for the UI's category filter and the auto-suggest helper."""
    from . import memory_categories as mc
    return mc.all_categories()


class SuggestCategoryData(BaseModel):
    text: str


@app.post("/api/memory/suggest-category")
def suggest_memory_category(data: SuggestCategoryData):
    """Suggest a canonical category for a fact text. Used by the inline
    'remember this' form to auto-pick the right category as the user types."""
    from . import memory_categories as mc
    cat = mc.suggest_category(data.text)
    return {
        "category": cat,
        "importance": mc.default_importance_for(cat),
        "name": mc.get_category(cat)["name"] if mc.get_category(cat) else None,
    }


# ── Inner Life (v0.12) ──────────────────────────────────────────
# Endpoints for the companion's own continuity — current state, mood,
# private journal, special moments. All read by build_system_prompt so
# the AI has a real sense of "who I am right now".

@app.get("/api/companions/{cid}/state")
def get_companion_state(cid: str):
    """Return the companion's persistent state (mood, last-seen, streak,
    message counts). Auto-creates an empty row if missing."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    state = db.get_companion_state(cid)
    # Decorate with humanized fields for the UI
    from datetime import datetime as _dt
    days_known = 0
    if c.get("created_at"):
        try:
            days_known = (_dt.now() - _dt.fromisoformat(c["created_at"])).days
        except ValueError:
            pass
    state["days_known"] = days_known
    return state


class MoodData(BaseModel):
    mood: str


@app.put("/api/companions/{cid}/mood")
def set_companion_mood(cid: str, data: MoodData):
    """Set the companion's current mood (free text). Empty string clears."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    mood = (data.mood or "").strip()
    if len(mood) > 200:
        raise HTTPException(400, "Mood too long (200 char max)")
    return db.update_companion_mood(cid, mood)


# ── Companion journal (private thoughts) ──────────────────────────

class JournalEntryData(BaseModel):
    content: str
    mood: Optional[str] = None
    related_message_id: Optional[str] = None


@app.post("/api/companions/{cid}/journal")
def create_journal_entry(cid: str, data: JournalEntryData):
    """Add a private journal entry for the companion."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    try:
        return db.add_journal_entry(cid, data.content, data.mood, data.related_message_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/companions/{cid}/journal")
def list_journal_entries(cid: str, limit: int = 20):
    """List the companion's journal entries, most recent first."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    return db.list_journal(cid, limit)


@app.delete("/api/journal/{eid}")
def delete_journal_entry_endpoint(eid: str):
    """Delete a journal entry."""
    ok = db.delete_journal_entry(eid)
    return {"deleted": ok}


# ── Companion moments (episodic memory) ──────────────────────────

class MomentData(BaseModel):
    title: str
    description: Optional[str] = None
    related_message_id: Optional[str] = None
    significance: int = 5


@app.post("/api/companions/{cid}/moments")
def create_moment(cid: str, data: MomentData):
    """Record a special moment the companion wants to remember."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    try:
        return db.add_moment(cid, data.title, data.description, data.related_message_id, data.significance)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/companions/{cid}/moments")
def list_moments(cid: str, limit: int = 20):
    """List the companion's remembered moments, highest significance first."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    return db.list_moments(cid, limit)


@app.delete("/api/moments/{mid}")
def delete_moment_endpoint(mid: str):
    """Delete a moment."""
    ok = db.delete_moment(mid)
    return {"deleted": ok}


# ── Diary-as-letter (already-existing endpoint, just for symmetry) ──
# The build_system_prompt flow auto-marks unread diary entries as read on
# every chat send. These endpoints let the user peek at that loop manually.

@app.get("/api/companions/{cid}/diary/unread")
def list_unread_diary_entries(cid: str):
    """List diary entries the companion hasn't 'read' yet."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    return db.list_unread_diary(cid)


@app.post("/api/companions/{cid}/diary/mark-read")
def mark_diary_read_endpoint(cid: str):
    """Manually mark all unread diary entries as read (e.g. if the user
    just wants to dismiss them without the companion referencing them)."""
    c = db.get_companion(cid)
    if not c:
        raise HTTPException(404, "Companion not found")
    n = db.mark_diary_read(cid)
    return {"marked": n}

# ── Create companion full (wizard) ────────────────────────────────

class CreateCompanionFullData(BaseModel):
    name: str
    soul: str
    ocean: Optional[dict] = None
    archetype: str = ""
    relationshipType: str = "friend"
    memoryMode: str = "hybrid"
    voiceConfig: Optional[str] = None
    avatarPath: Optional[str] = None
    modelName: str = "qwen3:14b"
    enneagramType: Optional[int] = None
    enneagramWing: Optional[int] = None
    enneagramInstinct: Optional[str] = None
    enneagramHealth: Optional[str] = None



@app.post("/api/companions/full")
def create_companion_full(data: CreateCompanionFullData):
    """Create companion with soul.md file in one shot."""
    import uuid
    cid = str(uuid.uuid4())
    soul_path = db.DATA_DIR / "companions" / cid / "soul.md"
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(data.soul)
    avatar_path = data.avatarPath
    if avatar_path:
        import shutil
        dest = soul_path.parent / "avatar.png"
        shutil.copy(avatar_path, dest)
        avatar_path = str(dest)

    # The personality field is shown in the chat header. Use the cleaned
    # tagline extracted from the soul, NOT the raw first 200 chars of the
    # soul (which would include "# Title\n\n**bold tagline**..." — ugly).
    tagline = _extract_tagline(data.soul)

    # Validate Enneagram if provided (silently drop invalid rather than
    # blocking the create — the wizard's preview should not 500 on a
    # bad selection, the user can fix it on the EditCompanion panel).
    from . import enneagram as en
    etype = data.enneagramType
    ewing = None
    einstinct = None
    ehealth = None
    if etype is not None and etype in en.TYPES:
        try:
            ewing = en.validate_wing(etype, data.enneagramWing)
            einstinct = en.validate_instinct(data.enneagramInstinct)
            ehealth = en.validate_health(data.enneagramHealth)
        except ValueError:
            etype = None  # bad payload — drop silently

    conn = db.get_db()
    conn.execute("""
        INSERT INTO companions (id, name, backstory, personality, voice_config, memory_mode,
            model_name, relationship_type, soul_path,
            enneagram_type, enneagram_wing, enneagram_instinct, enneagram_health)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cid, data.name, "", tagline, data.voiceConfig,
          data.memoryMode, data.modelName, data.relationshipType, str(soul_path),
          etype, ewing, einstinct, ehealth))
    conn.commit()
    conn.close()
    return db.get_companion(cid)

@app.get("/api/companions/{cid}/avatar-url")
def companion_avatar_url(cid: str):
    """Return avatar as a data URL."""
    import base64
    c = db.get_companion(cid)
    if not c or not c.get("avatar_path") or not os.path.exists(c["avatar_path"]):
        return {"url": None}
    with open(c["avatar_path"], "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"url": f"data:image/png;base64,{b64}"}

# ── Chat ──────────────────────────────────────────────────────────

@app.get("/api/chat/{companion_id}/messages")
def recent_messages(companion_id: str, limit: int = 100):
    return db.recent_messages(companion_id, limit)

@app.post("/api/chat/send")
def send_message(data: SendMessageData):
    try:
        return ollama.send_message(data.companionId, data.text)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/chat/messages/{mid}")
def delete_message_endpoint(mid: str):
    """Delete a single chat message. Returns {deleted: true/false}."""
    ok = db.delete_message(mid)
    return {"deleted": ok}


class RegenerateData(BaseModel):
    companionId: str
    # Optional: which message id to anchor on. If not provided, the most recent
    # assistant message is used. The user message just before it (and that assistant
    # message itself) are removed, then a new assistant reply is generated.
    afterUserMessageId: Optional[str] = None


@app.post("/api/chat/regenerate")
def regenerate(data: RegenerateData):
    """Re-generate the last assistant response. Removes the latest assistant message
    and (if it has no user message before it that needs preserving) the latest user
    message, then re-runs the chat. Pass `afterUserMessageId` to anchor on a
    specific user message — everything from that user message onward is removed
    and re-generated."""
    try:
        return ollama.regenerate(data.companionId, data.afterUserMessageId)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


class EditResendData(BaseModel):
    companionId: str
    messageId: str  # The user message to edit
    newText: str    # The replacement text


@app.post("/api/chat/edit-resend")
def edit_resend(data: EditResendData):
    """Edit a user message and re-generate the assistant reply that followed it.
    The edited message keeps its original id; everything from it onward is removed
    and re-generated with the new text."""
    if not data.newText or not data.newText.strip():
        raise HTTPException(400, "New message text cannot be empty")
    try:
        return ollama.edit_and_resend(data.companionId, data.messageId, data.newText.strip())
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


class ChatMetaData(BaseModel):
    model: Optional[str] = None
    total_duration_ns: Optional[int] = None
    eval_count: Optional[int] = None
    prompt_eval_count: Optional[int] = None


@app.post("/api/chat/messages/{mid}/meta")
def set_message_meta(mid: str, data: ChatMetaData):
    """Attach response-time / model / token metadata to a message. The frontend
    calls this right after receiving an assistant reply so the user can see how
    long the model took and what model produced it."""
    from . import db as _db
    msg = _db.get_message(mid)
    if not msg:
        raise HTTPException(404, "Message not found")
    # We piggyback on the messages table by serializing meta into the content
    # field with a sentinel. Less elegant than a side table, but no schema change.
    # The frontend strips this back out for display.
    import json as _json
    if msg["role"] == "assistant" and "---meta:" not in (msg.get("content") or ""):
        meta_line = f"\n\n---meta: {_json.dumps({k: v for k, v in data.model_dump().items() if v is not None})}---"
        _db.update_message_content(mid, msg["content"] + meta_line)
    return {"ok": True}


@app.get("/api/chat/{companion_id}/export")
def export_chat(companion_id: str, format: str = "md"):
    """Export a companion's chat history as a Markdown file.

    This is a real QoL win — users want to keep conversations, share them, or
    print them. We group by day and label roles clearly.
    """
    c = db.get_companion(companion_id)
    if not c:
        raise HTTPException(404, "Companion not found")
    msgs = db.recent_messages(companion_id, limit=10000)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", c["name"]).strip("_") or "companion"

    if format == "txt":
        lines = [f"{c['name']} — chat export", ""]
        for m in msgs:
            who = c["name"] if m["role"] == "assistant" else "You"
            ts = m.get("created_at", "")
            lines.append(f"[{ts}] {who}:")
            lines.append(m["content"])
            lines.append("")
        body = "\n".join(lines)
        return Response(
            content=body.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}-chat.txt"'},
        )

    # Markdown
    out = [f"# {c['name']} — Chat Export", ""]
    if c.get("personality"):
        out += ["", f"> *{c['personality'][:200]}*", ""]
    out += ["", f"_Exported {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]

    last_day = None
    for m in msgs:
        day = (m.get("created_at") or "")[:10]
        if day != last_day:
            out += ["", f"## {day}", ""]
            last_day = day
        who = f"**{c['name']}**" if m["role"] == "assistant" else "**You**"
        # Strip the ---meta: ... --- block from content
        content = re.sub(r"\n*---meta:.*?---", "", m["content"]).strip()
        out += [f"{who}: {content}", ""]

    return Response(
        content="\n".join(out).encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-chat.md"'},
    )

@app.post("/api/chat/interact")
def avatar_interact(data: AvatarInteractData):
    try:
        return ollama.avatar_interact(data.companionId, data.interaction)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/chat/{companion_id}/system-prompt")
def get_system_prompt(companion_id: str):
    """Return the full system prompt that would be sent to Ollama for this companion.
    Includes soul.md, personality, backstory, the companion's current state
    (v0.12 inner life), substrate (model info), identity memories, and recent
    summaries. Useful for debugging 'why is my AI saying this?'."""
    companion = db.get_companion(companion_id)
    if not companion:
        raise HTTPException(404, f"Companion {companion_id} not found")
    model_name = companion.get("model_name", "qwen3:14b")
    style = ollama.get_model_style(model_name)
    prompt = ollama.build_system_prompt(companion_id)
    state = db.get_companion_state(companion_id)
    return {
        "companion_id": companion_id,
        "model_name": model_name,
        "model_style": style,
        "state": state,
        "prompt": prompt,
        "prompt_length": len(prompt),
    }

@app.post("/api/chat/consolidate")
def maybe_consolidate(companionId: str, threshold: int = 20):
    try:
        n = ollama.maybe_auto_consolidate(companionId, threshold)
        return {"count": n}
    except Exception as e:
        return {"count": 0, "error": str(e)}

# ── Memory ────────────────────────────────────────────────────────

@app.get("/api/memory/{companion_id}")
def list_memories(companion_id: str):
    return db.list_memories(companion_id)

@app.post("/api/memory")
def add_memory(data: AddMemoryData):
    try:
        return db.add_memory(data.companionId, data.factText, data.category, data.importance)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.put("/api/memory")
def update_memory(data: UpdateMemoryData):
    try:
        db.update_memory(data.id, data.factText, data.category, data.importance)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}

@app.delete("/api/memory/{mid}")
def delete_memory(mid: str):
    db.delete_memory(mid)
    return {"ok": True}

@app.post("/api/memory/{mid}/promote")
def promote_to_identity(mid: str):
    db.promote_to_identity(mid)
    return {"ok": True}

@app.get("/api/memory/{companion_id}/counts")
def memory_counts(companion_id: str):
    return db.memory_category_counts(companion_id)

@app.post("/api/memory/{companion_id}/extract")
def extract_facts(companion_id: str):
    try:
        facts = ollama.extract_facts(companion_id)
        return {"facts": facts}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Summaries ─────────────────────────────────────────────────────

@app.post("/api/summaries")
def save_summary(data: SaveSummaryData):
    return db.save_session_summary(data.companionId, data.summary, data.emotionalTone, data.relationshipState)

@app.get("/api/summaries/{companion_id}")
def recent_summaries(companion_id: str, limit: int = 10):
    return db.recent_summaries(companion_id, limit)

# ── Diary ────────────────────────────────────────────────────────

@app.post("/api/diary")
def add_diary(data: AddDiaryData):
    try:
        return db.add_diary(data.companionId, data.content, data.moodTag)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/diary/{companion_id}")
def list_diary(companion_id: str):
    return db.list_diary(companion_id)

@app.delete("/api/diary/{did}")
def delete_diary(did: str):
    db.delete_diary(did)
    return {"ok": True}

# ── Art ──────────────────────────────────────────────────────────

@app.post("/api/art/generate")
def generate_image(data: ImageGenData):
    try:
        w, h = 1024, 1024
        if data.size:
            sizes = {"512x512": (512, 512), "768x768": (768, 768), "1024x1024": (1024, 1024)}
            w, h = sizes.get(data.size, (1024, 1024))
        return ollama.generate_image(data.companionId, data.prompt, data.model or "x/z-image-turbo", w, h, data.seed)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/art/quick")
def quick_art(data: SendMessageData):
    try:
        result = ollama.quick_art_from_chat(data.companionId, data.text, None)
        if not result:
            raise HTTPException(500, "Failed to generate art")
        return result
    except Exception as e:
        raise HTTPException(500, str(e))

class AvatarGenData(BaseModel):
    companionName: str
    archetype: str
    soul: str
    imageModel: Optional[str] = None
    size: str = "1024x1024"

@app.post("/api/art/avatar")
def generate_avatar(data: AvatarGenData):
    try:
        result = ollama.generate_avatar(data.companionName, data.archetype, data.soul, data.imageModel)
        if not result:
            raise HTTPException(500, "Avatar generation failed")
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


class ArtUploadData(BaseModel):
    companionId: str
    prompt: Optional[str] = ""
    base64: str
    filename: Optional[str] = None
    mime: Optional[str] = "image/png"


@app.post("/api/art/upload")
def upload_art(data: ArtUploadData):
    """Save an image (base64) as art for a companion.

    Used as a fallback when Ollama image generation isn't available, or when
    the user wants to bring their own art (photo, screenshot, etc.).
    """
    import base64, uuid as _uuid
    companion = db.get_companion(data.companionId)
    if not companion:
        raise HTTPException(404, "Companion not found")

    b64 = data.base64
    # Strip data URL prefix if present: "data:image/png;base64,XXXX"
    if "," in b64 and b64.lstrip().startswith("data:"):
        b64 = b64.split(",", 1)[1]

    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise HTTPException(400, "Invalid base64 image data")

    # Pick extension from MIME type
    mime = (data.mime or "image/png").lower()
    ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
               "image/gif": "gif", "image/webp": "webp"}
    ext = ext_map.get(mime, "png")

    # Detect actual magic bytes — trust the bytes, not the mime type
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = "png"
    elif raw.startswith(b"\xff\xd8\xff"):
        ext = "jpg"
    elif raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        ext = "gif"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        ext = "webp"

    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Image too large (25MB max)")

    art_dir = db.DATA_DIR / "art" / data.companionId
    art_dir.mkdir(parents=True, exist_ok=True)
    fname = art_dir / f"{_uuid.uuid4()}.{ext}"
    fname.write_bytes(raw)

    entry = db.add_art(
        data.companionId,
        (data.prompt or "Uploaded image").strip()[:500],
        str(fname),
        f"upload:{ext}",
        None, None, None,
    )
    return {
        "id": entry["id"],
        "file_path": str(fname),
        "model": f"upload:{ext}",
        "prompt": entry["prompt"],
        "width": None,
        "height": None,
    }


@app.get("/api/art/{companion_id}/history")
def art_history(companion_id: str):
    return db.get_art_history(companion_id)

@app.delete("/api/art/{aid}")
def delete_art(aid: str):
    db.delete_art(aid)
    return {"ok": True}

@app.get("/api/art/{aid}/image")
def read_art_image(aid: str, companion_id: str):
    """Return the art file directly (PNG or SVG) so the frontend <img src>
    can render it. Detects the content type from the file extension so SVG
    fallback art is served as image/svg+xml instead of image/png."""
    history = db.get_art_history(companion_id)
    art = next((a for a in history if a["id"] == aid), None)
    if not art:
        raise HTTPException(404, "Art not found")
    file_path = art["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(404, "Image file not found")
    ext = Path(file_path).suffix.lower()
    if ext == ".svg":
        media_type = "image/svg+xml"
    elif ext in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif ext == ".webp":
        media_type = "image/webp"
    elif ext == ".gif":
        media_type = "image/gif"
    else:
        media_type = "image/png"
    with open(file_path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type=media_type)


@app.post("/api/art/{aid}/reveal")
def reveal_art(aid: str, companion_id: str):
    """Reveal an art file in the OS file manager (Finder on macOS, Explorer
    on Windows, xdg-open on Linux). Right-click "Show in Finder" in the UI
    hits this endpoint. The companion_id is required for the ownership check
    (so users can't reveal other companions' art paths)."""
    import subprocess, sys as _sys
    history = db.get_art_history(companion_id)
    art = next((a for a in history if a["id"] == aid), None)
    if not art:
        raise HTTPException(404, "Art not found")
    file_path = art["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(404, "Image file not found")
    try:
        if _sys.platform == "darwin":
            # -R reveals the file in Finder (selects it)
            subprocess.Popen(["open", "-R", file_path])
        elif _sys.platform.startswith("win"):
            # /select, opens Explorer with the file highlighted
            subprocess.Popen(["explorer", f"/select,{file_path}"])
        else:
            # Linux: open the containing folder
            subprocess.Popen(["xdg-open", os.path.dirname(file_path)])
    except Exception as e:
        raise HTTPException(500, f"Failed to reveal file: {e}")
    return {"ok": True, "file_path": file_path}


@app.get("/api/art/{aid}/path")
def get_art_path(aid: str, companion_id: str):
    """Return the on-disk path of an art file. Used by the UI's right-click
    "Copy file path" action so the user can paste the full path into
    Finder's Go-To-Folder or a terminal."""
    history = db.get_art_history(companion_id)
    art = next((a for a in history if a["id"] == aid), None)
    if not art:
        raise HTTPException(404, "Art not found")
    return {"ok": True, "file_path": art["file_path"], "id": aid}


@app.post("/api/art/{aid}/open")
def open_art(aid: str, companion_id: str):
    """Open the art file in the user's default image viewer / browser.
    Right-click "Open" in the UI hits this. Different from reveal — reveal
    shows it in the file manager, open launches the actual viewer."""
    import subprocess, sys as _sys
    history = db.get_art_history(companion_id)
    art = next((a for a in history if a["id"] == aid), None)
    if not art:
        raise HTTPException(404, "Art not found")
    file_path = art["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(404, "Image file not found")
    try:
        if _sys.platform == "darwin":
            subprocess.Popen(["open", file_path])
        elif _sys.platform.startswith("win"):
            os.startfile(file_path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", file_path])
    except Exception as e:
        raise HTTPException(500, f"Failed to open file: {e}")
    return {"ok": True, "file_path": file_path}

@app.get("/api/avatar/{companion_id}")
def get_avatar(companion_id: str):
    """Return companion avatar as base64 data URL."""
    companion = db.get_companion(companion_id)
    if not companion:
        raise HTTPException(404, "Companion not found")
    avatar_path = companion.get("avatar_path", "")
    if not avatar_path or not os.path.exists(avatar_path):
        return {"base64": None, "url": None}
    import base64
    with open(avatar_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = os.path.splitext(avatar_path)[1].lower().strip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(ext, "image/png")
    return {"base64": b64, "url": f"data:{mime};base64,{b64}"}

# ── Soul ─────────────────────────────────────────────────────────

@app.get("/api/soul/{companion_id}")
def read_soul(companion_id: str):
    return {"markdown": ollama.read_soul(companion_id)}

@app.post("/api/soul/generate")
def generate_soul(inputs: SoulInputsData):
    try:
        return ollama.generate_soul(inputs.model_dump())
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/soul/score-ocean")
def score_ocean(quiz_answers: list[QuizAnswer]):
    return ollama.score_ocean([a.model_dump() for a in quiz_answers])

@app.post("/api/soul/write")
def write_soul(companionId: str, markdown: str):
    try:
        ollama.write_soul_md(companionId, markdown)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Art ↔ Memory bridge ──────────────────────────────────────────

class RememberArtData(BaseModel):
    companion_id: str
    note: Optional[str] = None


@app.post("/api/art/{aid}/remember")
def save_art_as_memory(aid: str, data: RememberArtData):
    try:
        return ollama.save_art_as_memory(data.companion_id, aid, data.note or "")
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Counts ───────────────────────────────────────────────────────

@app.get("/api/counts/{companion_id}")
def counts(companion_id: str):
    return {
        "memory": db.memory_count(companion_id),
        "diary": db.diary_count(companion_id),
        "message": db.message_count(companion_id),
        "art": db.art_count(companion_id),
    }

# ── Quiz constants ───────────────────────────────────────────────

@app.get("/api/quiz-constants")
def quiz_constants():
    return {
        "questions": [
            {"id": "q-0", "trait_letter": "O", "text": "I have a vivid imagination and love exploring new ideas.", "reverse": False},
            {"id": "q-1", "trait_letter": "O", "text": "I prefer routine over spontaneity.", "reverse": True},
            {"id": "q-2", "trait_letter": "C", "text": "I am highly organized and always keep my promises.", "reverse": False},
            {"id": "q-3", "trait_letter": "C", "text": "I sometimes leave things to the last minute.", "reverse": True},
            {"id": "q-4", "trait_letter": "E", "text": "I gain energy from being around people.", "reverse": False},
            {"id": "q-5", "trait_letter": "E", "text": "I prefer quiet environments to recharge.", "reverse": True},
            {"id": "q-6", "trait_letter": "A", "text": "I trust others easily and enjoy cooperation.", "reverse": False},
            {"id": "q-7", "trait_letter": "A", "text": "I tend to be skeptical of strangers.", "reverse": True},
            {"id": "q-8", "trait_letter": "N", "text": "I remain calm under pressure.", "reverse": False},
            {"id": "q-9", "trait_letter": "N", "text": "I often worry about things I cannot control.", "reverse": True},
        ],
        "archetypes": [
            {"id": "mentor", "label": "The Mentor — wise, guiding, patient"},
            {"id": "nurturer", "label": "The Nurturer — warm, caring, protective"},
            {"id": "rebel", "label": "The Rebel — bold, unconventional, free-spirited"},
            {"id": "creator", "label": "The Creator — imaginative, artistic, expressive"},
            {"id": "explorer", "label": "The Explorer — curious, adventurous, independent"},
            {"id": "innocent", "label": "The Innocent — pure, hopeful, joyful"},
            {"id": "sage", "label": "The Sage — thoughtful, analytical, insightful"},
            {"id": "jester", "label": "The Jester — playful, witty, fun-loving"},
            {"id": "lover", "label": "The Lover — passionate, devoted, charismatic"},
            {"id": "ruler", "label": "The Ruler — authoritative, responsible, protective"},
        ],
        "pronouns": [
            {"id": "he/him", "label": "He/Him"},
            {"id": "she/her", "label": "She/Her"},
            {"id": "they/them", "label": "They/Them"},
            {"id": "it/its", "label": "It/Its"},
        ],
        "age_brackets": [
            {"id": "young-adult", "label": "Young Adult (18-25)"},
            {"id": "adult", "label": "Adult (26-40)"},
            {"id": "middle-aged", "label": "Middle-Aged (41-55)"},
            {"id": "mature", "label": "Mature (55+)"},
            {"id": "ageless", "label": "Ageless / Timeless"},
        ],
        "voice_packs": [
            {"id": "af_heart", "name": "Af_heart", "language": "en", "gender": "female"},
            {"id": "af_bella", "name": "Af_bella", "language": "en", "gender": "female"},
            {"id": "af_nova", "name": "Af_nova", "language": "en", "gender": "female"},
            {"id": "af_sarah", "name": "Af_sarah", "language": "en", "gender": "female"},
            {"id": "am_adam", "name": "Am_adam", "language": "en", "gender": "male"},
            {"id": "am_michael", "name": "Am_michael", "language": "en", "gender": "male"},
            {"id": "bf_emma", "name": "Bf_emma", "language": "en", "gender": "female"},
            {"id": "bm_george", "name": "Bm_george", "language": "en", "gender": "male"},
            {"id": "jf_alpha", "name": "Jf_alpha", "language": "ja", "gender": "female"},
            {"id": "zf_xiaoxiao", "name": "Zf_xiaoxiao", "language": "zh", "gender": "female"},
        ],
    }


# ── Static file serving (React UI) ───────────────────────────────

@app.get("/")
def serve_index():
    """Serve the React app."""
    index_path = DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"error": "UI not built. Run: pnpm build"}

@app.get("/{path:path}")
def serve_static(path: str):
    """Serve static assets from dist/, with src-ui-public/ as a fallback for icons etc."""
    # First try the bundled dist (frontend assets, hashed JS/CSS)
    file_path = DIST_DIR / path
    if file_path.is_file():
        return FileResponse(str(file_path))
    # Then the bundled src-ui-public dir (icons, brand SVG) — flattened
    # because PyInstaller bundles a renamed dir to avoid colliding with the
    # real src-ui/ on the dev box.
    public_path = PUBLIC_DIR / path
    if public_path.is_file():
        return FileResponse(str(public_path))
    # Dev-only fallback: also try the real src-ui/public/ path
    if not getattr(sys, "frozen", False):
        dev_public = Path(__file__).resolve().parent.parent / "src-ui" / "public" / path
        if dev_public.is_file():
            return FileResponse(str(dev_public))
    # Fallback to index.html for SPA routing
    index_path = DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"error": f"File not found: {path}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18765, log_level="warning")
