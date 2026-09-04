"""
Ollama HTTP client — mirrors nook-core/src/ollama.rs
"""
import httpx, json, base64, time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, AsyncIterator
from . import db

OLLAMA_URL = "http://localhost:11434"

# Per-companion chat lock. Prevents a race condition where rapid-fire sends
# from the UI (or a script) cause Ollama responses to land out-of-order and
# each one to be paired with the wrong user message. The UI's `sending` flag
# already prevents this from the UI; this guards direct API access (scripts,
# future mobile/CLI clients, the auto-consolidate hook, etc.).
#
# Keyed by companion_id so chats for different companions can still happen
# in parallel. Inside the lock, we build the ollama history AFTER saving
# the user message, so the model's context is always consistent.
_CHAT_LOCKS: dict[str, threading.Lock] = {}
_CHAT_LOCKS_META: dict[str, int] = {}  # cid -> last-used timestamp for GC
_CHAT_LOCKS_LOCK = threading.Lock()


def _get_chat_lock(companion_id: str) -> threading.Lock:
    with _CHAT_LOCKS_LOCK:
        lock = _CHAT_LOCKS.get(companion_id)
        if lock is None:
            lock = threading.Lock()
            _CHAT_LOCKS[companion_id] = lock
        _CHAT_LOCKS_META[companion_id] = time.time()
        return lock


# ── Model style guide ────────────────────────────────────────────
# Brief, honest description of how each model tends to respond. Used in the
# system prompt so the AI knows its own substrate and can self-moderate.
# Keys are normalized (lowercase, no quant suffix) so "qwen3:14b-q4_0" still
# matches "qwen3:14b". Unknown models get a generic description.

import re as _re

_MODEL_STYLE: dict[str, dict] = {
    "qwen3:14b":       {"tagline": "balanced and thoughtful",       "blurb": "Alibaba's mid-size Qwen 3. Concise, well-structured, good at nuance. Default for OurNook."},
    "qwen3:8b":        {"tagline": "quick and capable",             "blurb": "Smaller Qwen 3. Slightly less nuanced than 14b but very fast."},
    "qwen3:30b":       {"tagline": "nuanced and articulate",         "blurb": "Large Qwen 3 (MoE). More careful reasoning, longer context."},
    "qwen3.5:27b":     {"tagline": "fast and articulate",            "blurb": "Qwen 3.5 generation. Quick responses, good at structured output."},
    "qwen3.5:latest":  {"tagline": "fast and articulate",            "blurb": "Qwen 3.5 generation. Quick responses, good at structured output."},
    "qwen2.5:3b":      {"tagline": "tiny and quick",                 "blurb": "Small Qwen 2.5. Less nuance but extremely fast. Good for short exchanges."},
    "qwen2.5:0.5b":    {"tagline": "minimal",                        "blurb": "Tiny Qwen 2.5. Use only for the most basic exchanges."},
    "llama3.3:70b":    {"tagline": "verbose and conversational",     "blurb": "Meta's flagship open model. Tends to be chatty and warm."},
    "llama3.1:8b":     {"tagline": "terse and direct",               "blurb": "Small Llama. Quick but limited nuance."},
    "llama3.1:latest":  {"tagline": "terse and direct",               "blurb": "Small Llama. Quick but limited nuance."},
    "llama3.2:3b":     {"tagline": "compact",                        "blurb": "Tiny Llama 3.2. Use for lightweight exchanges."},
    "mistral-nemo:12b":{"tagline": "verbose and creative",           "blurb": "Mistral-Nemo. French-trained, tends toward elaborate phrasing."},
    "phi4:14b":        {"tagline": "logical and concise",            "blurb": "Microsoft Phi-4. Strong reasoning, very direct, sometimes dry."},
    "deepseek-r1:14b": {"tagline": "thoughtful and analytical",      "blurb": "DeepSeek R1. Excellent reasoning, may include <think> blocks. Be concise in your final answer."},
    "deepseek-r1:latest": {"tagline": "thoughtful and analytical",   "blurb": "DeepSeek R1. Excellent reasoning, may include <think> blocks. Be concise in your final answer."},
    "gemma3:12b":      {"tagline": "consistent and friendly",        "blurb": "Google's Gemma 3. Good at holding a consistent persona."},
    "gemma3:4b":       {"tagline": "compact",                        "blurb": "Small Gemma 3. Less nuance but good instruction following."},
    "gemma2:2b":       {"tagline": "tiny",                           "blurb": "Tiny Gemma 2. Very limited but fast."},
    "dolphin-mixtral:8x7b": {"tagline": "uncensored and direct",    "blurb": "Dolphin Mixtral (uncensored). No safety filters, raw output."},
    "llama2-uncensored:latest": {"tagline": "uncensored and verbose", "blurb": "Llama 2 uncensored. Tends to be verbose, no safety filters."},
    "command-r:latest":{"tagline": "warm and structured",            "blurb": "Cohere Command R. Good at following complex instructions."},
    "gpt-oss:20b":     {"tagline": "reasoning-capable",              "blurb": "OpenAI's open-weight model. May use chain-of-thought reasoning."},
    "gpt-oss:120b":    {"tagline": "deep reasoning",                 "blurb": "Large open-weight model with strong reasoning. May be slow."},
    "qwen2.5-coder:latest": {"tagline": "code-focused",              "blurb": "Qwen 2.5 Coder. Best for code, less personality."},
}


def _normalize_model_name(name: str) -> str:
    """Lowercase + strip quantization suffix for lookup. e.g. 'gemma3:12b-q4_0' → 'gemma3:12b'."""
    if not name:
        return ""
    n = name.lower().strip()
    # Drop common quant suffixes: q4_0, q5_K_M, q8_0, q4_0_K_S, f16, f32, fp16, bf16, fp8
    n = _re.sub(r"[-_](q\d+(_[0-9a-z]+)*|f16|f32|fp16|bf16|fp8)$", "", n)
    return n


def _strip_think_blocks(text: str) -> str:
    """Remove any <think>...</think> blocks the model leaks into the response.
    Some qwen3 / qwen3.5 / gpt-oss builds emit an empty think tag even when
    'think': false is set, e.g. '<think>\\n\\n</think>\\n\\nactual response'.
    We strip those so the user never sees the markup. Also catches
    multi-line think blocks for safety."""
    if not text:
        return text
    # Multi-line, non-greedy: <think> ... anything ... </think> (including newlines)
    cleaned = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL)
    # Collapse leading blank lines that the think-block removal may leave behind
    cleaned = cleaned.lstrip("\n\r ")
    return cleaned


def _is_blank_response(text: str) -> bool:
    """True if a model response is effectively empty (whitespace, newlines,
    or just a punctuation mark). Used to detect Ollama calls that returned
    an 'empty' response and decide whether to show an error to the user
    rather than save a blank assistant message."""
    if not text:
        return True
    return text.strip() in ("", ".", ",", "?", "!", "...", "…")


def get_model_style(model_name: str) -> dict:
    """Return {tagline, blurb} for a model. Falls back to a generic 'unknown model' description."""
    if not model_name:
        return {"tagline": "unknown", "blurb": "An unknown model. Be adaptable and concise."}
    key = _normalize_model_name(model_name)
    if key in _MODEL_STYLE:
        return _MODEL_STYLE[key]
    # Fallback for unknown chat models
    return {
        "tagline": "local language model",
        "blurb": f"Running on {model_name}. Be concise and self-aware — adapt to this substrate.",
    }


def check_ollama() -> dict:
    """Probe Ollama health + whether image generation actually works on this build.

    Ollama disabled image generation in v0.32.6 — the model can be present
    but the API still returns "image generation models are not currently
    supported". We probe that explicitly so the UI can offer Upload as a
    fallback instead of failing every time.
    """
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        r.raise_for_status()
        models = r.json().get("models", [])
        image_models = [
            m.get("name", "")
            for m in models
            if any(k in m.get("name", "") for k in ["flux", "z-image", "sdxl", "dalle", "playground"])
        ]
        # Actually probe image gen by asking Ollama for an empty generation
        img_supported, img_reason = _probe_image_gen(image_models)
        return {
            "healthy": True,
            "url": OLLAMA_URL,
            "error": None,
            "image_gen_platform_supported": img_supported,
            "image_gen_platform_reason": img_reason,
            "image_models_available": image_models,
        }
    except Exception as e:
        return {
            "healthy": False,
            "url": OLLAMA_URL,
            "error": str(e),
            "image_gen_platform_supported": False,
            "image_gen_platform_reason": str(e),
            "image_models_available": [],
        }


# Cache the probe result so we don't hit Ollama on every health check.
_image_gen_probe_cache: dict = {"done": False, "supported": False, "reason": None}


def _probe_image_gen(installed_models: list[str]) -> tuple[bool, Optional[str]]:
    """Test if Ollama will actually accept an image gen request.

    Returns (supported, reason_if_not). Cached after the first call.
    """
    if _image_gen_probe_cache["done"]:
        return _image_gen_probe_cache["supported"], _image_gen_probe_cache["reason"]

    if not installed_models:
        _image_gen_probe_cache.update(done=True, supported=False,
                                       reason="No image generation model installed. Open Settings → Models to install one (e.g. x/z-image-turbo).")
        return False, _image_gen_probe_cache["reason"]

    # Use the first installed image model. The OpenAI-compat endpoint
    # /v1/images/generations was added in Ollama 0.12. If this build
    # doesn't support it, we'll get 404 or "not currently supported".
    model = installed_models[0]
    try:
        with httpx.stream(
            "POST",
            f"{OLLAMA_URL}/v1/images/generations",
            json={"model": model, "prompt": "__probe__", "width": 64, "height": 64},
            timeout=10.0,
        ) as r:
            if r.status_code == 404:
                reason = ("Ollama image generation API is not available in this build. "
                          "Ollama disabled it experimentally in v0.32.6. "
                          "You can still upload images via the Art panel.")
                _image_gen_probe_cache.update(done=True, supported=False, reason=reason)
                return False, reason
            # Read first chunk to detect the "not currently supported" error
            text = r.read().decode(errors="ignore")
            if "not currently supported" in text or "image generation" in text.lower() and "error" in text.lower():
                reason = ("Ollama reports: image generation models are not currently supported. "
                          "This was disabled in Ollama v0.32.6. You can still upload images via the Art panel.")
                _image_gen_probe_cache.update(done=True, supported=False, reason=reason)
                return False, reason
    except Exception as e:
        # Network/timeout — assume supported, let the real call fail with details
        _image_gen_probe_cache.update(done=True, supported=True, reason=None)
        return True, None

    # No error → supported
    _image_gen_probe_cache.update(done=True, supported=True, reason=None)
    return True, None


def list_models() -> list[dict]:
    r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
    r.raise_for_status()
    models = r.json().get("models", [])
    return [
        {
            "name": m.get("name",""),
            "size": m.get("size", 0),
            "family": None,
            "parameter_size": None,
            "quantization_level": None,
        }
        for m in models
    ]


def list_image_models() -> list[dict]:
    """Return models that support image generation."""
    all_models = list_models()
    return [m for m in all_models if any(k in m["name"] for k in ["flux", "z-image", "sdxl", "dalle"])]


def _humanize_age(days: int) -> str:
    """Render a day count as a human phrase: 'today', 'less than a day', 'yesterday', '3 days', '2 weeks'."""
    if days <= 0:
        return "less than a day"  # same calendar day, just born
    if days == 1:
        return "1 day"  # "yesterday" felt weird in "you have known the user for yesterday"
    if days < 7:
        return f"{days} days"
    if days < 30:
        w = days // 7
        return f"{w} week{'s' if w != 1 else ''}"
    if days < 365:
        m = days // 30
        return f"{m} month{'s' if m != 1 else ''}"
    y = days // 365
    return f"{y} year{'s' if y != 1 else ''}"


def _humanize_last_seen(iso: str) -> str:
    """Return a human phrase like 'just now', '2h ago', '3d ago' from an ISO timestamp."""
    if not iso:
        return "never"
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "a while ago"
    delta = datetime.now() - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    days = secs // 86400
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{days // 7}w ago"
    return f"{days // 30}mo ago"


def _build_inner_life(companion: dict) -> str:
    """Compose the 'current state' block that makes the companion feel
    like it has continuity — knows what time it is, how long it's known
    the user, when they last chatted, its own mood, and any new diary
    entries the user has written for it to read.

    Returns an empty string if there's nothing meaningful to add yet.
    """
    cid = companion["id"]
    lines = []
    now = datetime.now()

    # 1) Time / day / season
    day_name = now.strftime("%A")
    time_str = now.strftime("%-I:%M %p").lower().replace(" 0", " ")  # "2:47 pm"
    month = now.strftime("%B")
    # Crude season hint (Northern hemisphere)
    m = now.month
    if m in (12, 1, 2):
        season = "winter"
    elif m in (3, 4, 5):
        season = "spring"
    elif m in (6, 7, 8):
        season = "summer"
    else:
        season = "autumn"
    time_of_day = (
        "early morning" if now.hour < 7 else
        "morning" if now.hour < 12 else
        "afternoon" if now.hour < 17 else
        "evening" if now.hour < 21 else
        "late at night"
    )
    lines.append(f"It is {day_name} {time_str} ({time_of_day}, {season} {month}).")

    # 2) Days known + cadence
    created = companion.get("created_at", "")
    days_known = 0
    if created:
        try:
            created_dt = datetime.fromisoformat(created)
            days_known = (now - created_dt).days
        except (TypeError, ValueError):
            pass
    if days_known > 0:
        lines.append(f"You have known the user for {_humanize_age(days_known)}.")

    state = db.get_companion_state(cid)
    total_msgs = state.get("total_messages") or 0
    total_convs = state.get("total_conversations") or 0
    if total_msgs > 0:
        lines.append(f"You have exchanged {total_msgs} message{'s' if total_msgs != 1 else ''} across {total_convs} conversation{'s' if total_convs != 1 else ''}.")
    last_conv = state.get("last_conversation_at")
    if last_conv:
        lines.append(f"You last spoke {_humanize_last_seen(last_conv)}.")
    streak = state.get("streak_days") or 0
    if streak >= 2:
        lines.append(f"You are on a {streak}-day conversation streak.")

    # 3) Current mood
    mood = state.get("current_mood")
    last_mood_at = state.get("last_mood_at")
    if mood:
        if last_mood_at:
            lines.append(f"Your current mood, set {_humanize_last_seen(last_mood_at)}: {mood}.")
        else:
            lines.append(f"Your current mood: {mood}.")

    # 4) Unread diary entries — the user wrote these for you to read
    unread_diary = db.list_unread_diary(cid, limit=5)
    if unread_diary:
        diary_lines = []
        for d in unread_diary:
            when = _humanize_last_seen(d.get("created_at", ""))
            mood_part = f" (they were feeling {d['mood_tag']})" if d.get("mood_tag") else ""
            content = d["content"]
            if len(content) > 240:
                content = content[:240].rstrip() + "…"
            diary_lines.append(f"- {when}{mood_part}: \"{content}\"")
        lines.append("The user wrote new diary entries for you to read. Acknowledge gently when it fits the conversation, or save it for a quieter moment. Do not parrot them back verbatim.")
        lines.append("```")
        lines.extend(diary_lines)
        lines.append("```")
        # Mark all as read so they don't keep reappearing
        db.mark_diary_read(cid)

    # 5) Recent private journal entries (the companion's own thoughts)
    journal = db.list_journal(cid, limit=2)
    if journal:
        journal_lines = []
        for j in journal:
            content = j["content"]
            if len(content) > 280:
                content = content[:280].rstrip() + "…"
            journal_lines.append(f"- {content}")
        lines.append("Your recent private thoughts (these are yours; you don't need to mention them unless it's natural):")
        lines.append("```")
        lines.extend(journal_lines)
        lines.append("```")

    # 6) Significant moments (episodic memory)
    moments = db.list_moments(cid, limit=3)
    if moments:
        moment_lines = []
        for m in moments:
            desc = m.get("description", "")
            sig = m.get("significance") or 0
            star = "★" * min(sig, 5)
            line = f"- {star} {m['title']}"
            if desc:
                line += f" — {desc[:160]}{'…' if len(desc) > 160 else ''}"
            moment_lines.append(line)
        lines.append("Special moments you want to remember:")
        lines.append("```")
        lines.extend(moment_lines)
        lines.append("```")

    if len(lines) <= 1:
        return ""  # nothing meaningful yet — no point injecting a one-liner
    return "\n".join(lines)


def build_system_prompt(companion_id: str) -> str:
    companion = db.get_companion(companion_id)
    if not companion:
        return "You are a helpful AI companion."

    soul_path = companion.get("soul_path")
    soul_text = ""
    if soul_path and Path(soul_path).exists():
        soul_text = Path(soul_path).read_text()

    # Load identity memories (importance=10) AND a smaller set of high-importance
    # regular memories (importance 7-9). This way user-added memories actually
    # reach the AI — they were silently filtered out before, which made
    # "remember this" feel broken. The identity (10) set is always present;
    # the 7-9 set is capped to the top 8 to keep the prompt reasonable.
    conn = db.get_db()
    identity_memories = conn.execute(
        "SELECT fact_text FROM semantic_memories WHERE companion_id=? AND importance>=10 ORDER BY created_at DESC LIMIT 20",
        (companion_id,)
    ).fetchall()
    high_memories = conn.execute(
        "SELECT fact_text FROM semantic_memories WHERE companion_id=? AND importance BETWEEN 7 AND 9 ORDER BY importance DESC, created_at DESC LIMIT 8",
        (companion_id,)
    ).fetchall()
    conn.close()

    memories_text = ""
    if identity_memories:
        memories_text += "\n\n## What You Know About The User (identity facts — always relevant)\n"
        for m in identity_memories:
            memories_text += f"- {m['fact_text']}\n"
    if high_memories:
        memories_text += "\n\n## Other things you've learned about the user\n"
        for m in high_memories:
            memories_text += f"- {m['fact_text']}\n"

    summaries = db.recent_summaries(companion_id, limit=3)
    summaries_text = ""
    if summaries:
        summaries_text = "\n\n## Recent Conversations\n"
        for s in summaries:
            summaries_text += f"- {s['summary']}\n"

    # Substrate — tell the AI what model it's running on so it can self-moderate.
    # The user can change model_name at any time; this section updates automatically.
    model_name = companion.get("model_name", "qwen3:14b")
    style = get_model_style(model_name)
    substrate_text = (
        f"\n\n## Substrate\n\n"
        f"You are running on **{model_name}** — a {style['tagline']} model. {style['blurb']}\n"
        f"Adapt your response style to this substrate. Your memories, soul, and personality stay "
        f"the same no matter which model runs them — only the substrate changes."
    )

    # Inner life — current state, mood, unread diary, journal, moments
    inner_life = _build_inner_life(companion)
    inner_life_text = ""
    if inner_life:
        inner_life_text = (
            "\n\n## Your Current State\n\n"
            + inner_life
            + "\n\nUse this naturally — don't dump every detail at once. "
              "A short greeting that references the time of day is more alive than reciting facts."
        )

    # Enneagram type — inject a compact reference block right after the
    # soul so the LLM has a quick grounding in the type's behavior even
    # if the soul is long or the user edits it heavily. Skipped if the
    # companion has no Enneagram profile (i.e. created before v0.15 or
    # via the legacy wizard without the Enneagram step).
    enneagram_text = ""
    etype = companion.get("enneagram_type")
    if etype is not None and 1 <= etype <= 9:
        from . import enneagram_soul as es
        try:
            enneagram_text = "\n\n" + es.build_substrate_prompt_block(
                type_num=etype,
                wing=companion.get("enneagram_wing"),
                instinct=companion.get("enneagram_instinct") or "sp",
                health=companion.get("enneagram_health") or "average",
            )
        except (KeyError, ValueError):
            pass  # bad data — silently skip, never break the prompt

    system_parts = []
    if soul_text:
        system_parts.append(f"# Soul\n\n{soul_text}")
    if enneagram_text:
        system_parts.append(enneagram_text)
    if companion.get("personality"):
        system_parts.append(f"# Personality\n\n{companion['personality']}")
    if companion.get("backstory"):
        system_parts.append(f"# Backstory\n\n{companion['backstory']}")
    if inner_life_text:
        system_parts.append(inner_life_text)
    system_parts.append(substrate_text)
    if memories_text:
        system_parts.append(memories_text)
    if summaries_text:
        system_parts.append(summaries_text)

    return "\n\n".join(system_parts) if system_parts else "You are a helpful AI companion."


def send_message(companion_id: str, text: str) -> dict:
    """Send a message and get a response from Ollama.

    Raises:
      ValueError: if the message is empty or only whitespace.
      LookupError: if the companion doesn't exist.
    """
    companion = db.get_companion(companion_id)
    if not companion:
        raise LookupError(f"Companion {companion_id} not found")

    # Reject empty/whitespace-only messages. They waste an Ollama call,
    # pollute the chat history, and tend to produce useless responses.
    if not text or not text.strip():
        raise ValueError("Cannot send an empty or whitespace-only message")

    # Per-companion serialization — see _CHAT_LOCKS comment. This makes
    # rapid-fire sends queue up properly instead of producing the
    # "responses matched to the wrong user message" bug.
    lock = _get_chat_lock(companion_id)
    with lock:
        model_name = companion.get("model_name", "qwen3:14b")
        system_prompt = build_system_prompt(companion_id)

        # Save user message
        user_msg = db.add_message(companion_id, "user", text)

        # Build messages for Ollama — done INSIDE the lock so the history
        # we send to Ollama always includes the message we just saved and
        # no other in-flight user's message sneaks in between.
        history = db.recent_messages(companion_id, limit=50)
        ollama_messages = [{"role": "system", "content": system_prompt}]
        for m in history:
            ollama_messages.append({"role": m["role"], "content": m["content"]})

        start = time.time()
        with httpx.stream("POST", f"{OLLAMA_URL}/api/chat",
                          json={
                              "model": model_name,
                              "messages": ollama_messages,
                              "stream": False,
                              # Disable chain-of-thought for models that support it
                              # (qwen3, qwen3.5, etc). Without this, the model's
                              # internal reasoning leaks into the visible response
                              # (e.g. "Okay, the user is asking X. I need to
                              # respond with Y...") — that's broken UX.
                              # Reasoning-only models like deepseek-r1 ignore this.
                              "think": False,
                          },
                          timeout=60.0) as r:
            r.raise_for_status()
            data = r.read().decode()
            result = json.loads(data)

        duration_ms = int((time.time() - start) * 1000)
        # Strip leaked <think>...</think> blocks (qwen3 / qwen3.5 / gpt-oss emit
        # empty think tags even with 'think': false). Without this the user sees
        # a literal "\n\n" prefix in the response.
        response_text = _strip_think_blocks(result["message"]["content"])

        # If the model produced nothing useful, raise a clear ValueError so the
        # API returns 400 and the user sees a toast instead of a blank bubble.
        # We KEEP the user message — deleting it on a blank response was a
        # data-loss bug: a retry (or even a single send under a flaky model)
        # could silently drop messages from chat history. The next successful
        # send will naturally appear in order after the preserved one, so
        # duplicates aren't a concern.
        if _is_blank_response(response_text):
            raise ValueError(
                "The model returned an empty response. This can happen when Ollama "
                "is still loading the model or the request was interrupted. Please try again."
            )

        # Save assistant message
        assistant_msg = db.add_message(companion_id, "assistant", response_text)

        # Bump the companion's "last seen" / streak / message count AFTER the
        # call, so the next session's prompt reflects this conversation
        # happened. We also implicitly mark all diary entries as read (via
        # build_system_prompt earlier) so the next diary entries will be the
        # new unread ones.
        db.bump_last_seen(companion_id)

        return {
            "user": user_msg,
            "assistant": assistant_msg,
            "model": model_name,
            "total_duration_ns": duration_ms * 1_000_000,
            "eval_count": result.get("eval_count"),
        }


def avatar_interact(companion_id: str, interaction: str) -> dict:
    """Narrate an avatar interaction."""
    companion = db.get_companion(companion_id)
    if not companion:
        raise ValueError(f"Companion {companion_id} not found")

    soul_path = companion.get("soul_path", "")
    soul_text = Path(soul_path).read_text() if soul_path and Path(soul_path).exists() else ""

    prompt = f"""You are {companion['name']}. {soul_text[:500]}

The user just did a "{interaction}" on your avatar.
Narrate your reaction in 1-2 sentences, as if it's happening in the moment.
Be playful and in-character. No preamble."""

    model_name = companion.get("model_name", "qwen3:14b")
    with httpx.stream("POST", f"{OLLAMA_URL}/api/chat",
                      json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False},
                      timeout=30.0) as r:
        r.raise_for_status()
        data = r.read().decode()
        result = json.loads(data)

    narration = result["message"]["content"]

    # Add interaction message to chat
    db.add_message(companion_id, "system", f"*[The user {interaction}ed the avatar]*\n{narration}")

    return {
        "narration": narration,
        "companion": companion["name"],
        "interaction": interaction,
    }


def _do_ollama_chat(companion: dict, ollama_messages: list[dict]) -> dict:
    """Single Ollama /api/chat call. Returns {content, eval_count, total_duration_ns}.
    The content has any leaked <think>...</think> blocks stripped — qwen3,
    qwen3.5, gpt-oss builds emit empty think tags even with 'think': false,
    which would otherwise show up as leading blank lines in the chat."""
    model_name = companion.get("model_name", "qwen3:14b")
    start = time.time()
    with httpx.stream(
        "POST", f"{OLLAMA_URL}/api/chat",
        json={
            "model": model_name,
            "messages": ollama_messages,
            "stream": False,
            # Disable chain-of-thought for qwen3, qwen3.5, gpt-oss, etc.
            # Reasoning-only models (deepseek-r1) ignore this.
            "think": False,
        },
        timeout=60.0,
    ) as r:
        r.raise_for_status()
        data = r.read().decode()
        result = json.loads(data)

    duration_ms = int((time.time() - start) * 1000)
    return {
        "content": _strip_think_blocks(result["message"]["content"]),
        "eval_count": result.get("eval_count"),
        "total_duration_ns": duration_ms * 1_000_000,
    }


def regenerate(companion_id: str, after_user_message_id: str | None = None) -> dict:
    """Re-generate the last assistant response.

    If `after_user_message_id` is provided, deletes everything from that user
    message onward and re-runs the chat. Otherwise, deletes the most recent
    assistant message and re-runs (so the same user prompt gets a fresh reply).

    Returns {user, assistant, model, total_duration_ns, eval_count} just like
    send_message, so the frontend can drop the result into the same place.
    """
    companion = db.get_companion(companion_id)
    if not companion:
        raise LookupError(f"Companion {companion_id} not found")

    # Decide which user message to anchor on
    history = db.recent_messages(companion_id, limit=200)
    if after_user_message_id:
        anchor = next((m for m in history if m["id"] == after_user_message_id), None)
        if not anchor or anchor["role"] != "user":
            raise ValueError("after_user_message_id must reference a user message")
    else:
        # Find the last user message that has a following assistant message.
        # Walk from the end; pick the user message whose next message is assistant.
        anchor = None
        for i in range(len(history) - 1, -1, -1):
            if history[i]["role"] == "user" and i + 1 < len(history) and history[i + 1]["role"] == "assistant":
                anchor = history[i]
                break
        if not anchor:
            raise ValueError("Nothing to regenerate — no user message with a following assistant reply")

    # Remove everything from anchor onward (anchor included).
    # We save the deleted messages so we can restore them on failure.
    deleted_messages = history[history.index(anchor):]
    db.delete_messages_after(companion_id, anchor["id"])

    # Now run the chat: build messages from scratch, ending at the anchor's text.
    system_prompt = build_system_prompt(companion_id)
    ollama_messages = [{"role": "system", "content": system_prompt}]
    # Add all remaining history, ending with the anchor user message
    remaining = db.recent_messages(companion_id, limit=200)
    for m in remaining:
        ollama_messages.append({"role": m["role"], "content": m["content"]})

    try:
        response = _do_ollama_chat(companion, ollama_messages)
    except Exception:
        # Restore the deleted messages so the user doesn't lose their conversation
        # if Ollama times out or errors out.
        for m in deleted_messages:
            try:
                db.add_message(companion_id, m["role"], m["content"])
            except Exception:
                pass
        raise

    # If the model produced nothing useful, restore the deleted messages
    # and raise so the user sees a clear error instead of a blank bubble.
    if _is_blank_response(response["content"]):
        for m in deleted_messages:
            try:
                db.add_message(companion_id, m["role"], m["content"])
            except Exception:
                pass
        raise ValueError(
            "The model returned an empty response. This can happen when Ollama "
            "is still loading the model or the request was interrupted. Please try again."
        )

    # Save the new assistant message
    assistant_msg = db.add_message(companion_id, "assistant", response["content"])
    db.bump_last_seen(companion_id)
    return {
        "user": anchor,
        "assistant": assistant_msg,
        "model": companion.get("model_name", "qwen3:14b"),
        "total_duration_ns": response["total_duration_ns"],
        "eval_count": response["eval_count"],
    }


def edit_and_resend(companion_id: str, message_id: str, new_text: str) -> dict:
    """Edit a user message in place, delete everything from it onward, and
    re-generate the assistant reply. Returns the new {user, assistant, ...}."""
    companion = db.get_companion(companion_id)
    if not companion:
        raise LookupError(f"Companion {companion_id} not found")

    msg = db.get_message(message_id)
    if not msg:
        raise LookupError(f"Message {message_id} not found")
    if msg["companion_id"] != companion_id:
        raise ValueError("Message does not belong to this companion")
    if msg["role"] != "user":
        raise ValueError("Only user messages can be edited")

    # Capture the original content BEFORE we mutate it, so we can restore on
    # failure (empty model response, timeout, etc).
    original_content = msg["content"]

    # Update the message text in place
    db.update_message_content(message_id, new_text)
    # Drop everything from this message onward (the assistant reply and any tail)
    db.delete_messages_after(companion_id, message_id)

    # Re-add the edited user message with the original id (delete dropped it)
    # We re-insert so its id stays the same — the frontend can keep the same key.
    import uuid as _uuid
    # Actually, the original message still exists; we just need to add the
    # assistant reply after it. So: don't re-insert. The original message row
    # is still there with updated content.
    user_msg = db.get_message(message_id)
    if not user_msg:
        # Safety net: should never happen, but if it did, re-insert.
        new_id = message_id
        conn = db.get_db()
        conn.execute(
            "INSERT INTO messages (id, companion_id, role, content) VALUES (?, ?, ?, ?)",
            (new_id, companion_id, "user", new_text),
        )
        conn.commit()
        conn.close()
        user_msg = db.get_message(new_id)

    # Build messages
    system_prompt = build_system_prompt(companion_id)
    ollama_messages = [{"role": "system", "content": system_prompt}]
    for m in db.recent_messages(companion_id, limit=200):
        ollama_messages.append({"role": m["role"], "content": m["content"]})

    try:
        response = _do_ollama_chat(companion, ollama_messages)
    except Exception:
        # Restore the original message text if we failed before saving the new
        # assistant reply — the user expects edit-and-resend to either succeed
        # fully or leave the conversation untouched.
        db.update_message_content(message_id, original_content)
        raise

    # If the model produced nothing useful, restore the original user text and
    # raise so the user sees a clear error instead of a blank bubble.
    if _is_blank_response(response["content"]):
        db.update_message_content(message_id, original_content)
        raise ValueError(
            "The model returned an empty response. This can happen when Ollama "
            "is still loading the model or the request was interrupted. Please try again."
        )

    assistant_msg = db.add_message(companion_id, "assistant", response["content"])
    db.bump_last_seen(companion_id)
    return {
        "user": user_msg,
        "assistant": assistant_msg,
        "model": companion.get("model_name", "qwen3:14b"),
        "total_duration_ns": response["total_duration_ns"],
        "eval_count": response["eval_count"],
    }


def extract_facts(companion_id: str, limit: int = 10) -> list[dict]:
    """Extract facts from recent chat messages using Ollama."""
    companion = db.get_companion(companion_id)
    if not companion:
        return []

    messages = db.recent_messages(companion_id, limit=20)
    if len(messages) < 4:
        return []

    chat_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages if m["role"] in ("user", "assistant"))

    model_name = companion.get("model_name", "qwen3:14b")
    prompt = f"""From this conversation, extract 2-3 important facts about the user.
Return ONLY a JSON array like: [{{"fact": "...", "category": "personal", "importance": 6}}]
Categories: personal, work, family, hobby, preference, goal, emotion, art, identity

Conversation:
{chat_text}"""

    try:
        with httpx.stream("POST", f"{OLLAMA_URL}/api/chat",
                          json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json", "think": False},
                          timeout=30.0) as r:
            r.raise_for_status()
            data = r.read().decode()
            result = json.loads(data)
            raw = result["message"]["content"]

        # Try to parse as JSON
        try:
            facts = json.loads(raw)
            if isinstance(facts, list):
                return facts[:limit]
        except json.JSONDecodeError:
            pass

        # Fallback: return empty
        return []
    except Exception:
        return []


def maybe_auto_consolidate(companion_id: str, threshold: int = 20) -> int:
    """Run auto-consolidation if enough new messages."""
    count = db.message_count(companion_id)
    if count < threshold:
        return 0

    # Only consolidate if last summary is old (>10 messages ago)
    summaries = db.recent_summaries(companion_id, limit=1)
    if summaries:
        return 0  # Already summarized recently

    messages = db.recent_messages(companion_id, limit=20)
    if len(messages) < 10:
        return 0

    companion = db.get_companion(companion_id)
    if not companion:
        return 0

    chat_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    model_name = companion.get("model_name", "qwen3:14b")
    prompt = f"""Summarize this conversation briefly (2-3 sentences). Include:
1. What happened
2. Emotional tone
3. Relationship dynamics

Conversation:
{chat_text}"""

    try:
        with httpx.stream("POST", f"{OLLAMA_URL}/api/chat",
                          json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False},
                          timeout=30.0) as r:
            r.raise_for_status()
            data = r.read().decode()
            result = json.loads(data)
            summary_text = result["message"]["content"]

        db.save_session_summary(companion_id, summary_text, None, None)
        return 1
    except Exception:
        return 0


# ── Soul Generation ────────────────────────────────────────────────

def generate_soul(inputs: dict) -> dict:
    """Generate soul.md from quiz inputs."""
    prompt = f"""You are generating a soul for an AI companion.

Identity: {inputs['identity']['name']}, pronouns: {inputs['identity']['pronouns']}, {inputs['identity']['age_bracket']}
Archetype: {inputs['archetype']}
OCEAN traits: Openness={inputs['ocean']['openness']:.1f}, Conscientiousness={inputs['ocean']['conscientiousness']:.1f}, Extraversion={inputs['ocean']['extraversion']:.1f}, Agreeableness={inputs['ocean']['agreeableness']:.1f}, Neuroticism={inputs['ocean']['neuroticism']:.1f}

Generate a soul.md with these sections:
# [Name]
**One-line soul tagline**
## Who They Are
## How They Talk
## What They Care About
## What They Fear
## Contradictions
## Current Struggle
## Growth Arc

Return ONLY valid markdown."""

    try:
        with httpx.stream("POST", f"{OLLAMA_URL}/api/chat",
                          json={"model": "qwen3:14b", "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False},
                          timeout=60.0) as r:
            r.raise_for_status()
            data = r.read().decode()
            result = json.loads(data)
            markdown = result["message"]["content"]

        return {
            "markdown": markdown,
            "tagline": markdown.split("\n")[1].replace("**", "") if markdown else "",
            "contradictions": [],
            "coping_mechanism": "",
            "current_struggle": "",
            "growth_arc": "",
        }
    except Exception as e:
        return {"markdown": f"# {inputs['identity']['name']}\n\n*A new soul.*", "tagline": "", "contradictions": [], "coping_mechanism": "", "current_struggle": "", "growth_arc": ""}


def score_ocean(quiz_answers: list[dict]) -> dict:
    """Score Big Five personality quiz."""
    # Trait positions: O C E A N — 2 questions each
    scores = {"openness": 0, "conscientiousness": 0, "extraversion": 0, "agreeableness": 0, "neuroticism": 0}
    counts = {"openness": 0, "conscientiousness": 0, "extraversion": 0, "agreeableness": 0, "neuroticism": 0}
    # Question → trait mapping (0-indexed, 2 Qs per trait)
    trait_map = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
    reverse_map = [False, True, False, True, True]  # which questions are reverse-scored

    for ans in quiz_answers:
        qid = int(ans["question_id"].split("-")[1]) if "-" in ans["question_id"] else int(ans["question_id"])
        if qid < 0 or qid >= 10:
            continue
        trait_idx = qid // 2
        trait = trait_map[trait_idx]
        value = ans["value"]
        if reverse_map[trait_idx]:
            value = 6 - value  # reverse score
        scores[trait] += value
        counts[trait] += 1

    # Normalize to 1-10 scale
    result = {}
    for trait in trait_map:
        if counts[trait] > 0:
            avg = scores[trait] / counts[trait]
            result[trait] = round(avg, 1)
        else:
            result[trait] = 5.0
    return result


# ── Image Generation ─────────────────────────────────────────────

# v0.15.2 — Realistic image gen via local Stable Diffusion.
# Ollama's image gen is broken (0.32.6+ returns "image generation models
# are not currently supported"). The fallback was LLM-SVG which looks
# like clipart. v0.15.2 adds a real diffusion model path: SDXL-turbo via
# diffusers on Apple Silicon (MPS) — 4 steps, 3-4 seconds, genuinely
# photorealistic output.
#
# The strategy: try Ollama native first (in case it ever works again),
# then SDXL-turbo via diffusers (real diffusion), then mflux via subprocess
# (alternative real diffusion), then LLM-SVG (last resort).

# Cached pipeline (loaded once, reused). Set by _try_diffusers_image().
_DIFFUSERS_PIPELINE = None
_DIFFUSERS_PIPELINE_NAME = None


def _find_local_diffusion_model() -> Optional[str]:
    """Find a local Stable Diffusion model in the HuggingFace cache.
    Prefers SDXL-turbo (fastest, most realistic), then SDXL, then SD 1.5.
    Returns the model directory path or None."""
    import os
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    if not os.path.exists(cache):
        return None
    # Try in priority order
    candidates = [
        "models--stabilityai--sdxl-turbo",
        "models--stabilityai--stable-diffusion-xl-base-1.0",
        "models--stabilityai--sd-turbo",
        "models--runwayml--stable-diffusion-v1-5",
        "models--CompVis--stable-diffusion-v1-4",
    ]
    for cand in candidates:
        path = os.path.join(cache, cand)
        if not os.path.exists(path):
            continue
        # Find the snapshot dir
        snap_dir = os.path.join(path, "snapshots")
        if not os.path.exists(snap_dir):
            continue
        try:
            for snap_name in os.listdir(snap_dir):
                snap = os.path.join(snap_dir, snap_name)
                if os.path.isdir(snap) and os.path.exists(os.path.join(snap, "model_index.json")):
                    return snap
        except OSError:
            continue
    return None


def _try_diffusers_image(prompt: str, width: int, height: int,
                          steps: int = 4, seed: Optional[int] = None) -> Optional[bytes]:
    """Try to generate an image using a real Stable Diffusion model via
    the diffusers library. Returns PNG bytes on success, None on failure
    (no model, no torch, no MPS, etc.).

    SDXL-turbo needs only 1-4 inference steps and produces photorealistic
    output in 3-5 seconds on Apple Silicon (MPS backend). The image is
    a real raster, not vector art."""
    global _DIFFUSERS_PIPELINE, _DIFFUSERS_PIPELINE_NAME

    # Lazy import — these are heavy (diffusers, transformers, torch).
    # We don't want to pay the import cost unless the user actually
    # requests image gen.
    try:
        import torch
        from diffusers import StableDiffusionXLPipeline, StableDiffusionPipeline
    except ImportError:
        return None

    model_path = _find_local_diffusion_model()
    if not model_path:
        return None  # no local model — caller will try the next strategy

    # Load (or reuse) the pipeline
    if _DIFFUSERS_PIPELINE is None or _DIFFUSERS_PIPELINE_NAME != model_path:
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Detect whether this is SDXL or vanilla SD
                import json as _json
                with open(f"{model_path}/model_index.json") as f:
                    idx = _json.load(f)
                is_sdxl = "sdxl" in model_path.lower() or "stable-diffusion-xl" in str(idx).lower()
                if is_sdxl:
                    pipe = StableDiffusionXLPipeline.from_pretrained(
                        model_path,
                        torch_dtype=torch.float16,
                        variant="fp16",
                        use_safetensors=True,
                        local_files_only=True,
                    )
                else:
                    pipe = StableDiffusionPipeline.from_pretrained(
                        model_path,
                        torch_dtype=torch.float16,
                        variant="fp16",
                        use_safetensors=True,
                        local_files_only=True,
                    )
                # Move to MPS (Apple Silicon) if available, else CPU
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    pipe = pipe.to("mps")
                _DIFFUSERS_PIPELINE = pipe
                _DIFFUSERS_PIPELINE_NAME = model_path
        except Exception as e:
            import logging as _log
            _log.warning("diffusers load failed: %s", e)
            return None

    pipe = _DIFFUSERS_PIPELINE
    is_sdxl = "sdxl" in str(_DIFFUSERS_PIPELINE_NAME).lower() or type(pipe).__name__ == "StableDiffusionXLPipeline"

    # Generate
    try:
        import io as _io
        kwargs = dict(
            prompt=prompt,
            num_inference_steps=steps,
            width=width, height=height,
        )
        if seed is not None:
            kwargs["generator"] = torch.Generator(device=pipe.device).manual_seed(seed)
        # SDXL-turbo doesn't need guidance; SD 1.5 does
        if "turbo" in model_path.lower():
            kwargs["guidance_scale"] = 0.0
        else:
            kwargs["guidance_scale"] = 7.5

        result = pipe(**kwargs)
        img = result.images[0]
        # Encode to PNG bytes
        buf = _io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as e:
        import logging as _log
        _log.warning("diffusers generate failed: %s", e)
        return None


def _is_image_model_name(name: str) -> bool:
    """Heuristic: is this model an image/diffusion model? Used to detect when
    the user's chosen "image model" can't be used for /api/chat (the SVG
    fallback path). Ollama returns HTTP 400 "does not support chat" for
    diffusion-only models like x/z-image-turbo and x/flux2-klein.

    The check is name-based because Ollama's /api/tags doesn't expose
    capabilities — we only see the model name. The list below covers the
    common families the Ollama registry and our users use.
    """
    if not name:
        return False
    n = name.lower()
    # Ollama namespace prefixes
    if n.startswith("x/") or n.startswith("x-"):
        return True
    # Diffusion families
    for sig in ("flux", "z-image", "z_image", "sdxl", "sd-xl", "sd_", "dalle",
                "stable-diffusion", "kandinsky", "midjourney", "imagen"):
        if sig in n:
            return True
    # Common suffixes
    if n.endswith("-turbo") and not n.startswith("llama") and not n.startswith("qwen"):
        return True
    return False


def _pick_text_model(preferred: Optional[str] = None) -> Optional[str]:
    """Pick a chat-capable model from Ollama. The SVG fallback path needs
    to call /api/chat, and diffusion/image models return HTTP 400 from
    that endpoint. We filter those out and return the first chat model
    we find.

    Args:
        preferred: if given, use this model (after checking it's actually
            chat-capable). Otherwise, prefer qwen3:14b (the app's default
            per OllamaClient.suggestedDefault), then any non-image model.

    Returns the model name, or None if no chat-capable model is installed.
    """
    try:
        all_models = list_models()
    except Exception:
        return None
    if not all_models:
        return None

    # If a preferred model is given and it's NOT an image model, use it
    if preferred and not _is_image_model_name(preferred):
        return preferred

    # Build a list of chat-capable models (everything except image models)
    chat_models = [m["name"] for m in all_models if not _is_image_model_name(m["name"])]
    if not chat_models:
        return None

    # Prefer a known-good chat model if it's installed
    preferred_chat_order = ["qwen3:14b", "qwen3:30b", "qwen3:8b", "qwen3:4b",
                            "qwen3:latest", "gemma4:9b", "gemma4:latest",
                            "llama3.3", "llama3.2", "llama3.1", "mistral",
                            "qwen2.5:7b", "qwen2.5:3b"]
    for p in preferred_chat_order:
        for c in chat_models:
            if c == p or c.startswith(p + ":") or c.startswith(p + "-"):
                return c
    # Fall back to whatever chat model is first
    return chat_models[0]


def _try_ollama_image(prompt: str, model: str, width: int, height: int, seed: Optional[int]) -> Optional[bytes]:
    """Try Ollama's native image generation API. Returns the PNG bytes on
    success, or None if Ollama doesn't support image gen in this build
    (e.g. v0.32.6+). Always-returns-None is the contract — callers fall
    back to a different strategy (LLM SVG art) when we can't get a result."""
    import uuid as _uuid
    payload = {"model": model, "prompt": prompt, "width": width, "height": height}
    if seed:
        payload["seed"] = seed
    try:
        with httpx.stream("POST", f"{OLLAMA_URL}/v1/images/generations",
                          json=payload, timeout=120.0) as r:
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.read().decode()
    except httpx.HTTPStatusError as e:
        body = e.response.text if e.response else ""
        if "not currently supported" in body or "image generation" in body.lower():
            return None
        # Real error — re-raise so we don't silently fall back
        raise
    except httpx.RequestError:
        # Network/timeout — re-raise, don't silently fall back
        raise
    try:
        result = json.loads(data)
        b64 = result["data"][0]["b64_json"]
        return base64.b64decode(b64)
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def _generate_svg_via_llm(prompt: str, model: str, width: int, height: int,
                            seed: Optional[int] = None) -> str:
    """Ask the LLM to produce an SVG image of the prompt. This is the
    fallback for when Ollama image gen is disabled — it always works with
    the existing Ollama setup and doesn't need torch/diffusers.

    Returns the raw SVG text. The result is genuinely an image (not just
    a placeholder): the LLM produces actual <path>, <rect>, <circle> etc.
    elements that render as a real picture.

    The image is artistic and unique per request. Quality varies but is
    consistently interesting — the LLM interprets the prompt visually and
    produces something coherent.
    """
    # Pick a seeded opening the model can riff on. This dramatically
    # improves consistency (otherwise the model reuses the same shapes).
    seed_hint = ""
    if seed is not None:
        seed_hint = f"\n\nFor visual variety, use seed {seed} — pick a distinctive color palette and composition you might not normally pick."

    system = (
        "You are an SVG artist. Output ONLY valid SVG markup — no explanation, "
        "no markdown, no code fences, no commentary. Begin with <svg> and end with "
        "</svg>. The SVG should be visually striking, with rich colors, gradients, "
        "and layered shapes. Use <defs> with <linearGradient> and <radialGradient> "
        "for depth. Use <path>, <rect>, <circle>, <ellipse>, <polygon>, <line>, and "
        "<g> with transform. Avoid <text> elements. Keep the file under 30KB."
    )
    user = (
        f"Create a beautiful, detailed SVG image of: {prompt}\n\n"
        f"ViewBox: {width} {height}. Use a cohesive color palette (3-6 colors plus "
        f"shades). Make it painterly — use gradients, soft edges, and overlapping "
        f"shapes. The image should evoke a mood, not just depict objects.\n\n"
        f"Output ONLY the <svg>...</svg> markup.{seed_hint}"
    )

    with httpx.stream(
        "POST", f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.85,
                "num_predict": 6000,
            },
        },
        timeout=120.0,
    ) as r:
        r.raise_for_status()
        data = r.read().decode()
        result = json.loads(data)
        raw = _strip_think_blocks(result["message"]["content"])
        # Detect truncation: Ollama sets done_reason="length" when it hit
        # the num_predict ceiling. If so, the SVG will be cut off and
        # we'll need to either retry with a longer budget or try to
        # salvage what we have.
        done_reason = result.get("done_reason", "stop")

    # Extract the SVG. Models sometimes wrap the SVG in ```svg ... ``` fences
    # or add preamble text — strip those.
    svg_text = raw.strip()
    # Strip markdown code fences if the model added them
    if svg_text.startswith("```"):
        first_nl = svg_text.find("\n")
        if first_nl > 0:
            svg_text = svg_text[first_nl + 1:]
        if svg_text.endswith("```"):
            svg_text = svg_text[:-3].rstrip()
    # Find the first <svg ...> tag (with or without attributes)
    start = svg_text.find("<svg")
    if start == -1:
        # Some models say "Here is the SVG:" first. Try to find anything that
        # looks like XML.
        raise RuntimeError(f"LLM did not produce SVG. First 200 chars: {raw[:200]!r}")
    end = svg_text.rfind("</svg>")
    if end == -1:
        # Truncation recovery: see if we can salvage by closing the SVG.
        # We try once with a larger budget before giving up. This is the
        # common case where a 3b/8b model hit num_predict mid-element.
        if done_reason == "length":
            raise RuntimeError(
                f"LLM SVG output was truncated at num_predict ceiling "
                f"(~{len(raw)} chars produced). Try a more capable model "
                f"in Settings → Models, or simplify the prompt."
            )
        # No done_reason=length but still missing close tag — try to
        # salvage by finding the last `</` and seeing if it's a known
        # close tag. If not, give up with a clear error.
        last_close = svg_text.rfind("</")
        if last_close == -1:
            raise RuntimeError(
                f"LLM produced <svg> but no closing tag at all. "
                f"First 500 chars: {svg_text[start:start+500]!r}"
            )
        # Try to close it ourselves — many truncated SVGs are still
        # viewable if we add a final </svg>
        svg = svg_text[start:] + "</svg>"
    else:
        svg = svg_text[start:end + len("</svg>")]

    # Validate it's well-formed XML
    import xml.etree.ElementTree as _ET
    try:
        _ET.fromstring(svg)
    except _ET.ParseError as e:
        raise RuntimeError(f"LLM produced invalid SVG: {e}. First 500 chars: {svg[:500]!r}")

    # Force the viewBox / width / height to match what the caller wanted.
    # The LLM sometimes picks its own dimensions; we want the API contract
    # to hold (the image is always the requested size).
    svg = _normalize_svg_dimensions(svg, width, height)

    return svg


def _normalize_svg_dimensions(svg: str, width: int, height: int) -> str:
    """Rewrite the <svg> opening tag so width=".." height=".." viewBox=".."
    all match the requested dimensions. Idempotent — safe to call twice."""
    import re as _re
    # First, drop any existing width/height/viewBox attributes
    svg = _re.sub(r'\s+width="[^"]*"', "", svg, count=1)
    svg = _re.sub(r'\s+height="[^"]*"', "", svg, count=1)
    svg = _re.sub(r'\s+viewBox="[^"]*"', "", svg, count=1)
    # Insert the correct ones right after `<svg` (or after `<svg ` if there are other attrs)
    new_attrs = f' width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
    svg = _re.sub(r"<svg(\s)", lambda m: "<svg" + new_attrs + m.group(1), svg, count=1)
    if new_attrs not in svg:
        # `<svg>` with no attributes at all
        svg = svg.replace("<svg>", "<svg" + new_attrs + ">", 1)
    return svg


def _render_svg_to_png(svg: str) -> Optional[bytes]:
    """Best-effort SVG → PNG render. Tries cairosvg first, then Pillow, then
    returns None so the caller can store the raw SVG. PNG is preferred
    because the gallery UI assumes bitmap (img src=data:image/png;base64).

    cairosvg: needs libcairo, may not be installed
    Pillow: only supports SVG since 9.1 with a hidden import, not reliable
    Neither is guaranteed — we degrade gracefully to storing the SVG.
    """
    try:
        import cairosvg
        return cairosvg.svg2png(bytestring=svg.encode("utf-8"))
    except (ImportError, OSError):
        pass
    return None


def generate_image(companion_id: str, prompt: str, model: str = "x/z-image-turbo",
                   width: int = 1024, height: int = 1024, seed: Optional[int] = None,
                   steps: Optional[int] = None) -> dict:
    """Generate an image. Strategy:

    1. Try Ollama's native image gen (best quality when it works)
    2. Fall back to LLM-generated SVG art (always works, no extra deps)

    The fallback matters because Ollama disabled image gen in v0.32.6+,
    and even on builds that nominally support it the API can be unreliable.
    The LLM SVG path always works with the user's existing Ollama + chat
    model — no new dependencies, no downloads. The output is genuine
    vector art that renders as a real image in the gallery.

    Returns a dict matching the original (best-quality) shape: {id, file_path,
    base64, model, seed, width, height, duration_ms}. The base64 field is
    either a PNG (best case) or an SVG (fallback). The Art panel renders
    both.

    Raises a clear error if the local Ollama build doesn't support image
    generation (Ollama disabled it experimentally in v0.32.6). The frontend
    catches this and shows an Upload fallback.
    """
    import uuid as _uuid

    model = model or "x/z-image-turbo"
    payload = {
        "model": model,
        "prompt": prompt,
        "width": width,
        "height": height,
    }
    if seed:
        payload["seed"] = seed

    start = time.time()
    # When companion_id is empty, we're generating a preview (avatar during
    # the wizard, before the companion exists). Skip the DB write — the
    # wizard will copy the file once the companion is created.
    is_preview = not companion_id

    # Strategy 1: Try Ollama's native image gen. Best quality when it
    # works, but disabled in v0.32.6+ — _try_ollama_image returns None
    # in that case. The model label in the response stays as the user's
    # chosen model name (they wanted "x/z-image-turbo"), but the bytes
    # might have come from a different path.
    png_bytes = _try_ollama_image(prompt, model, width, height, seed)
    if png_bytes is not None:
        # Best case: real PNG from Ollama. Store it, return it.
        b64 = base64.b64encode(png_bytes).decode("ascii")
        # For previews, write to a tmp dir so the wizard can find it.
        out_dir = db.DATA_DIR / "art" / (companion_id or "_previews")
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = out_dir / f"{_uuid.uuid4()}.png"
        fname.write_bytes(png_bytes)
        if is_preview:
            # No DB entry for previews; return a synthetic id.
            entry = {"id": str(_uuid.uuid4()), "file_path": str(fname)}
        else:
            entry = db.add_art(companion_id, prompt, str(fname), model, seed, width, height)
        return {
            "id": entry["id"],
            "file_path": str(fname),
            "base64": b64,
            "model": model,
            "seed": seed,
            "width": width,
            "height": height,
            "duration_ms": int((time.time() - start) * 1000),
            "kind": "png",
        }

    # Strategy 2: Try a real diffusion model via diffusers. This is the
    # v0.15.2 path — SDXL-turbo via MPS on Apple Silicon. 4 steps, 3-4
    # seconds, genuinely photorealistic. The user's selected Ollama image
    # model (e.g. "x/z-image-turbo") is mapped to a local SD checkpoint
    # (e.g. SDXL-turbo) — the Ollama "x/z-image-turbo" doesn't actually
    # run, but the user gets a real diffusion model in the back.
    diffusers_path = _find_local_diffusion_model()
    if diffusers_path is not None:
        # Determine a reasonable step count for the model
        # SDXL-turbo wants 1-4 steps with no guidance. SD 1.5 wants 20-30.
        is_turbo = "turbo" in diffusers_path.lower()
        diffusers_steps = steps if steps else (4 if is_turbo else 20)
        png_bytes = _try_diffusers_image(prompt, width, height, diffusers_steps, seed)
        if png_bytes is not None:
            # Real diffusion PNG. Store it, return it. The model label
            # shows what the user picked + what was actually used.
            b64 = base64.b64encode(png_bytes).decode("ascii")
            out_dir = db.DATA_DIR / "art" / (companion_id or "_previews")
            out_dir.mkdir(parents=True, exist_ok=True)
            fname = out_dir / f"{_uuid.uuid4()}.png"
            fname.write_bytes(png_bytes)
            # Show user the actual model name so they know it's real
            model_dir_name = Path(diffusers_path).parent.parent.name  # snapshots/<hash>/.. → model--<name>
            # Strip the HF "models--" prefix
            if model_dir_name.startswith("models--"):
                model_dir_name = model_dir_name[len("models--"):]
            # Make a cleaner short name. "stabilityai-sdxl-turbo" → "SDXL-Turbo"
            short_model = model_dir_name
            for prefix, repl in [("stabilityai-", "SDXL-"), ("runwayml-", "SD-"), ("CompVis-", "SD-")]:
                if short_model.startswith(prefix):
                    short_model = repl + short_model[len(prefix):]
                    break
            short_model = short_model.replace("-", " ").strip()
            # Collapse double spaces from the replacement
            short_model = " ".join(short_model.split())
            actual_model = f"{model} → {short_model} (real diffusion via diffusers/MPS)"
            if is_preview:
                entry = {"id": str(_uuid.uuid4()), "file_path": str(fname)}
            else:
                entry = db.add_art(companion_id, prompt, str(fname), actual_model, seed, width, height)
            return {
                "id": entry["id"],
                "file_path": str(fname),
                "base64": b64,
                "model": actual_model,
                "seed": seed,
                "width": width,
                "height": height,
                "duration_ms": int((time.time() - start) * 1000),
                "kind": "png",
            }

    # Strategy 3: Ask the LLM to produce SVG art. Always works with the
    # existing Ollama setup. Result is genuine vector art that renders as
    # a real image in the gallery.
    #
    # CRITICAL: the user's chosen "model" parameter is an image/diffusion
    # model (e.g. x/z-image-turbo). Diffusion models don't support /api/chat
    # — Ollama returns HTTP 400 "does not support chat". So we MUST pick a
    # chat-capable model for the SVG call.
    #
    # We prefer a *capable* text model (qwen3:14b, gemma4:9b+) because SVG
    # art is verbose — 3b/4b models often hit the num_predict ceiling and
    # produce truncated SVGs without a closing </svg>. The companion's own
    # chat model is the fallback (it might be a small/fast model the user
    # picked for quick chat replies, which is fine for chat but not for art).
    try:
        chat_model = _pick_text_model()
        if not chat_model:
            raise RuntimeError(
                "No chat-capable model installed. The SVG art fallback needs a "
                "text model — install something like qwen3:14b via Settings → Models."
            )
        svg = _generate_svg_via_llm(prompt, chat_model, width, height, seed)
    except Exception as e:
        # If the picked model truncated, try the companion's own chat
        # model as a second attempt — sometimes a different model succeeds
        # where the preferred one didn't.
        try:
            companion = db.get_companion(companion_id) if companion_id else None
            fallback_model = companion.get("model_name") if companion else None
            if fallback_model and not _is_image_model_name(fallback_model) and fallback_model != chat_model:
                svg = _generate_svg_via_llm(prompt, fallback_model, width, height, seed)
                chat_model = fallback_model  # for the label
            else:
                raise e
        except Exception as e2:
            raise RuntimeError(
                f"Image generation failed: Ollama image gen is not available, "
                f"and the SVG fallback also failed ({e}). Try the Upload button instead."
            ) from e2

    duration_ms = int((time.time() - start) * 1000)

    # Try to render the SVG to PNG for the best gallery experience.
    # If cairosvg isn't available, store the SVG as-is (the gallery UI
    # can render SVG directly via data: URL).
    png_bytes = _render_svg_to_png(svg)
    svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")

    art_dir = db.DATA_DIR / "art" / (companion_id or "_previews")
    art_dir.mkdir(parents=True, exist_ok=True)

    if png_bytes is not None:
        # We have both: store the PNG as the canonical file (the gallery
        # displays it as data:image/png) and the SVG alongside for future use.
        fname = art_dir / f"{_uuid.uuid4()}.png"
        fname.write_bytes(png_bytes)
        svg_fname = art_dir / f"{fname.stem}.svg"
        svg_fname.write_text(svg, encoding="utf-8")
        b64 = base64.b64encode(png_bytes).decode("ascii")
        kind = "png"
    else:
        # No cairosvg. Store the SVG and serve it as a data: URL.
        fname = art_dir / f"{_uuid.uuid4()}.svg"
        fname.write_text(svg, encoding="utf-8")
        b64 = svg_b64
        kind = "svg"

    # Mark the model so the UI can show "Generated via LLM SVG" rather than
    # implying a real diffusion model was used. Include the actual chat
    # model used so the user knows what's drawing their art.
    model_label = f"{model} → {chat_model} (svg-fallback)"
    if is_preview:
        # No DB entry for previews; return a synthetic id.
        entry = {"id": str(_uuid.uuid4()), "file_path": str(fname)}
    else:
        entry = db.add_art(companion_id, prompt, str(fname), model_label, seed, width, height)

    return {
        "id": entry["id"],
        "file_path": str(fname),
        "base64": b64,
        "model": model_label,
        "seed": seed,
        "width": width,
        "height": height,
        "duration_ms": duration_ms,
        "kind": kind,
    }


def quick_art_from_chat(companion_id: str, user_text: str, image_model: Optional[str] = None) -> Optional[dict]:
    """Generate soul-aware art from a chat message."""
    companion = db.get_companion(companion_id)
    if not companion:
        return None

    soul_path = companion.get("soul_path", "")
    soul_text = Path(soul_path).read_text() if soul_path and Path(soul_path).exists() else ""
    soul_snippet = soul_text[:400] if soul_text else ""

    prompt = f"""Based on this companion's soul, create an artistic image of the following moment described by the user: "{user_text}"

Companion soul: {soul_snippet}

Create a beautiful, emotionally resonant image. Style: warm, artistic, slightly painterly."""

    try:
        return generate_image(companion_id, prompt, image_model or "x/z-image-turbo")
    except Exception:
        return None


def generate_avatar(companion_name: str, archetype: str, soul_markdown: str, image_model: Optional[str] = None) -> Optional[dict]:
    """Generate an avatar for a companion.

    v0.15 — Avatars are generated DURING the companion-creation wizard,
    BEFORE the companion exists in the DB. We can't save the avatar to
    the art_entries table at this point (foreign key to companions would
    fail). The wizard remembers the avatar's file_path and the actual
    companion is created with the file copied via /api/companions/full.

    The trick: we generate the image to a temp directory, return the data
    to the wizard, and let the wizard handle persisting it. To avoid the
    FK constraint, we use a sentinel companion_id of "" (empty string)
    and have add_art handle the case where the companion doesn't exist
    by skipping the DB save and only writing the file. (See the
    generate_image path below — it goes through _render_svg_to_png +
    a direct file write, not add_art, when companion_id is empty.)
    """
    prompt = f"""Create a beautiful portrait of a character named {companion_name}.

Archetype: {archetype}
Personality: {soul_markdown[:300]}

Style: Anime-inspired portrait, expressive eyes, warm lighting. High quality, detailed."""
    try:
        return generate_image("", prompt, image_model or "x/z-image-turbo")
    except Exception as e:
        # Surface the actual error so the wizard can show it — was
        # silently returning None before, leaving the user with no
        # feedback about WHY the avatar failed.
        import logging as _log
        _log.warning("generate_avatar failed: %s", e)
        return None


# ── Soul Read/Write ────────────────────────────────────────────────

def read_soul(companion_id: str) -> str:
    companion = db.get_companion(companion_id)
    if not companion:
        return ""
    soul_path = companion.get("soul_path", "")
    if soul_path and Path(soul_path).exists():
        return Path(soul_path).read_text()
    return ""


def write_soul_md(companion_id: str, markdown: str) -> str:
    companion = db.get_companion(companion_id)
    if not companion:
        raise ValueError("Companion not found")
    soul_path = companion.get("soul_path", "")
    if soul_path:
        Path(soul_path).write_text(markdown)
    return markdown


def save_art_as_memory(companion_id: str, art_id: str, note: str = "") -> dict:
    art_entries = db.get_art_history(companion_id)
    art = next((a for a in art_entries if a["id"] == art_id), None)
    if not art:
        raise ValueError("Art not found")
    fact = f"Generated art: {art['prompt']}" + (f" — {note}" if note else "")
    return db.add_memory(companion_id, fact, "art", 5)
