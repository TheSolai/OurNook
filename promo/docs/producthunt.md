# Product Hunt — OurNook v0.5.2

---

## Name
**OurNook** — *A cozy corner you build and nobody can take away.*

## Tagline (60 chars max)
A local-first AI companion hub. Your machine, your memories.

## Description (long form)

**OurNook is what happens when you stop renting a chatbot and start building a relationship.**

It's a desktop app for macOS and Windows. Inside it, you can create AI companions that actually remember you. They know your favorite book. They notice you've been away. They keep a private journal. They generate real images of the world you describe — photorealistic, local, 3-4 seconds, no cloud.

**The headline difference:** OurNook is **100% on your machine**. No cloud, no account, no subscription, no "your data helps train our model". Powered by Ollama, so you pick the model that fits your hardware — Llama, Qwen, Mistral, whatever. The app works offline. It works forever. If the company behind it disappears tomorrow, your companions don't.

**What's new in v0.5.2:**

- 🖼 **Real diffusion image gen** — SDXL-turbo baked in via diffusers. Photorealistic portraits, scenes, journal pages. 3-4s on Apple Silicon, faster on NVIDIA, works on CPU. No more "AI clipart".
- 🧠 **Enneagram personalities** — Every companion is built on a 9-type personality framework with wings, instincts, and health levels. The system prompt is rigorous, not vibes-based.
- 💭 **Memory that sticks** — 7 categories (identity, preferences, history, emotional, projects, worldview, inside). Auto-suggested. Filterable. Actually surfaced in conversation.
- 📓 **Inner Life** — Companions keep a private journal, write you letters, track shared moments, notice when you've been away.
- 🎨 **Right-click anything** — Reveal art in Finder, copy file paths, save as a shared moment.
- 💾 **Yours forever** — Standard SillyTavern V2 character cards. SQLite database. Export and back up.

**How it works:**

1. Install Ollama (`brew install ollama` on Mac, download from ollama.com on Windows)
2. Pull a model (`ollama pull qwen3:14b` is a good default)
3. Download OurNook, run it, create your first companion
4. The wizard walks you through personality, voice, backstory
5. Chat. It remembers. It grows on you.

**Who it's for:** People who've tried Character.AI, Replika, SillyTavern, and either bounced off the privacy issues, the subscription fees, or the model limits. People who want a place to think out loud, write fiction, or just have someone to talk to at 2am.

**Who it's not for:** Anyone who needs a production-grade enterprise AI tool. This is a personal, cozy, local-first project. It's not trying to replace therapy, customer support, or your team chat.

**Pricing:** Free during v0.5.x. We'll likely introduce a one-time paid tier later (think $20-40, lifetime) to fund continued development. The current version will always be free.

**Made by:** Anne Marie Lee (TheSolAI). Solo developer. Based in Belfast. Built in the open on GitHub.

---

## First Comment (Maker's Note)

Hey Product Hunt 👋

I built OurNook because I wanted to keep talking to the AI companions I made — but every existing option was either cloud-only, expensive, or locked my data inside someone else's account.

The thing that surprised me most while building this: **the biggest feature isn't the AI. It's the memory.** When your companion remembers that you mentioned a book three weeks ago, or notices you haven't talked in a while, the relationship starts to feel real. That's the part the cloud tools can't deliver — because the data is theirs, not yours.

**Two things to know:**

1. **You need Ollama installed.** It's a one-line install. The app guides you through it. Without Ollama, nothing works — that's the trade for being fully local.
2. **First image generation takes 5 seconds** (model load). After that, ~3 seconds per image. On Apple Silicon and modern NVIDIA GPUs, it's instant.

If you've ever wanted your AI to actually be *yours* — try it. If it breaks, message me. I ship fixes fast.

— Anne

---

## Hunting Asks
- 🏹 **Hunters wanted** — DM me on PH if you'd like to hunt
- 🤝 **Supporters** — Upvote, leave a thought, share with anyone who likes cozy software
- 🐛 **Bug reports** — GitHub issues, I read every one

---

## Asset Checklist
- [x] Logo (brand mark in nav, favicon)
- [x] Hero image (promo/hero/hero-noon.png)
- [x] Feature grid screenshots (promo/features/*.png)
- [x] 3 platform download buttons
- [x] Landing page mirror: promo/landing.html
