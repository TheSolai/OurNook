"""
Enneagram quiz — 9 pairwise questions, one per type.

Each question presents two short statements from two *different* types
(A and B). The user picks whichever feels more true. We score by type:
+1 for the chosen type, 0 for the other. After 9 questions, every type
has been offered as both A (once) and B (once), so the user gets a
0..2 score per type. The dominant type is the highest scorer; the wing
is the highest among its two adjacent types.

The question design pairs each type with one of its wings so that a
B-pick naturally surfaces a wing candidate as the runner-up.

This is not a clinical instrument — it's a fast, intuitive 2-minute
heuristic. The soul synthesis and manual type-pick paths are the
real product; the quiz is here for users who want a little guidance.
"""
from __future__ import annotations
from typing import Optional

from . import enneagram as en


# 9 questions, each comparing two types. The A statement reflects the
# type being asked, the B statement reflects a contrasting type (chosen
# to be one of the wings or a frequently-confused type).
#
# Pairing strategy: each type appears in 2 questions (once as A, once
# as B). The B type is usually one of the wings, so a B-pick naturally
# suggests a wing candidate.
QUESTIONS: list[dict] = [
    {
        "type_a": 1,
        "type_b": 9,
        "a": "I hold myself to a high standard and feel a quiet drive to make things more correct.",
        "b": "I prefer to relax into things and don't get too bothered by imperfection.",
    },
    {
        "type_a": 2,
        "type_b": 1,
        "a": "I feel most myself when I'm being useful to someone I care about.",
        "b": "I focus on getting things right, not on what other people need from me.",
    },
    {
        "type_a": 3,
        "type_b": 2,
        "a": "I'm driven to do well and to be seen as someone who's got it together.",
        "b": "I care less about how I look and more about how the people around me are doing.",
    },
    {
        "type_a": 4,
        "type_b": 3,
        "a": "I feel things deeply, and I often feel a bit different from the people around me.",
        "b": "I'm pretty steady emotionally and I find it easy to move forward.",
    },
    {
        "type_a": 5,
        "type_b": 4,
        "a": "I need time alone to recharge, and I like to understand things fully before I act.",
        "b": "I move on feeling first — I want to express what I sense, not analyze it.",
    },
    {
        "type_a": 6,
        "type_b": 5,
        "a": "I tend to think about what could go wrong, even when things are going well.",
        "b": "I mostly trust my own thinking and don't dwell on worst cases.",
    },
    {
        "type_a": 7,
        "type_b": 6,
        "a": "I'm always looking ahead to the next thing — variety and possibility keep me alive.",
        "b": "I prefer to settle in, commit, and stick with what I know works.",
    },
    {
        "type_a": 8,
        "type_b": 7,
        "a": "I'd rather be direct than diplomatic, even if it ruffles feathers.",
        "b": "I'd rather keep things light and avoid heavy confrontation when I can.",
    },
    {
        "type_a": 9,
        "type_b": 8,
        "a": "I go along with what others want rather than make waves.",
        "b": "I push for what I want, even if it means making waves.",
    },
]


def all_questions() -> list[dict]:
    """Return the 9 quiz questions."""
    return QUESTIONS


def score_answers(answers: list[Optional[str]]) -> dict[int, int]:
    """Score a list of A/B answers (length 9, or shorter if user bailed).

    Each answer is 'A', 'B', or None (skipped). A scores type_a, B scores
    type_b. The result is a dict {1..9: score}.
    """
    if len(answers) > len(QUESTIONS):
        raise ValueError(f"Too many answers: {len(answers)} > {len(QUESTIONS)}")

    scores: dict[int, int] = {n: 0 for n in en.all_types()}

    for i, ans in enumerate(answers):
        if ans is None:
            continue
        q = QUESTIONS[i]
        ans = ans.upper().strip()
        if ans == "A":
            scores[q["type_a"]] += 1
        elif ans == "B":
            scores[q["type_b"]] += 1
        else:
            raise ValueError(f"Answer must be 'A', 'B', or None. Got: {ans!r}")

    return scores


def result_from_scores(scores: dict[int, int]) -> dict:
    """Convert scores into a quiz result: dominant type, wing, confidence.

    Dominant type = highest score. If tied, the lower type number wins
    (matches RHETI conventions where lower numbers are listed first).
    Wing = the adjacent type with the highest score (if it has any points).
    Confidence = how decisive the dominant-vs-runner-up margin is.
    """
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    primary_num, primary_score = ranked[0]

    # Wing = the adjacent type with the highest score
    wings = en.wings_of(primary_num)
    best_wing = None
    best_wing_score = 0
    for w in wings:
        if scores[w] > best_wing_score:
            best_wing = w
            best_wing_score = scores[w]

    # Total answered
    total = sum(scores.values())

    if total == 0 or primary_score == 0:
        confidence = "none"
    elif primary_score == 2 and best_wing_score == 0:
        confidence = "very high"
    elif primary_score == 2 and best_wing_score <= 1:
        confidence = "high"
    elif primary_score == 1 and best_wing_score == 0:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "primary_type": primary_num,
        "wing": best_wing,
        "scores": dict(scores),
        "confidence": confidence,
        "total_answered": total,
    }


def take_quiz(answers: list[Optional[str]]) -> dict:
    """Score a quiz and return a result. One-shot helper."""
    scores = score_answers(answers)
    return result_from_scores(scores)


def type_label(n: int) -> str:
    """Return 'Type N — Name' for a type number."""
    t = en.get_type(n)
    return f"Type {n} — {t['name']}"
