# Installing OurNook

## macOS

1. **Download** the `.dmg` file (e.g. `OurNook-v0.1.0-macOS-arm64.dmg`)
2. **Double-click** the .dmg to mount it
3. **Drag** the `OurNook` app to the `/Applications` shortcut
4. **Open** Applications → right-click `OurNook` → **Open**
   - This is needed the first time because the app isn't signed with an
     Apple Developer certificate. After this first launch, macOS will
     remember your choice.
5. **Allow** the security prompt ("OurNook is from an unidentified developer")
6. OurNook opens! The first-launch wizard will guide you through installing
   Ollama and your first model.

If you see "OurNook is damaged": open Terminal and run
`xattr -cr /Applications/OurNook.app` then try again.

## Windows

1. **Download** the `.zip` file (e.g. `OurNook-v0.1.0-Windows-x64.zip`)
2. **Right-click** the .zip → **Extract All** to a folder of your choice
   (e.g. `C:\Program Files\OurNook` or just your Desktop)
3. **Open** the extracted folder and **double-click** `OurNook.exe`
4. **Allow** the Windows SmartScreen prompt: "More info" → "Run anyway"
5. OurNook opens! The first-launch wizard will guide you through
   installing Ollama and your first model.

We recommend **pinning OurNook to your taskbar** for easy access:
- Right-click the OurNook icon in the taskbar → Pin

## First-run wizard

When you open OurNook for the first time, you'll see a 4-step setup
wizard. Each step has clear next actions and the Models tab has direct
links to download Ollama for your platform.

The four steps:

1. **Install Ollama** — the local engine that runs your AI. The wizard
   links you to the right download for your platform. After installing,
   click "Re-check" and the dot turns green.
2. **Start Ollama** — Ollama runs in the background. Just open the
   Ollama app once, or the wizard will launch it for you.
3. **Install a chat model** — the wizard recommends `qwen3:14b` (~9 GB,
   good quality). Older machines can use `qwen2.5:3b` (~2 GB).
4. **Install a memory model** — `nomic-embed-text` (~274 MB, used for
   searching memories). Tiny — always install this.

Total: about 10 minutes on a fast connection. After that, you're set up
forever — models stay on your machine and don't need re-downloading.

## Where's my data?

Your companions, memories, diary, and art live in standard locations:

- **macOS**: `~/Library/Application Support/OurNook/`
- **Windows**: `%APPDATA%\OurNook\` (usually `C:\Users\<you>\AppData\Roaming\OurNook\`)

Each companion has its own subdirectory with:
- `soul.md` — the personality file (plain text, you can edit it)
- `art/` — uploaded and generated art

The whole folder is your data. Back it up by copying it. Restore by
copying it back. (Or use the in-app Backup & Restore.)

## Uninstallation

OurNook is fully self-contained. To uninstall:

1. Move `OurNook.app` to the Trash (macOS) or delete the folder (Windows)
2. Optionally delete the data folder (see above) — only if you don't
   want to keep your companions

That's it. There's no system service, no daemon, no leftover files
in `/Library/Application Support/` (except the data folder if you
chose to keep it).
