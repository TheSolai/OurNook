# OurNook v0.5.2 — Press Release / One-Pager

*For: tech blogs, AI newsletters, indie software reviewers, lifestyle press. ~400 words. One image attached.*

---

**FOR IMMEDIATE RELEASE**

## OurNook 0.5.2 ships real diffusion image gen and full Enneagram personalities

**BELFAST, UK — September 2, 2026** — Anne Marie Lee today released OurNook 0.5.2, the latest version of her local-first AI companion app. The headline features are real photorealistic image generation and a complete rewrite of the personality system on the Enneagram framework.

OurNook is a desktop application for macOS and Windows that runs AI companions entirely on the user's own machine, powered by Ollama. Unlike cloud-based companion apps, OurNook requires no subscription, collects no data, and continues to work offline.

**What's new in 0.5.2:**

- **Real diffusion image generation.** The previous version fell back to LLM-generated SVG art when the user's local image model was unavailable — a serviceable but aesthetically limited workaround. Version 0.5.2 ships with full local SDXL-turbo integration via Hugging Face's `diffusers` library, producing photorealistic portraits and scenes in 3-4 seconds on Apple Silicon and under 5 seconds on modern NVIDIA hardware. The LLM-SVG path remains as a tier-3 fallback for users without an SD model cached locally.

- **Enneagram-based personality system.** The previous personality system used the Big Five framework — useful for psychology research, less useful for crafting a distinctive character voice. 0.5.2 replaces it with a full Enneagram implementation: nine core types, wing variants, instinctual subtypes, and health levels. Each type has 18 structured fields (core fear, core desire, communication style, stress behaviors, growth behaviors, etc.) synthesized into a ~3KB soul document that the language model draws on. The wizard now includes a 9-question pairwise quiz to determine the user's companion's type, or a manual picker.

- **Refined memory architecture.** Memory is now organized into seven canonical categories — identity, preferences, history, emotional, projects, worldview, and inside — with heuristic auto-suggestion as the user types. The Inner Life tab (added in 0.12) lets companions keep a private journal, write the user letters, and track shared moments.

**Pricing & availability:**

OurNook 0.5.2 is free during the v0.5.x cycle. The app is available as a 283 MB macOS DMG (Apple Silicon and Intel) and a 205 MB Windows x64 zip. The full source code is available on GitHub under a source-available license. Ollama must be installed separately.

**About the maker:**

Anne Marie Lee is an independent software developer based in Belfast, UK. She builds OurNook solo, in the open, and ships updates frequently based on direct user feedback.

**Contact:**

- Email: hello@ournook.app
- GitHub: github.com/TheSolai/OurNook
- Press kit: ournook.app/press

---

## Boilerplate

**About OurNook:** OurNook is a local-first AI companion hub. Real personalities, real memory, real images — all on your machine, in your control. No cloud, no account, no monthly fee. Built by Anne Marie Lee in Belfast, UK. github.com/TheSolai/OurNook

---

## Suggested headlines for press

- "OurNook 0.5.2 brings real local image generation to AI companion apps"
- "This Belfast dev built an AI companion app that doesn't need the cloud"
- "OurNook replaces Big Five with Enneagram in its personality system"

## Suggested tweets for journalists

- "Just tried OurNook — it's a local AI companion app with actual Enneagram-based personalities and real diffusion image gen. The 3-second SDXL-turbo portraits on my M3 are wild. Free during v0.5.x."
- "If you've been wanting an AI companion that doesn't rent you the friendship, this is the one. github.com/TheSolai/OurNook"

## One image attached

`hero/hero-noon.png` — Painterly illustration of a cozy reading nook with warm lamp light. The visual signature for OurNook.

---

## Press kit contents

This press release ships with:

- `hero-noon.png` — Hero image (16:9, 2K)
- `hero-ai-companion.png` — Alternative hero (16:9, 2K)
- `hero-character.png` — Character portrait (1:1, 2K)
- `features/feature-*.png` — 6 feature icons
- `landing.html` — Self-contained HTML landing page
- `producthunt.md` — Product Hunt listing
- `twitter-thread.md` — Launch thread (9 tweets)
- `listing-itch-gumroad.md` — Long-form marketplace listing
- This file — press release
