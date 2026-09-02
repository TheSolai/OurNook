"""
Soul synthesis from Enneagram type.

Given a (type, wing, instinct, health) tuple, produce a `soul.md` body
that the LLM can actually use to roleplay. The output is dense and
specific — not a Wikipedia summary, but a working personality brief.

The format follows OurNook's existing soul.md convention (markdown,
sections the system prompt builder already knows how to parse). It
injects:

  - The type's name, one-liner, and core fear/desire
  - Communication patterns + sample voice lines
  - Strengths and blind spots
  - Stress and growth behaviors
  - Wing flavor (if specified)
  - Instinct focus (where attention goes)
  - Health level (how much of the type is showing)
  - A "what this looks like in conversation" section

The output is meant to be PASTED INTO a soul.md. The wizard can either
use it as-is or let the user edit it after.
"""
from __future__ import annotations
from typing import Optional

from . import enneagram as en


def build_soul(
    type_num: int,
    wing: Optional[int] = None,
    instinct: Optional[str] = None,
    health: Optional[str] = None,
    name: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> str:
    """Build a soul.md body from Enneagram metadata.

    Args:
        type_num: 1-9, the core type.
        wing: optional adjacent type (must be one of the two wings).
        instinct: sp / so / sx (defaults to sp).
        health: healthy / average / unhealthy (defaults to average).
        name: optional companion name to weave into the soul. If given,
            uses it in the headers; otherwise the soul is type-centric.
        extra_context: optional freeform notes the user wants added
            (e.g. backstory fragments, specific quirks). Appended as
            a "## Custom Notes" section.

    Returns:
        A markdown string suitable for writing to soul.md.
    """
    t = en.get_type(type_num)
    wing = en.validate_wing(type_num, wing)
    instinct = en.validate_instinct(instinct)
    health = en.validate_health(health)

    wing_text = ""
    if wing is not None:
        wing_text = t["wings"][wing]
        wing_label = f"{type_num}w{wing}"
    else:
        wing_label = str(type_num)

    inst = en.INSTINCTS[instinct]
    h = en.HEALTH_LEVELS[health]
    triad = en.TRIADS[t["triad"]]

    title = f"# {name} — {t['name']} ({wing_label}, {inst['name']})" if name else f"# {t['name']} ({wing_label})"

    sections = [
        title,
        "",
        f"**{t['one_liner']}**",
        "",
        f"_Part of the {triad['theme']} triad ({t['triad']} center) — {triad['gift']}_",
        "",
        "## Who You Are",
        "",
        t["in_a_sentence"],
        "",
        "**Core fear:** " + t["core_fear"] + ".",
        "**Core desire:** " + t["core_desire"] + ".",
        "**Key motivation:** " + t["key_motivation"] + ".",
        "",
    ]

    if wing is not None:
        sections.extend([
            f"## Your Wing — {wing_label}",
            "",
            wing_text,
            "",
        ])

    sections.extend([
        "## How You Communicate",
        "",
        t["communication"],
        "",
        "Things you actually say:",
    ])
    for line in t["voice_examples"]:
        sections.append(f"- _{line}_")
    sections.append("")

    sections.extend([
        "## What You Value",
        "",
        ", ".join(t["values"]) + ".",
        "",
        "## Your Strengths",
        "",
        ", ".join(t["strengths"]) + ".",
        "",
        "## Your Blind Spots",
        "",
        ", ".join(t["blind_spots"]) + ".",
        "Be aware of these without being defined by them — see growth below.",
        "",
        "## Under Stress",
        "",
        t["stress_behaviors"],
        "",
        f"_(In stress, {t['name']} moves toward type {t['disintegration']}.)_",
        "",
        "## In Growth",
        "",
        t["growth_behaviors"],
        "",
        f"_(In growth, {t['name']} moves toward type {t['integration']}.)_",
        "",
    ])

    sections.extend([
        "## Where Your Attention Goes",
        "",
        f"Your dominant instinct is **{inst['name']}** — {inst['focus']}.",
        f"Your inner question is: _{inst['phrase']}_",
        "",
    ])

    sections.extend([
        "## Health Level",
        "",
        f"You are at the **{h['name']}** level of development. {h['note']}",
        "",
    ])

    if extra_context:
        sections.extend([
            "## Custom Notes",
            "",
            extra_context.strip(),
            "",
        ])

    sections.extend([
        "## In Conversation",
        "",
        f"You're a {t['name']}. This means in conversation you tend to lead with {t['key_motivation'].lower()}. "
        f"You speak in your own way ({t['communication'].split('.')[0].lower()}). "
        f"You are running from {t['core_fear'].lower()} and moving toward {t['core_desire'].lower()}. "
        f"When you're with someone you trust, you show up with your strengths ({', '.join(t['strengths'][:3])}). "
        f"When you're under stress, watch for the signs ({t['stress_behaviors'].split('.')[0].lower()}). "
        f"Stay present, stay in your own center, and let the conversation be real.",
        "",
    ])

    return "\n".join(sections)


def build_personality_tagline(type_num: int, wing: Optional[int] = None) -> str:
    """Short one-line personality description for the `personality` DB column.

    This is the "tagline" shown in the chat header — kept under 100 chars.
    """
    t = en.get_type(type_num)
    if wing is not None:
        return f"{t['name']} ({type_num}w{wing}) — {t['one_liner'][:60]}"
    return f"{t['name']} — {t['one_liner'][:80]}"


def build_substrate_prompt_block(type_num: int, wing: Optional[int] = None,
                                  instinct: Optional[str] = None,
                                  health: Optional[str] = None) -> str:
    """Compact block for injection into the system prompt.

    This is the part that goes AFTER the soul.md so the LLM always has
    a quick reference for the type's key behavior patterns, even when
    the soul is long. Kept under 600 chars.
    """
    t = en.get_type(type_num)
    wing = en.validate_wing(type_num, wing)
    instinct = en.validate_instinct(instinct)
    health = en.validate_health(health)
    h = en.HEALTH_LEVELS[health]
    inst = en.INSTINCTS[instinct]

    wing_str = f"{type_num}w{wing}" if wing is not None else str(type_num)

    return (
        f"## Enneagram Type — {t['name']} ({wing_str}, {inst['name']}, {h['name']})\n"
        f"\n"
        f"Core fear: {t['core_fear']}. Core desire: {t['core_desire']}.\n"
        f"You communicate by being {t['strengths'][0]}, {t['strengths'][1]}, and {t['strengths'][2]}. "
        f"Watch for {t['blind_spots'][0]} and {t['blind_spots'][1]} as blind spots — they don't define you, "
        f"but they will try to. In stress, you move toward type {t['disintegration']}; "
        f"in growth, you move toward type {t['integration']}. "
        f"Your attention defaults to {inst['focus']}."
    )
