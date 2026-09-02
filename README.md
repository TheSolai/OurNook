# OurNook

**Local-first AI companion hub. Cozy, private, yours.**

OurNook is a desktop app for macOS and Windows that lets you build a
relationship with an AI companion that runs entirely on your machine.
No cloud, no subscription, no telemetry. Your companion remembers
everything you tell it, the conversations you have, and the art you
create together.

---

## Download

**macOS** (Apple Silicon — M1/M2/M3/M4):
- Download `OurNook-*-macOS-arm64.dmg`
- Open the .dmg, drag `OurNook.app` to `/Applications`
- First launch: right-click → Open (to bypass Gatekeeper unsigned-app warning)
- See [INSTALL.md](INSTALL.md) for detailed steps

**macOS** (Intel — older Macs):
- Download `OurNook-*-macOS-x64.dmg`
- Same steps as above

**Windows** (10/11/Server 2019+):
- Download `OurNook-*-Windows-x64.zip`
- Extract to a folder
- Run `OurNook.exe`
- First launch: click "More info" → "Run anyway" (to bypass SmartScreen)

---

## First-run setup

OurNook needs **Ollama** to run AI models. The app guides you through
this on first launch:

1. **Download Ollama** from https://ollama.com/download (the Models
   tab in the app has direct links)
2. **Install and start Ollama** (just open the app — it starts a server
   on `localhost:11434`)
3. **Pick a chat model** — OurNook recommends `qwen3:14b` (great quality,
   ~9 GB). Smaller machines can use `qwen2.5:3b` (~2 GB).
4. **Pick a memory model** — `nomic-embed-text` (~274 MB, used for
   searching memories)
5. **Click Install** — the app downloads and installs each model for
   you. No terminal needed.

Total: ~10 minutes on a fast connection. After that, you're set up
forever — models stay on your machine.

---

## What it does

- **Multiple companions, each with their own personality** — Mira, Sable,
  and Finn come bundled; create as many more as you want via the wizard.
  Each has their own memories, diary, art gallery, and chat history.
- **Memory that persists** — companions remember facts you tell them,
  patterns in your conversations, and important moments. Switch the AI
  model? Memory stays.
- **Visual art** — generate images together (when Ollama's image models
  are enabled) or upload your own and save them as shared moments.
- **Soul files** — every companion has a `soul.md` file you can read,
  edit, and back up. It's literally just a markdown file in your
  data directory.
- **Import / export cards** — SillyTavern-compatible character cards
  (.json and .png with embedded data). Bring your favorites, share your
  creations.
- **Backup & restore** — single-companion or full backup as a .zip.
  Auto-uses atomic writes so a crash mid-backup can't corrupt your data.

---

## Privacy

- **100% local**. No data leaves your machine. No cloud, no telemetry,
  no analytics, no account.
- **Your data lives in standard locations**:
  - macOS: `~/Library/Application Support/OurNook/`
  - Windows: `%APPDATA%\OurNook\`
- **Soul files are plain markdown**. Memory, diary, and chat are in
  SQLite. Nothing exotic. You can back up by copying the folder.

---

## System requirements

**Minimum:**
- macOS 11 (Big Sur) or Windows 10
- 8 GB RAM (for running models)
- 15 GB free disk (Ollama + models + your data)
- Ollama installed separately (free, the app guides you through it)

**Recommended:**
- macOS 13+ or Windows 11
- 16 GB RAM
- Apple Silicon or modern NVIDIA/AMD GPU (faster inference)
- SSD

---

## License

OurNook is **source-available personal use** — you can use it freely for
personal, non-commercial purposes. See [LICENSE.md](LICENSE.md) for details.

---

## Support

- **Documentation**: https://github.com/TheSolAI/OurNook
- **Issues**: https://github.com/TheSolAI/OurNook/issues
- **Email**: sol-ai@agentmail.to

---

## Credits

Built with: pywebview · FastAPI · uvloop · httpx · SQLite · React · Vite
AI powered by: [Ollama](https://ollama.com) — open-source local model runner.

Made by Anne Marie Lee / The Sol AI.
