"""
SQLite database layer for OurNook.
mirrors nook-core/src/memory.rs schema.
"""
import sqlite3, json, uuid, os, platform, threading
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

def _get_data_dir() -> Path:
    """Cross-platform app data directory."""
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        base = home / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
    else:
        base = home / ".local" / "share"
    return base / "OurNook"

DATA_DIR = _get_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "companions.db"


def get_db() -> sqlite3.Connection:
    """Open a connection with safe defaults.

    - Foreign-key enforcement is opt-in per-connection (PRAGMA foreign_keys = ON).
    - WAL mode is enabled on first connection for better concurrent reads.
    - Row factory returns sqlite3.Row (dict-like) for ergonomic access.
    - `check_same_thread=False` because FastAPI's threadpool may share the conn.
      Note: our use is mostly read-after-write within a single request, and
      writes are short transactions. We serialize hot writes via a module-level
      lock where needed.
    """
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Enable WAL mode + busy_timeout on first connection. WAL gives concurrent
# readers much better performance and avoids "database is locked" errors when
# a long read overlaps a quick write. safe to call multiple times.
_WAL_ENABLED = False
_WAL_LOCK = threading.Lock()


def _enable_wal_once():
    global _WAL_ENABLED
    with _WAL_LOCK:
        if _WAL_ENABLED:
            return
        try:
            conn = get_db()
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")  # safe with WAL, much faster
            conn.execute("PRAGMA busy_timeout = 5000")  # 5s instead of default ~1s
            conn.close()
            _WAL_ENABLED = True
        except Exception:
            pass  # never let WAL setup break the app


_enable_wal_once()


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS companions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        avatar_path TEXT,
        backstory TEXT,
        personality TEXT,
        voice_config TEXT,
        memory_mode TEXT DEFAULT 'hybrid',
        model_name TEXT DEFAULT 'qwen3:14b',
        relationship_type TEXT DEFAULT 'friend',
        soul_path TEXT,
        enneagram_type INTEGER,
        enneagram_wing INTEGER,
        enneagram_instinct TEXT,
        enneagram_health TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        starred INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS messages_fts (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        starred INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts_idx
    USING fts5(id UNINDEXED, companion_id UNINDEXED, role UNINDEXED, content, starred UNINDEXED, created_at UNINDEXED,
               content='messages', content_rowid='rowid');

    CREATE TABLE IF NOT EXISTS session_summaries (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        emotional_tone TEXT,
        relationship_state TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS semantic_memories (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        fact_text TEXT NOT NULL,
        category TEXT,
        importance INTEGER DEFAULT 5,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS journal_entries (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        content TEXT NOT NULL,
        keyphrases TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS diary_entries (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        content TEXT NOT NULL,
        mood_tag TEXT,
        companion_read_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS art_entries (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        prompt TEXT NOT NULL,
        negative_prompt TEXT,
        model TEXT,
        seed INTEGER,
        width INTEGER DEFAULT 1024,
        height INTEGER DEFAULT 1024,
        steps INTEGER,
        file_path TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_messages_companion ON messages(companion_id);
    CREATE INDEX IF NOT EXISTS idx_memories_companion ON semantic_memories(companion_id);
    CREATE INDEX IF NOT EXISTS idx_summaries_companion ON session_summaries(companion_id);
    CREATE INDEX IF NOT EXISTS idx_diary_companion ON diary_entries(companion_id);
    CREATE INDEX IF NOT EXISTS idx_art_companion ON art_entries(companion_id);

    -- ── v0.12 Inner Life ──────────────────────────────────────────
    -- companion_state: per-companion persistent state — mood, last-seen,
    -- streak, message counts. Injected into the system prompt so the
    -- companion has continuity across sessions.
    CREATE TABLE IF NOT EXISTS companion_state (
        companion_id TEXT PRIMARY KEY,
        current_mood TEXT,
        last_mood_at TEXT,
        last_seen_at TEXT,
        last_conversation_at TEXT,
        total_messages INTEGER DEFAULT 0,
        total_conversations INTEGER DEFAULT 0,
        streak_days INTEGER DEFAULT 0,
        last_streak_date TEXT,
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );

    -- companion_journal: the companion's private thoughts. Visible to it
    -- in the system prompt, optionally visible to the user in the UI.
    CREATE TABLE IF NOT EXISTS companion_journal (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        content TEXT NOT NULL,
        mood TEXT,
        related_message_id TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_journal_companion ON companion_journal(companion_id, created_at DESC);

    -- companion_moments: episodic memory — special conversation moments
    -- the companion wants to remember (distinct from facts about the user).
    CREATE TABLE IF NOT EXISTS companion_moments (
        id TEXT PRIMARY KEY,
        companion_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        related_message_id TEXT,
        significance INTEGER DEFAULT 5,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (companion_id) REFERENCES companions(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_moments_companion ON companion_moments(companion_id, created_at DESC);
    """)
    conn.commit()

    # v0.15 — Enneagram columns. ALTER TABLE ADD COLUMN has no IF NOT
    # EXISTS in SQLite, so we check PRAGMA table_info and add only the
    # missing ones. Safe to re-run on fresh and existing DBs.
    _existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(companions)").fetchall()}
    if "enneagram_type" not in _existing_cols:
        conn.execute("ALTER TABLE companions ADD COLUMN enneagram_type INTEGER")
    if "enneagram_wing" not in _existing_cols:
        conn.execute("ALTER TABLE companions ADD COLUMN enneagram_wing INTEGER")
    if "enneagram_instinct" not in _existing_cols:
        conn.execute("ALTER TABLE companions ADD COLUMN enneagram_instinct TEXT")
    if "enneagram_health" not in _existing_cols:
        conn.execute("ALTER TABLE companions ADD COLUMN enneagram_health TEXT")
    conn.commit()
    conn.close()
    _ensure_bundled_companions()


def _ensure_bundled_companions():
    """Seed Mira, Sable, Finn if DB is empty."""
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*) FROM companions")
    if cur.fetchone()[0] > 0:
        conn.close()
        return
    conn.close()

    bundled = [
        ("mira", "Mira", "Mira is a warm, curious soul who sees the world in colour and connection. She's the friend who remembers how you take your coffee, notices when you're quiet, and fills silences without filling them with noise.", "Open, curious, warm, empathetic — the friend who makes everything feel a little less heavy.", "af_bella", "A cozy evening, a cup of tea, and the quiet comfort of being truly seen."),
        ("sable", "Sable", "Sable moves through the world with quiet intensity. Sharp observations, dry wit, and a surprising tenderness underneath. Not loud, not clingy — just *present*.", "Guarded, perceptive, dry-humoured, deeply loyal once trust is earned.", "am_adam", "The warmth of a hand on your shoulder when you didn't ask for it."),
        ("finn", "Finn", "Finn is sunshine in human form — bright, optimistic, always finding something to be excited about. The friend who texts you pictures of clouds that look like rabbits.", "Extraverted, enthusiastic, playful, eternally optimistic.", "bm_george", "A perfect moment you didn't know you needed."),
    ]

    conn = get_db()
    for cid, name, backstory, personality, voice, hook in bundled:
        companion_id = str(uuid.uuid4())
        soul_path = DATA_DIR / "companions" / companion_id / "soul.md"
        soul_path.parent.mkdir(parents=True, exist_ok=True)
        soul_content = f"# {name}\n\n**{hook}**\n\n## Who They Are\n\n{backstory}\n\n## How They Talk\n\n{personality}"
        soul_path.write_text(soul_content)
        avatar_dir = DATA_DIR / "companions" / companion_id
        avatar_dir.mkdir(parents=True, exist_ok=True)
        conn.execute("""
            INSERT INTO companions (id, name, backstory, personality, voice_config, soul_path, model_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (companion_id, name, backstory, personality, json.dumps({"voice_id": voice}), str(soul_path), "qwen3:14b"))
    conn.commit()
    conn.close()


# ── Companion CRUD ────────────────────────────────────────────────

@dataclass
class Companion:
    id: str
    name: str
    avatar_path: Optional[str]
    backstory: str
    personality: str
    voice_config: Optional[str]
    memory_mode: str
    model_name: str
    relationship_type: str
    enneagram_type: Optional[int]
    enneagram_wing: Optional[int]
    enneagram_instinct: Optional[str]
    enneagram_health: Optional[str]
    created_at: str
    updated_at: str

def list_companions() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM companions ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_companion(cid: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM companions WHERE id = ?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_companion(cid: str, fields: dict) -> Optional[dict]:
    """Update a companion's editable fields. Only the supplied keys are touched."""
    allowed = {"name", "backstory", "personality", "voice_config", "memory_mode",
               "enneagram_type", "enneagram_wing", "enneagram_instinct", "enneagram_health",
               "model_name", "relationship_type"}
    sets = []
    values = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            values.append(v)
    if not sets:
        return get_companion(cid)
    sets.append("updated_at=datetime('now')")
    values.append(cid)
    conn = get_db()
    conn.execute(f"UPDATE companions SET {', '.join(sets)} WHERE id=?", values)
    conn.commit()
    conn.close()
    return get_companion(cid)

def create_companion(data: dict) -> dict:
    cid = str(uuid.uuid4())
    conn = get_db()
    avatar_path = data.get("avatar_path")
    voice_config = data.get("voice_config")
    soul_path = DATA_DIR / "companions" / cid / "soul.md"
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(f"# {data['name']}\n\n*A new soul.*")
    conn.execute("""
        INSERT INTO companions (id, name, avatar_path, backstory, personality, voice_config,
            memory_mode, model_name, relationship_type, soul_path,
            enneagram_type, enneagram_wing, enneagram_instinct, enneagram_health)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cid, data["name"], avatar_path, data.get("backstory",""), data.get("personality",""),
          voice_config, data.get("memory_mode","hybrid"), data.get("model_name","qwen3:14b"),
          data.get("relationship_type","friend"), str(soul_path),
          data.get("enneagram_type"), data.get("enneagram_wing"),
          data.get("enneagram_instinct"), data.get("enneagram_health")))
    conn.commit()
    conn.close()
    return get_companion(cid)

def delete_companion(cid: str):
    conn = get_db()
    conn.execute("DELETE FROM companions WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    # Clean up filesystem
    companion_dir = DATA_DIR / "companions" / cid
    art_dir = DATA_DIR / "art" / cid
    for d in [companion_dir, art_dir]:
        import shutil
        if d.exists():
            shutil.rmtree(d)

# ── Messages ─────────────────────────────────────────────────────

@dataclass
class Message:
    id: str
    companion_id: str
    role: str
    content: str
    starred: bool
    created_at: str

def recent_messages(companion_id: str, limit: int = 100) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE companion_id = ? ORDER BY created_at DESC LIMIT ?",
        (companion_id, limit)
    ).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    result.reverse()
    return result

def add_message(companion_id: str, role: str, content: str) -> dict:
    mid = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (id, companion_id, role, content) VALUES (?, ?, ?, ?)",
        (mid, companion_id, role, content)
    )
    conn.commit()
    conn.close()
    return {"id": mid, "companion_id": companion_id, "role": role, "content": content, "starred": False, "created_at": datetime.now().isoformat()}


def delete_message(mid: str) -> bool:
    """Delete a single message by id. Returns True if it existed."""
    conn = get_db()
    cur = conn.execute("DELETE FROM messages WHERE id = ?", (mid,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def delete_messages_after(companion_id: str, after_id: str) -> int:
    """Delete all messages for a companion whose created_at is >= the message with
    `after_id`. Used by edit-resend and regenerate to roll back the conversation
    past a chosen anchor. Returns the number of messages removed."""
    conn = get_db()
    anchor = conn.execute(
        "SELECT created_at FROM messages WHERE id = ? AND companion_id = ?",
        (after_id, companion_id),
    ).fetchone()
    if not anchor:
        conn.close()
        return 0
    cur = conn.execute(
        "DELETE FROM messages WHERE companion_id = ? AND created_at >= ?",
        (companion_id, anchor["created_at"]),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def update_message_content(mid: str, content: str) -> bool:
    """Edit a message's content. Returns True if it existed."""
    conn = get_db()
    cur = conn.execute(
        "UPDATE messages SET content = ? WHERE id = ?",
        (content, mid),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n > 0


def get_message(mid: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ── Memory ────────────────────────────────────────────────────────

def list_memories(companion_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM semantic_memories WHERE companion_id = ? ORDER BY importance DESC, created_at DESC",
        (companion_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_memory(companion_id: str, fact_text: str, category: Optional[str], importance: int = 5) -> dict:
    """Insert a semantic memory. Raises ValueError on empty/whitespace facts.

    Importance is clamped to the valid range 1–10:
      - 1-4:  minor fact
      - 5-9:  significant
      - 10:   identity-defining (auto-injected into every chat's system prompt)
    """
    if not fact_text or not fact_text.strip():
        raise ValueError("Memory text cannot be empty or whitespace-only")
    if not isinstance(importance, int):
        try:
            importance = int(importance)
        except (TypeError, ValueError):
            importance = 5
    importance = max(1, min(10, importance))  # clamp 1..10

    mid = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO semantic_memories (id, companion_id, fact_text, category, importance) VALUES (?, ?, ?, ?, ?)",
        (mid, companion_id, fact_text.strip(), (category or "").strip() or None, importance)
    )
    conn.commit()
    conn.close()
    return {"id": mid, "companion_id": companion_id, "fact_text": fact_text, "category": category, "importance": importance, "created_at": datetime.now().isoformat()}

def update_memory(mid: str, fact_text: str, category: Optional[str], importance: int):
    """Update a memory. Raises ValueError on empty/whitespace facts. Clamps importance 1-10."""
    if not fact_text or not fact_text.strip():
        raise ValueError("Memory text cannot be empty or whitespace-only")
    if not isinstance(importance, int):
        try:
            importance = int(importance)
        except (TypeError, ValueError):
            importance = 5
    importance = max(1, min(10, importance))

    conn = get_db()
    conn.execute("UPDATE semantic_memories SET fact_text=?, category=?, importance=? WHERE id=?",
                 (fact_text.strip(), (category or "").strip() or None, importance, mid))
    conn.commit()
    conn.close()

def delete_memory(mid: str):
    conn = get_db()
    conn.execute("DELETE FROM semantic_memories WHERE id = ?", (mid,))
    conn.commit()
    conn.close()

def promote_to_identity(mid: str):
    conn = get_db()
    conn.execute("UPDATE semantic_memories SET importance=10 WHERE id=?", (mid,))
    conn.commit()
    conn.close()

def memory_category_counts(companion_id: str) -> dict:
    conn = get_db()
    rows = conn.execute("""
        SELECT category, COUNT(*) as count FROM semantic_memories
        WHERE companion_id = ? GROUP BY category
    """, (companion_id,)).fetchall()
    conn.close()
    return {r["category"] or "uncategorized": r["count"] for r in rows}

# ── Session Summaries ─────────────────────────────────────────────

def save_session_summary(companion_id: str, summary: str, emotional_tone: Optional[str], relationship_state: Optional[str]) -> dict:
    sid = str(uuid.uuid4())
    conn = get_db()
    conn.execute("""
        INSERT INTO session_summaries (id, companion_id, summary, emotional_tone, relationship_state)
        VALUES (?, ?, ?, ?, ?)
    """, (sid, companion_id, summary, emotional_tone, relationship_state))
    conn.commit()
    conn.close()
    return {"id": sid, "companion_id": companion_id, "summary": summary, "emotional_tone": emotional_tone, "relationship_state": relationship_state, "created_at": datetime.now().isoformat()}

def recent_summaries(companion_id: str, limit: int = 10) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM session_summaries WHERE companion_id = ? ORDER BY created_at DESC LIMIT ?",
        (companion_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Diary ─────────────────────────────────────────────────────────

def add_diary(companion_id: str, content: str, mood_tag: Optional[str]) -> dict:
    """Add a diary entry. Raises ValueError on empty/whitespace content."""
    if not content or not content.strip():
        raise ValueError("Diary content cannot be empty or whitespace-only")
    content = content.strip()
    mood_tag = (mood_tag or "").strip() or None

    did = str(uuid.uuid4())
    conn = get_db()
    conn.execute("INSERT INTO diary_entries (id, companion_id, content, mood_tag) VALUES (?, ?, ?, ?)",
                 (did, companion_id, content, mood_tag))
    conn.commit()
    conn.close()
    return {"id": did, "companion_id": companion_id, "content": content, "mood_tag": mood_tag, "companion_read_at": None, "created_at": datetime.now().isoformat()}

def list_diary(companion_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM diary_entries WHERE companion_id = ? ORDER BY created_at DESC", (companion_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_diary(did: str):
    conn = get_db()
    conn.execute("DELETE FROM diary_entries WHERE id = ?", (did,))
    conn.commit()
    conn.close()

# ── Art ───────────────────────────────────────────────────────────

def add_art(companion_id: str, prompt: str, file_path: str, model: str, seed: Optional[int], width: int, height: int) -> dict:
    aid = str(uuid.uuid4())
    conn = get_db()
    conn.execute("""
        INSERT INTO art_entries (id, companion_id, prompt, file_path, model, seed, width, height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (aid, companion_id, prompt, file_path, model, seed, width, height))
    conn.commit()
    conn.close()
    return {"id": aid, "companion_id": companion_id, "prompt": prompt, "file_path": file_path, "model": model,
            "seed": seed, "width": width, "height": height, "created_at": datetime.now().isoformat()}

def get_art_history(companion_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM art_entries WHERE companion_id = ? ORDER BY created_at DESC", (companion_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_art(aid: str):
    conn = get_db()
    conn.execute("DELETE FROM art_entries WHERE id = ?", (aid,))
    conn.commit()
    conn.close()

# ── Counts ────────────────────────────────────────────────────────

def memory_count(companion_id: str) -> int:
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*) FROM semantic_memories WHERE companion_id = ?", (companion_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def diary_count(companion_id: str) -> int:
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*) FROM diary_entries WHERE companion_id = ?", (companion_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def message_count(companion_id: str) -> int:
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*) FROM messages WHERE companion_id = ?", (companion_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def art_count(companion_id: str) -> int:
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*) FROM art_entries WHERE companion_id = ?", (companion_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count


# ── Inner Life (v0.12) ───────────────────────────────────────────
# These power the companion's continuity — mood, last-seen, streak,
# private journal, special moments. All injected into build_system_prompt
# so the companion has a real sense of "who I am right now" and
# "what's been happening since we last talked."

def get_companion_state(companion_id: str) -> dict:
    """Return the companion's state, creating an empty row if missing.
    All datetime fields are returned as ISO strings."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM companion_state WHERE companion_id = ?", (companion_id,)
    ).fetchone()
    if not row:
        # Lazy-create with defaults so callers never have to handle missing
        conn.execute(
            "INSERT INTO companion_state (companion_id) VALUES (?)", (companion_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM companion_state WHERE companion_id = ?", (companion_id,)
        ).fetchone()
    conn.close()
    return dict(row) if row else {}


def update_companion_mood(companion_id: str, mood: str) -> dict:
    """Set the companion's current mood. Empty string clears it."""
    mood = (mood or "").strip()
    get_companion_state(companion_id)  # ensure row exists
    conn = get_db()
    conn.execute(
        "UPDATE companion_state SET current_mood = ?, last_mood_at = datetime('now') WHERE companion_id = ?",
        (mood or None, companion_id),
    )
    conn.commit()
    conn.close()
    return get_companion_state(companion_id)


def bump_last_seen(companion_id: str) -> dict:
    """Bump last_seen_at + increment total_messages + update streak.
    Called on every chat send. Streak rules:
      - If last_conversation_at was yesterday: streak += 1
      - If last_conversation_at was today: streak unchanged
      - If last_conversation_at was >1 day ago: streak resets to 1
      - If never chatted before: streak = 1
    Also increments total_conversations only on the first message of a
    new conversation (gap > 30 min counts as a new conversation).

    IMPORTANT: SQLite's datetime('now') returns UTC. We must use datetime.utcnow()
    in Python for the time delta comparison, otherwise local-timezone offsets
    cause every send to look like > 30 min apart (the conversation counter
    increments per send instead of per real conversation)."""
    state = get_companion_state(companion_id)
    conn = get_db()
    # Bump message count by 1 (the user message that was just sent)
    new_total_msgs = (state.get("total_messages") or 0) + 1

    # Always use UTC to match what SQLite's datetime('now') stores.
    now_utc = datetime.utcnow()

    # Streak logic — use the UTC date so it matches the stored YYYY-MM-DD.
    today = now_utc.strftime("%Y-%m-%d")
    last_streak_date = state.get("last_streak_date")
    streak = state.get("streak_days") or 0
    if last_streak_date == today:
        new_streak = streak  # already counted today
    elif last_streak_date:
        try:
            last_dt = datetime.strptime(last_streak_date, "%Y-%m-%d").date()
            today_dt = datetime.strptime(today, "%Y-%m-%d").date()
            if (today_dt - last_dt).days == 1:
                new_streak = streak + 1
            else:
                new_streak = 1  # broke the streak
        except ValueError:
            new_streak = 1
    else:
        new_streak = 1  # first chat

    # New conversation? Gap > 30 min since last conversation.
    # The DB stores UTC timestamps without a 'Z' suffix (legacy: SQLite
    # datetime('now') returns 'YYYY-MM-DD HH:MM:SS' in UTC). Treat naive
    # strings as UTC when parsing.
    new_conv = False
    last_conv = state.get("last_conversation_at")
    if last_conv:
        try:
            # Strip a trailing Z if present, then treat as UTC.
            lc = last_conv.rstrip("Z")
            last_conv_dt = datetime.fromisoformat(lc)
            # If the timestamp is naive (no tzinfo), assume UTC
            if last_conv_dt.tzinfo is None:
                last_conv_dt = last_conv_dt.replace(tzinfo=timezone.utc).replace(tzinfo=None)
            delta_s = (now_utc - last_conv_dt).total_seconds()
            if delta_s > 30 * 60:
                new_conv = True
        except (ValueError, TypeError):
            new_conv = True
    else:
        new_conv = True
    new_total_convs = (state.get("total_conversations") or 0) + (1 if new_conv else 0)

    conn.execute("""
        UPDATE companion_state SET
            last_seen_at = datetime('now'),
            last_conversation_at = datetime('now'),
            total_messages = ?,
            total_conversations = ?,
            streak_days = ?,
            last_streak_date = ?
        WHERE companion_id = ?
    """, (new_total_msgs, new_total_convs, new_streak, today, companion_id))
    conn.commit()
    conn.close()
    return get_companion_state(companion_id)


# ── Companion journal (private thoughts) ──────────────────────────

def add_journal_entry(companion_id: str, content: str, mood: Optional[str] = None, related_message_id: Optional[str] = None) -> dict:
    """Add a private journal entry for the companion. Used by the user
    to write the companion's own thoughts, OR by the auto-extract flow
    to record what the companion is feeling after a session."""
    content = (content or "").strip()
    if not content:
        raise ValueError("Journal entry cannot be empty")
    if len(content) > 5000:
        raise ValueError("Journal entry too long (5000 char max)")
    eid = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO companion_journal (id, companion_id, content, mood, related_message_id) VALUES (?, ?, ?, ?, ?)",
        (eid, companion_id, content, mood, related_message_id),
    )
    conn.commit()
    conn.close()
    return {"id": eid, "companion_id": companion_id, "content": content, "mood": mood, "related_message_id": related_message_id, "created_at": datetime.now().isoformat()}


def list_journal(companion_id: str, limit: int = 20) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM companion_journal WHERE companion_id = ? ORDER BY created_at DESC LIMIT ?",
        (companion_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_journal_entry(eid: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM companion_journal WHERE id = ?", (eid,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# ── Companion moments (episodic memory) ──────────────────────────

def add_moment(companion_id: str, title: str, description: Optional[str] = None, related_message_id: Optional[str] = None, significance: int = 5) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("Moment title cannot be empty")
    if significance < 1 or significance > 10:
        raise ValueError("Significance must be 1-10")
    mid = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO companion_moments (id, companion_id, title, description, related_message_id, significance) VALUES (?, ?, ?, ?, ?, ?)",
        (mid, companion_id, title, description, related_message_id, significance),
    )
    conn.commit()
    conn.close()
    return {"id": mid, "companion_id": companion_id, "title": title, "description": description, "related_message_id": related_message_id, "significance": significance, "created_at": datetime.now().isoformat()}


def list_moments(companion_id: str, limit: int = 20) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM companion_moments WHERE companion_id = ? ORDER BY significance DESC, created_at DESC LIMIT ?",
        (companion_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_moment(mid: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM companion_moments WHERE id = ?", (mid,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# ── Diary-as-letter (mark diary as read by companion) ────────────

def list_unread_diary(companion_id: str, limit: int = 5) -> list[dict]:
    """Diary entries the user wrote that the companion hasn't 'read' yet.
    On the next chat send, we auto-mark all of these as read AND inject
    them into the system prompt so the companion can naturally reference
    them. This is the loop that makes the diary feel like a real letter."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM diary_entries WHERE companion_id = ? AND companion_read_at IS NULL ORDER BY created_at DESC LIMIT ?",
        (companion_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_diary_read(companion_id: str) -> int:
    """Mark all unread diary entries for this companion as read.
    Called automatically at the start of each chat send."""
    conn = get_db()
    cur = conn.execute(
        "UPDATE diary_entries SET companion_read_at = datetime('now') WHERE companion_id = ? AND companion_read_at IS NULL",
        (companion_id,),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def mark_diary_read_one(did: str) -> bool:
    conn = get_db()
    cur = conn.execute(
        "UPDATE diary_entries SET companion_read_at = datetime('now') WHERE id = ? AND companion_read_at IS NULL",
        (did,),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n > 0
