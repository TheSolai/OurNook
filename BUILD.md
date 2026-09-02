# Building OurNook

This document covers how to build, test, and sign distributable binaries
for **macOS** (.app / .dmg) and **Windows** (.exe in a .zip). For most
release work, the [GitHub Actions workflow](.github/workflows/release.yml)
will do all of this automatically when you push a `v*` tag.

## TL;DR — local builds

```bash
# macOS (arm64 — Apple Silicon)
~/.nook-venv/bin/pyinstaller OurNook.spec --noconfirm
hdiutil create -volname "OurNook" -srcfolder dist/release-staging \
  -ov -format UDZO dist/release/OurNook-macOS-arm64.dmg

# Windows (must run on Windows or in a Windows CI runner)
pyinstaller OurNook-windows.spec --noconfirm
7z a -tzip dist\OurNook-Windows-x64.zip dist\OurNook
```

Outputs:
- macOS: `dist/release/OurNook-macOS-arm64.dmg` (~20 MB)
- Windows: `dist/release/OurNook-Windows-x64.zip` (~40 MB)

---

## Prerequisites

### All platforms
- **Python 3.10+** (3.12 recommended)
- **Node 20+** with `pnpm` (for the React frontend)
- **PyInstaller 6.x** (`pip install pyinstaller`)

### macOS
- macOS 11+ (Big Sur) on the build machine
- Xcode command line tools (`xcode-select --install`) — needed for the .app bundle
- `hdiutil` (built-in) for creating .dmg files

### Windows
- Windows 10+ (the build target) or Windows Server 2019+
- For code signing: a code-signing certificate (.pfx) + optional Authenticode timestamp service
- For installer creation: NSIS or Inno Setup (optional, not in current spec)

---

## Build process

### Step 1 — Build the frontend

```bash
pnpm install --frozen-lockfile
pnpm build
```

This produces `dist/index.html` and `dist/assets/*` — the compiled React
app that gets bundled into the binary.

### Step 2 — Install Python dependencies

The app needs these at runtime (PyInstaller will bundle them):
```
fastapi
uvicorn
httpx
pydantic
aiosqlite
pywebview
```

The full list is in `requirements.txt`. To set up a clean build venv:
```bash
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows
pip install -U pip
pip install -r requirements.txt
pip install pyinstaller
```

### Step 3 — Run PyInstaller

```bash
# macOS (arm64)
pyinstaller OurNook.spec --noconfirm --clean

# macOS (Intel — only works on an Intel Mac, or via Rosetta cross-build)
pyinstaller OurNook.spec --noconfirm --clean  # on an Intel host

# Windows
pyinstaller OurNook-windows.spec --noconfirm --clean
```

Output:
- `dist/OurNook.app/` (macOS) — proper .app bundle with Info.plist
- `dist/OurNook/OurNook.exe` (Windows) — one-folder bundle, ~40 MB
- `dist/OurNook/_internal/` — Python runtime + deps

### Step 4 — Package for distribution

```bash
# macOS .dmg
mkdir -p dist/release-staging
cp -R dist/OurNook.app dist/release-staging/
ln -s /Applications dist/release-staging/Applications
hdiutil create -volname "OurNook v0.1.0" \
  -srcfolder dist/release-staging \
  -ov -format UDZO \
  dist/release/OurNook-v0.1.0-macOS-arm64.dmg

# Windows .zip (with maximum compression)
7z a -tzip -mx=9 dist\OurNook-v0.1.0-Windows-x64.zip dist\OurNook
```

The macOS .dmg includes a symlink to `/Applications` so users can drag
the .app to install it (the standard macOS UX). The Windows zip just
extracts and runs.

---

## Code signing & notarization

### macOS

Without code signing, macOS Gatekeeper will block the app with:
> "OurNook can't be opened because Apple cannot check it for malicious software."

**For local testing only** (no Developer ID required), users can right-click
the app → "Open" → confirm. This bypasses Gatekeeper once.

**For real distribution**, you need:
1. **Apple Developer ID** ($99/yr): https://developer.apple.com/programs/enroll/
2. **Developer ID Application certificate** in Keychain
3. **Notarization** with Apple's notary service (otherwise the app gets
   killed silently on first launch by users on macOS 10.15+)

Sign + notarize:
```bash
# Sign the .app with hardened runtime + timestamp
codesign --deep --force --verify --verbose \
  --options runtime --timestamp \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  dist/OurNook.app

# Create a zip for notarization (the notary needs a specific format)
ditto -c -k --keepParent dist/OurNook.app dist/OurNook-notarize.zip

# Submit to Apple
xcrun notarytool submit dist/OurNook-notarize.zip \
  --keychain-profile "OurNook-Notary" \
  --wait

# Staple the ticket
xcrun stapler staple dist/OurNook.app

# Now repackage the .dmg
hdiutil create -volname "OurNook v0.1.0" \
  -srcfolder dist/release-staging \
  -ov -format UDZO \
  dist/release/OurNook-v0.1.0-macOS-arm64.dmg
```

You'll need to set up a keychain profile for `notarytool`:
```bash
xcrun notarytool store-credentials "OurNook-Notary" \
  --apple-id "you@example.com" \
  --team-id "TEAMID" \
  --password "app-specific-password"
```

### Windows

Without code signing, Windows SmartScreen will warn:
> "Windows protected your PC — Microsoft Defender SmartScreen prevented an
> unrecognized app from starting."

**For local testing**, click "More info" → "Run anyway".

**For real distribution** (strongly recommended):
1. **Code signing certificate** (~$70-200/yr): from DigiCert, Sectigo, etc.
   - Save as a `.pfx` file with a known password
   - Add to GitHub repo secrets as `WINDOWS_CERT_BASE64` (base64-encoded PFX)
2. **Timestamps** prevent the signature from expiring when the cert does

Sign the .exe:
```powershell
# PowerShell — sign with timestamp
$cert = Get-PfxCertificate -FilePath "ournook.pfx" -Password (Read-Host -AsSecureString)
Set-AuthenticodeSignature -FilePath "dist\OurNook\OurNook.exe" `
  -Certificate $cert -TimestampServer "http://timestamp.digicert.com"
```

For the GitHub Actions workflow, store the cert as a base64-encoded secret:
```bash
# Locally
base64 -i ournook.pfx -o ournook.pfx.b64
# Add to GitHub: Settings → Secrets → WINDOWS_CERT_BASE64
```

---

## Distribution

### Gumroad

Gumroad accepts any digital file. Upload the signed .dmg and .zip directly
to your product. Set a price (or $0+ for free).

Steps:
1. Go to https://gumroad.com/dashboard
2. New product → Digital product
3. Upload `OurNook-v0.1.0-macOS-arm64.dmg` and `OurNook-v0.1.0-Windows-x64.zip`
4. Add a description (use the README content)
5. Add cover image (the brand SVG rendered to PNG works)
6. Set price (Monzo preferred — no PayPal/Stripe middlemen)

### itch.io

itch.io is for indie games and tools, accepts any file format.

Steps:
1. Go to https://itch.io/dashboard
2. Create new project → kind: "Tools"
3. Set pricing: "Pay what you want" minimum $5 (or your choice)
4. Upload → "This file will be available on:" → all platforms
5. Add a 16:9 cover image
6. Description = the README

### Pricing note

Per the user's preferences (no middlemen like PayPal/Stripe), Monzo
direct payments are preferred. Both Gumroad and itch.io support Monzo
via their respective payout systems (Gumroad through Stripe Connect,
itch.io through their payment processor). If you want pure Monzo, you
can also sell directly via your own website and email the download link.

---

## Testing the built app

Before uploading anywhere, test the .dmg on a clean machine:

1. **Test the .dmg mounts correctly** (double-click)
2. **Test the .app launches** (drag to /Applications, open, verify window appears)
3. **Test the setup wizard** (delete any pre-existing OurNook data first)
4. **Test creating a companion + chatting** (requires Ollama installed)
5. **Test importing/exporting a card**
6. **Test backup/restore**
7. **Test quitting** (Cmd+Q or close window — should be clean)
8. **Test crash recovery** (force-kill the app, relaunch, check crash.log)

Test the Windows .zip:
1. Extract to a folder
2. Run `OurNook.exe`
3. Same checks as above

If any of these fail, fix and rebuild.

---

## CI/CD

The workflow at `.github/workflows/release.yml` runs on:
- Every push to a `v*` tag (e.g. `git push origin v0.1.0`)
- Manual trigger via the Actions tab

It builds for three targets in parallel:
- macOS arm64 (Apple Silicon)
- macOS x64 (Intel)
- Windows x64

And uploads artifacts to the GitHub Release page. To trigger:
```bash
git tag v0.1.0
git push origin v0.1.0
```

Then check the Actions tab and the Releases page.

---

## Build matrix details

| Target         | Runner         | Spec               | Output                          |
|----------------|----------------|--------------------|---------------------------------|
| macOS arm64    | macos-14       | OurNook.spec       | OurNook-macOS-arm64.dmg        |
| macOS x64      | macos-13       | OurNook.spec       | OurNook-macOS-x64.dmg          |
| Windows x64    | windows-latest | OurNook-windows.spec | OurNook-Windows-x64.zip      |

Apple Silicon is the dominant Mac platform now (M1/M2/M3/M4). The Intel
build is for older Macs. Both share the same .spec — PyInstaller produces
the right architecture automatically based on the runner.

---

## Bundle size notes

The macOS .app is ~37 MB; the .dmg is ~20 MB. The Windows .exe folder is
~40-50 MB; the .zip is ~15-20 MB. The Python runtime is the bulk — there's
no way to shrink it much without breaking functionality.

If size becomes an issue, options:
- Use `nuitka` instead of PyInstaller (typically 20-30% smaller, but slower build)
- Use UPX compression (already enabled)
- Split the bundle (e.g. download Python on first launch — much smaller download but worse UX)

For now, ~20-40 MB is reasonable for a desktop app that bundles its own runtime.

---

## File locations after build

```
dist/
├── OurNook.app/              # macOS .app bundle (run by double-clicking)
│   ├── Contents/
│   │   ├── MacOS/OurNook     # the binary
│   │   ├── Resources/        # bundled assets + Python framework
│   │   ├── Frameworks/       # native frameworks (WebKit, AppKit, Python)
│   │   └── Info.plist
├── OurNook/                  # Windows one-folder bundle
│   ├── OurNook.exe           # the launcher
│   ├── _internal/            # Python + all deps
│   ├── data/                 # dist/ + src-ui-public/
│   └── ...
├── release/
│   ├── OurNook-macOS-arm64.dmg     # ← upload to Gumroad/itch.io
│   ├── OurNook-Windows-x64.zip    # ← upload to Gumroad/itch.io
│   └── OurNook-macOS-x64.dmg      # (Intel Macs, when built)
└── release-staging/          # temp dir for .dmg creation
```

---

## Troubleshooting

**"OurNook.app is damaged and can't be opened"**: Gatekeeper rejection.
The user needs to right-click → Open → confirm. Or: the app isn't signed.
For distribution, sign it (see above).

**Windows SmartScreen warning**: Same as above. Sign the .exe.

**The app launches but the window is blank**: The frontend didn't bundle
properly. Check `dist/OurNook.app/Contents/Resources/data/dist/index.html` exists.
If not, rebuild the frontend (`pnpm build`).

**"Ollama not found" warning inside the app**: The system Ollama isn't
installed or isn't running. The setup wizard in the app guides the user
through installation. This is expected on a fresh machine.

**The app crashes immediately on launch**: Check `~/Library/Logs/DiagnosticReports/`
(macOS) or `%LOCALAPPDATA%\OurNook\crash.log` (Windows). The crash guard
in `our_nook.py` writes a traceback to `crash.log` in the user's data dir.
