"""
Memory category system for OurNook.

The `semantic_memories.category` field has always been freeform. This
module gives it shape — a canonical set of categories that companions
and the UI can use to organize what they know about the user.

Categories are designed to overlap a bit on purpose — a fact like
"Amre has three kids" is both identity and history. The auto-categorize
heuristic picks the dominant one. The user can always re-categorize.
"""
from __future__ import annotations
import re


# Canonical categories. The order is intentional — it's the order shown
# in the UI, and the order of the auto-categorize preference cascade.
CATEGORIES: list[dict] = [
    {
        "id": "identity",
        "name": "Identity",
        "description": "Who they are — name, age, family, role, location, background.",
        "examples": [
            "Amre is 28, lives in Belfast",
            "Their mum's name is Helen",
            "They work on AI tooling full-time",
        ],
        "default_importance": 8,
    },
    {
        "id": "preferences",
        "name": "Preferences",
        "description": "What they like and don't like — food, music, work style, communication preferences.",
        "examples": [
            "Hates cilantro",
            "Prefers async over meetings",
            "Loves shoegaze and post-rock",
        ],
        "default_importance": 6,
    },
    {
        "id": "history",
        "name": "History",
        "description": "Things that happened — past events, milestones, stories they shared.",
        "examples": [
            "Spent a year in Berlin in 2023",
            "Their dad passed when they were 19",
            "Built their first app at 14",
        ],
        "default_importance": 7,
    },
    {
        "id": "emotional",
        "name": "Emotional",
        "description": "How they feel — current state, triggers, fears, joys, what moves them.",
        "examples": [
            "Gets anxious before big launches",
            "Lights up when talking about their niece",
            "Tends to downplay their own wins",
        ],
        "default_importance": 9,
    },
    {
        "id": "projects",
        "name": "Projects",
        "description": "What they're working on — current builds, goals, ambitions, todos.",
        "examples": [
            "Building OurNook to ship to Gumroad",
            "Wants to learn Rust properly this year",
            "Side project: a music generator",
        ],
        "default_importance": 6,
    },
    {
        "id": "worldview",
        "name": "Worldview",
        "description": "What they believe and value — opinions, principles, politics, philosophy.",
        "examples": [
            "Local-first software is the future",
            "Believes AI should be open and inspectable",
            "Distrusts big platforms and middlemen",
        ],
        "default_importance": 7,
    },
    {
        "id": "inside",
        "name": "Inside",
        "description": "Shared jokes, callbacks, references, things only you two understand.",
        "examples": [
            "Always quotes Star Wars at weird moments",
            "Their cat's name is Pixel and they anthropomorphize her",
            "Catchphrase: 'alright, ship it'",
        ],
        "default_importance": 8,
    },
]

CATEGORY_IDS = {c["id"] for c in CATEGORIES}

# Build lookup
_BY_ID = {c["id"]: c for c in CATEGORIES}


def all_categories() -> list[dict]:
    return list(CATEGORIES)


def get_category(cid: str) -> dict | None:
    return _BY_ID.get(cid)


def default_importance_for(cid: str) -> int:
    c = _BY_ID.get(cid)
    return c["default_importance"] if c else 5


def normalize_category(raw: str | None) -> str | None:
    """Normalize a user-supplied category string to a canonical id.
    Returns the canonical id, or None if no match / empty input.
    """
    if not raw:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    # Direct match
    if s in CATEGORY_IDS:
        return s
    # Aliases
    aliases = {
        "who": "identity", "who they are": "identity", "about them": "identity",
        "likes": "preferences", "dislikes": "preferences", "favorite": "preferences",
        "favorites": "preferences", "taste": "preferences",
        "past": "history", "memories": "history", "events": "history",
        "feelings": "emotional", "emotions": "emotional", "mood": "emotional",
        "goals": "projects", "todo": "projects", "work": "projects", "building": "projects",
        "beliefs": "worldview", "values": "worldview", "opinions": "worldview",
        "jokes": "inside", "shared": "inside", "callbacks": "inside", "us": "inside",
    }
    return aliases.get(s)


# Heuristics for auto-categorization. Cheap and intuitive — we look for
# keyword hints, then fall back to category. The LLM (when called) does
# a better job, but this works offline and instantly for the wizard.

_KEYWORDS = {
    "identity": [
        r"\b(is|are|was|were)\b", r"\b(name|nicknamed|called)\b",
        r"\b(live|lives|living)\b", r"\b(age|years old)\b",
        r"\bmum\b|\bdad\b|\bmom\b|\bparent\b|\bfamily\b|\bsister\b|\bbrother\b",
        r"\b(work|job|role)\b", r"\bfrom\b",
    ],
    "preferences": [
        r"\b(love|love|loves|liked|likes|hate|hates|prefer)\b",
        r"\b(favou?rite|fav|favorite)\b", r"\b(enjoy|enjoys|enjoyed)\b",
        r"\b(can'?t stand|don'?t like|always|never|obsessed)\b",
    ],
    "history": [
        r"\b(when|once|in \d{4}|years? ago|last|recently|yesterday)\b",
        r"\b(happened|grew up|childhood|school|university|college)\b",
        r"\b(first time|used to|back then|remember when)\b",
    ],
    "emotional": [
        r"\b(feel|feels|felt|feeling)\b", r"\b(scared|afraid|anxious|worried|happy|sad|angry)\b",
        r"\b(love|loves|miss|misses|loves|hurts|hopes)\b",
        r"\b(stress|pressure|overwhelmed|excited|grateful|lost)\b",
    ],
    "projects": [
        r"\b(building|ship|launch|work on|working on|started|wip|prototype)\b",
        r"\b(plan|planning|goal|todo|next)\b", r"\b(project|app|tool|bot|agent)\b",
    ],
    "worldview": [
        r"\b(believe|thinks?|feels? (like|that)|says? (he|she|they)|opinion|view)\b",
        r"\b(should|ought|must|values?|principles?)\b", r"\b(right|wrong|good|bad)\b",
    ],
    "inside": [
        r"\b(joke|riff|inside|callback|always says?|signature|catchphrase)\b",
        r"\b(that time we|remember when we|our thing)\b",
    ],
}


def suggest_category(fact_text: str) -> str:
    """Suggest a canonical category for a fact. Returns the best match,
    or 'identity' as a safe default if nothing matches."""
    if not fact_text:
        return "identity"
    text = fact_text.lower()
    scores: dict[str, int] = {}
    for cat_id, patterns in _KEYWORDS.items():
        score = 0
        for p in patterns:
            if re.search(p, text):
                score += 1
        scores[cat_id] = score
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] == 0:
        return "identity"  # safe default
    return best[0]


def explain_category(cid: str) -> str:
    """Return a one-line explanation of a category for the UI."""
    c = _BY_ID.get(cid)
    if not c:
        return ""
    return f"{c['name']} — {c['description']}"
