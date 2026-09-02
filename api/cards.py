"""
SillyTavern character card format — import / export for OurNook.

Standard format (v1/v2 fields; we use v2):
{
  "name": "...",
  "description": "...",   // ← backstory
  "personality": "...",  // ← our personality
  "scenario": "...",
  "first_mes": "...",    // ← first message
  "mes_example": "...",  // ← example dialogues (newline-separated)
  "system_prompt": "...",
  "post_history_instructions": "...",
  "alternate_greetings": [...],
  "tags": [...],
  "creator": "...",
  "character_version": "...",
  "extensions": {
    "nook": {
      "memory_mode": "auto",
      "relationship_type": "friend",
      "voice_config": {...},
      "model_name": "qwen3:14b"
    }
  }
}

PNG cards embed this as a tEXt chunk with keyword "chara" (base64-encoded JSON).
"""
import json
import base64
import struct
import zlib
import re
from pathlib import Path
from typing import Optional
from . import db, ollama


# ── Soul parsing ────────────────────────────────────────────────

def parse_soul_md(soul_text: str) -> dict:
    """Pull structured fields from a soul.md written by the wizard.

    The wizard writes:
      # Name
      **tagline**
      ## Who They Are
      <backstory>
      ## How They Talk
      <personality>
      ## What They Care About
      <scenario/likes>
      ## What They Fear
      <fears>
      ## Contradictions
      <contradictions>
      ## Current Struggle
      <struggle>
      ## Growth Arc
      <arc>
    """
    out = {"tagline": "", "backstory": "", "personality": "", "scenario": "", "fears": "",
           "contradictions": "", "current_struggle": "", "growth_arc": ""}
    if not soul_text:
        return out
    lines = soul_text.splitlines()
    section = None
    buf: list[str] = []
    name_from_h1 = ""
    for ln in lines:
        h = ln.strip()
        if h.startswith("# ") and not h.startswith("## "):
            name_from_h1 = h[2:].strip()
            section = None
            continue
        if h.startswith("**") and h.endswith("**"):
            out["tagline"] = h.strip("*").strip()
            continue
        if h.startswith("## "):
            if section and buf:
                out[section] = "\n".join(buf).strip()
            section = h[3:].strip().lower()
            buf = []
            continue
        if section:
            buf.append(ln)
    if section and buf:
        out[section] = "\n".join(buf).strip()
    out["name_from_h1"] = name_from_h1
    return out


def soul_md_from_card(card: dict) -> str:
    """Reverse: take a parsed card, write a soul.md in our wizard format."""
    name = card.get("name", "Unnamed")
    tagline = card.get("tagline") or card.get("description", "")[:120]
    parts = [f"# {name}", "", f"**{tagline}**", ""]
    sections = [
        ("Who They Are", "description"),
        ("How They Talk", "personality"),
        ("What They Care About", "scenario"),
        ("What They Fear", "fears"),
        ("Contradictions", "contradictions"),
        ("Current Struggle", "current_struggle"),
        ("Growth Arc", "growth_arc"),
    ]
    for label, key in sections:
        val = card.get(key, "").strip()
        if val:
            parts += [f"## {label}", "", val, ""]
    return "\n".join(parts).rstrip() + "\n"


# ── SillyTavern format ──────────────────────────────────────────

def companion_to_card(companion_id: str) -> dict:
    """Build a SillyTavern-compatible card from a companion."""
    c = db.get_companion(companion_id)
    if not c:
        raise ValueError(f"Companion {companion_id} not found")

    soul_text = ""
    if c.get("soul_path") and Path(c["soul_path"]).exists():
        soul_text = Path(c["soul_path"]).read_text()

    soul = parse_soul_md(soul_text)
    personality = soul["personality"] or c.get("personality", "")
    description = soul["backstory"] or c.get("backstory", "")
    scenario = soul["scenario"] or ""

    first_mes = ""
    messages = db.recent_messages(companion_id, limit=50)
    for m in messages:
        if m["role"] == "assistant":
            first_mes = m["content"]
            break

    example_lines: list[str] = []
    if messages:
        for i in range(0, min(6, len(messages) - 1), 2):
            u = messages[i]
            a = messages[i + 1] if i + 1 < len(messages) else None
            if u["role"] == "user" and a and a["role"] == "assistant":
                example_lines.append(f"<START>\n{u['content']}\n{a['content']}\n<END>")
    mes_example = "\n".join(example_lines)

    voice_cfg = None
    if c.get("voice_config"):
        try: voice_cfg = json.loads(c["voice_config"])
        except Exception: pass

    return {
        "name": c["name"],
        "description": description,
        "personality": personality,
        "scenario": scenario,
        "first_mes": first_mes,
        "mes_example": mes_example,
        "system_prompt": soul_text,
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": [c.get("relationship_type", "friend"), c.get("memory_mode", "hybrid")],
        "creator": "OurNook",
        "character_version": "1",
        "extensions": {
            "nook": {
                "memory_mode": c.get("memory_mode", "hybrid"),
                "relationship_type": c.get("relationship_type", "friend"),
                "model_name": c.get("model_name", "qwen3:14b"),
                "voice_config": voice_cfg,
                "tagline": soul.get("tagline", ""),
            },
        },
    }


def card_to_companion(card: dict) -> dict:
    """Turn a SillyTavern card into OurNook companion fields. Returns a dict ready for db.create_companion."""
    name = (card.get("name") or "").strip()
    description = (card.get("description") or "").strip()
    personality = (card.get("personality") or "").strip()
    scenario = (card.get("scenario") or "").strip()
    first_mes = card.get("first_mes", "")
    mes_example = card.get("mes_example", "")
    system_prompt = card.get("system_prompt", "")

    # If the card has literally no name, try to use the description or fallback
    if not name:
        if description:
            # Use first line of description, capped
            name = description.split("\n")[0][:50].strip() or "Imported"
        else:
            name = "Imported"

    # Reject cards with no meaningful content at all — otherwise users
    # can spam-create empty companions by pasting `{}`.
    has_content = any([name != "Imported", description, personality, scenario, system_prompt])
    if not has_content:
        raise ValueError("Card has no content (missing name, description, personality, and system_prompt)")

    ext = card.get("extensions", {}) or {}
    nook_ext = ext.get("nook", {}) or {}

    # Build personality if blank — fall back to description
    if not personality and description:
        personality = description[:200]

    # Build a soul.md from the card (unless system_prompt is already soul-shaped)
    if system_prompt and system_prompt.lstrip().startswith("# "):
        soul_text = system_prompt
    else:
        soul_text = soul_md_from_card({
            "name": name,
            "tagline": nook_ext.get("tagline", "") or description[:120],
            "description": description,
            "personality": personality,
            "scenario": scenario,
            "fears": "", "contradictions": "", "current_struggle": "", "growth_arc": "",
        })

    # If there's a first_mes or example, append as "## First meeting" / "## Example dialogues"
    if first_mes or mes_example:
        soul_text = soul_text.rstrip() + "\n"
        if first_mes:
            soul_text += f"\n## First meeting\n\n{first_mes}\n"
        if mes_example:
            soul_text += f"\n## Example dialogues\n\n{mes_example}\n"

    return {
        "name": name,
        "backstory": description,
        "personality": personality[:200],
        "voice_config": json.dumps(nook_ext.get("voice_config")) if nook_ext.get("voice_config") else None,
        "memory_mode": nook_ext.get("memory_mode", "hybrid"),
        "model_name": nook_ext.get("model_name", "qwen3:14b"),
        "relationship_type": nook_ext.get("relationship_type", "friend"),
        "soul_text": soul_text,
    }


# ── PNG embedding ───────────────────────────────────────────────

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Build a single PNG chunk with length + type + data + CRC."""
    length = struct.pack(">I", len(data))
    body = chunk_type + data
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return length + body + struct.pack(">I", crc)


def embed_json_in_png(png_bytes: bytes, json_text: str) -> bytes:
    """Insert a tEXt chunk with keyword 'chara' carrying base64(json) into a PNG.

    If the PNG already has a 'chara' chunk, replace it.
    """
    if not png_bytes.startswith(PNG_MAGIC):
        raise ValueError("Not a valid PNG")

    b64 = base64.b64encode(json_text.encode("utf-8")).decode("ascii")
    new_chunk = _png_chunk(b"tEXt", b"chara\x00" + b64.encode("ascii"))

    # Walk existing chunks, skip old 'chara' tEXt, keep the rest
    out = bytearray(PNG_MAGIC)
    i = 8  # past signature
    while i < len(png_bytes):
        length = struct.unpack(">I", png_bytes[i:i+4])[0]
        ctype = png_bytes[i+4:i+8]
        end = i + 8 + length + 4
        if ctype == b"tEXt" and png_bytes[i+8:i+8+5] == b"chara":
            pass  # drop the old chara chunk
        else:
            out.extend(png_bytes[i:end])
        i = end

    # Find the IEND chunk and insert before it
    iend_pos = bytes(out).find(b"IEND")
    if iend_pos < 0:
        # No IEND? Just append before signature — rare.
        out.extend(new_chunk)
    else:
        # IEND is preceded by its 4-byte length; insert the new chunk before that.
        insert_at = iend_pos - 4
        out[insert_at:insert_at] = new_chunk
    return bytes(out)


def extract_json_from_png(png_bytes: bytes) -> Optional[str]:
    """Extract a 'chara' tEXt chunk's JSON payload from a PNG. Returns None if missing."""
    if not png_bytes.startswith(PNG_MAGIC):
        return None
    i = 8
    while i < len(png_bytes):
        length = struct.unpack(">I", png_bytes[i:i+4])[0]
        ctype = png_bytes[i+4:i+8]
        end = i + 8 + length + 4
        if ctype == b"tEXt" and png_bytes[i+8:i+8+5] == b"chara":
            data = png_bytes[i+8+6:end-4]  # skip keyword + null, drop CRC
            try:
                return base64.b64decode(data).decode("utf-8")
            except Exception:
                return None
        i = end
    return None


# ── File detection ──────────────────────────────────────────────

def detect_format(filename: str, head: bytes) -> str:
    """Return 'png', 'json', or raise ValueError."""
    if head.startswith(PNG_MAGIC):
        return "png"
    s = head.lstrip()
    if s.startswith(b"{") or s.startswith(b"["):
        return "json"
    raise ValueError(f"Unknown format: {filename}")


def parse_card_payload(filename: str, content: bytes) -> dict:
    """Parse a card file (JSON or PNG) into a card dict."""
    fmt = detect_format(filename, content[:16])
    if fmt == "json":
        try:
            return json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON: {e}")
    elif fmt == "png":
        raw = extract_json_from_png(content)
        if not raw:
            raise ValueError("PNG has no embedded character card (no 'chara' tEXt chunk)")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"PNG's embedded card is invalid JSON: {e}")
    raise ValueError("unreachable")


# ── High-level: build a companion from a card file ─────────────

def import_companion_from_file(filename: str, content: bytes) -> dict:
    """Full pipeline: parse a card file, create a new companion in the DB,
    and (if PNG) save the avatar to the companion's directory.

    Returns the new companion record.
    """
    card = parse_card_payload(filename, content)
    fields = card_to_companion(card)

    # Use wizard-style companion creation so soul_path is wired up
    import uuid
    cid = str(uuid.uuid4())
    soul_path = db.DATA_DIR / "companions" / cid / "soul.md"
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(fields["soul_text"])

    avatar_path = None
    if detect_format(filename, content[:16]) == "png":
        # The PNG itself is the avatar
        dest = soul_path.parent / "avatar.png"
        dest.write_bytes(content)
        avatar_path = str(dest)

    conn = db.get_db()
    conn.execute("""
        INSERT INTO companions (id, name, avatar_path, backstory, personality,
            voice_config, memory_mode, model_name, relationship_type, soul_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cid, fields["name"], avatar_path, fields["backstory"], fields["personality"],
          fields["voice_config"], fields["memory_mode"], fields["model_name"],
          fields["relationship_type"], str(soul_path)))
    conn.commit()
    conn.close()
    return db.get_companion(cid)
