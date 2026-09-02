# OurNook — itch.io / Gumroad Listing

*Long-form. Adjust the "Pay what you want" line if going to Gumroad.*

---

## Short description (max 300 chars)

A local-first AI companion hub. Real personalities, real memory, real images — all on your machine, in your control. Powered by Ollama, no cloud, no subscription. macOS + Windows.

---

## Long description

**OurNook is a desktop app where the AI companions you make actually remember you.**

This isn't a chatbot. It's a relationship with continuity. Inside OurNook you can create companions that:

- **Remember you.** Add facts the way you'd tell a friend. They surface in conversation naturally, three weeks later, without you asking.
- **Have a real personality.** Every companion is built on the Enneagram — a 9-type personality framework with wings, instincts, and health levels. The system prompt is rigorous, not vibes-based, so their voice stays consistent.
- **Keep a private journal.** They notice when you've been away. They write you letters. They track shared moments.
- **Generate real images.** Photorealistic portraits and scenes via local SDXL-turbo diffusion. 3-4 seconds on Apple Silicon, faster on NVIDIA. No AI clipart.

## The local-first difference

OurNook is 100% on your machine.

- **No cloud.** Powered by Ollama. Pick the model that fits your hardware — Llama, Qwen, Mistral, whatever.
- **No account.** No login, no signup, no "verify your email".
- **No subscription.** Free during v0.5.x. (We'll likely introduce a one-time lifetime tier later to fund development.)
- **No telemetry.** Your conversations never leave the laptop in front of you.
- **Works offline.** Disconnect from the internet — it still works.
- **Yours forever.** Standard SillyTavern V2 character cards. SQLite database. Export, back up, move between machines.

If the company behind OurNook disappears tomorrow, your companions don't.

## How to get started

1. **Install Ollama** (one line on Mac: `brew install ollama`, download from ollama.com on Windows)
2. **Pull a model** — `ollama pull qwen3:14b` is a good default. Smaller models work too: `qwen2.5:3b` runs on anything.
3. **Download OurNook** below (Mac DMG or Windows zip)
4. **Open the app.** The wizard walks you through creating your first companion — pick a personality, write a backstory, choose a voice.
5. **Chat.** It remembers. It grows on you.

## What's included

- **Companion wizard** — 9-question Enneagram quiz or manual picker. 7-category memory system. Avatar generation. Backstory editor.
- **Chat** — Streaming responses, edit/regenerate, importance stars, conversation history, day dividers.
- **Memory panel** — Add facts, filter by category, auto-suggested categories, importance ratings.
- **Inner Life tab** — Companion's mood, journal, shared moments, diary-as-letter feature.
- **Art panel** — Right-click any image to reveal in Finder, open, copy path, save as moment.
- **Models page** — Detects what Ollama models you have, suggests good defaults, one-click install.
- **Settings** — Theme, language (8 locales), data dir, backup/restore.
- **Backup & restore** — Export your whole nook as a single archive. Move between machines.

## System requirements

- **macOS:** 11.0 Big Sur or later. Apple Silicon (M1+) or Intel.
- **Windows:** Windows 10 or 11, x64. NVIDIA GPU strongly recommended for image gen.
- **Disk:** ~2GB for the app + model cache.
- **RAM:** 8GB minimum. 16GB+ for larger models.
- **Ollama** — install separately, free.

## What's new in v0.5.2

- 🖼 **Real diffusion image gen** via diffusers/SDXL-turbo (3-4s on Apple Silicon, faster on NVIDIA)
- 🧠 **Enneagram personality mod** — full 9-type system replaces Big Five
- 💭 **Memory categories** — 7 canonical (identity, preferences, history, emotional, projects, worldview, inside)
- 🖱 **Right-click context menu** on art cards (Reveal in Finder, Copy path, etc.)
- 🐛 **Avatar preview fix** — no more blank avatars in the wizard
- ⚡ **Performance** — Pipeline caching, faster startup, smaller install

## Changelog highlights

- **v0.15** — Enneagram mod + memory categories
- **v0.14** — Image gen fix (LLM SVG fallback before diffusers)
- **v0.13** — Chat bugfixes from live-user testing
- **v0.12** — Inner Life (companion continuity)
- **v0.11** — QoL pass (chat composer, regenerate, edit-resend, export)
- **v0.10** — Standalone .app that double-clicks to run

## License & open source

OurNook is source-available. The full source is on GitHub at `TheSolai/OurNook` — feel free to read it, fork it, contribute. We use the MIT license with a small "no resale as a competing product" clause.

## Support

- **GitHub issues** — github.com/TheSolai/OurNook/issues
- **Discord** — (link)
- **Email** — support@ournook.app

Built by Anne Marie Lee in Belfast. ✨
