# OurNook Promo Kit v0.5.2

Everything you need to launch OurNook publicly. Hand it to a designer, a marketer, or a Product Hunt hunter and they can ship.

## Folder layout

```
promo/
├── README.md                      # this file
├── landing.html                   # self-contained HTML landing page (open in browser)
├── hero/                          # 3 hero images
│   ├── hero-noon.png              # 16:9 — cozy reading nook with lamp
│   ├── hero-ai-companion.png      # 16:9 — translucent AI across from person in cafe
│   └── hero-character.png         # 1:1 — character portrait
├── features/                      # 6 feature icons (1:1 each)
│   ├── feature-memory.png
│   ├── feature-soul.png
│   ├── feature-local.png
│   ├── feature-imagery.png
│   ├── feature-privacy.png
│   └── feature-cozy.png
├── docs/                          # all the copy
│   ├── producthunt.md             # PH headline + tagline + body + maker's note
│   ├── twitter-thread.md          # 9-tweet launch thread
│   ├── listing-itch-gumroad.md    # long-form marketplace listing
│   └── press-release.md           # ~400-word press release + boilerplate
└── ../dist/release/               # build artifacts (linked into the kit)
    ├── OurNook-0.5.2-macOS-arm64.dmg          (local Mac build, 283 MB)
    ├── gh-artifacts/OurNook-macOS-arm64/      (GH Mac arm64 DMG, 282 MB)
    ├── gh-artifacts/OurNook-Windows-x64/      (GH Windows zip, 205 MB)
    └── gh-artifacts/OurNook-macOS-x64/        (GH Mac x64 DMG, when ready)
```

## How to use this

**For Product Hunt launch:**
1. Open `docs/producthunt.md`
2. Upload `hero/hero-noon.png` as the gallery image
3. Upload 3-4 `features/feature-*.png` as gallery extras
4. Paste the headline / tagline / body / maker's note

**For Twitter / X launch:**
1. Open `docs/twitter-thread.md`
2. Post tweets 1-9 in order, ~3-5 min apart
3. Pin tweet 1 to your profile
4. Attach `hero/hero-noon.png` to tweet 1

**For itch.io / Gumroad:**
1. Open `docs/listing-itch-gumroad.md`
2. Upload `hero/hero-noon.png` as the cover
3. Use the "Long description" verbatim
4. Attach the build artifacts as downloads

**For a personal website / landing page:**
1. Open `landing.html` in a browser to preview
2. It's self-contained — upload the whole `promo/` folder to any static host
3. Update the GitHub release URL once Mac x64 is done

**For press / journalists:**
1. Send `docs/press-release.md` as the body
2. Attach `hero/hero-noon.png` and `hero-character.png`
3. Direct them to the GitHub repo for the source

## Brand notes

- **Palette:** warm charcoal `#1a1614` + dusty rose `#d4a59a` + sage `#9eb29b` + soft cream
- **Tone:** cozy, no-nonsense, "a place you build", slightly literary
- **Tagline:** "A cozy corner you build and nobody can take away."
- **Logo:** ◉ (small concentric circle in a rounded square)
- **Avoid:** corporate AI clichés ("transform your workflow", "unleash the power"), hyperbole, screenshots of stock-photo avatars

## Status of build artifacts

| Platform | Status | Size | Location |
|---|---|---|---|
| macOS Apple Silicon | ✅ done | 283 MB | `dist/release/OurNook-0.5.2-macOS-arm64.dmg` |
| macOS Intel | ⏳ queued on GH | — | `dist/release/gh-artifacts/OurNook-macOS-x64/` (when ready) |
| Windows x64 | ✅ done | 205 MB | `dist/release/gh-artifacts/OurNook-Windows-x64/OurNook-main-Windows-x64.zip` |

The local Mac DMG and the GH Mac arm64 DMG are byte-for-byte equivalent in functionality. Use whichever.

Once the Mac x64 build finishes, copy the artifact to `dist/release/` and update the table.
