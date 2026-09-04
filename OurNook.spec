# -*- mode: python ; coding: utf-8 -*-
"""
OurNook — PyInstaller spec.

Builds a standalone executable (or .app on macOS) that bundles:
  - The Python runtime + all our deps (FastAPI, uvicorn, httpx, pydantic, aiosqlite, pywebview)
  - The compiled React frontend (dist/)
  - The static assets (src-ui/public/icons/)

The data dir layout inside the bundle uses a renamed `src-ui-public/` to avoid
collisions with the real `src-ui/` source dir at the project root.

Build with:
  pyinstaller OurNook.spec

Output:
  macOS:   dist/OurNook.app
  Windows: dist/OurNook/OurNook.exe  (one-folder mode)
  Linux:   dist/OurNook/OurNook      (one-folder mode)
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# Project root
ROOT = Path(SPECPATH).resolve()

# Are we building on Windows?
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# The main script
ENTRY = str(ROOT / "our_nook.py")

# Data files to bundle. Each entry: (source_path, dest_in_bundle)
# The dest name is what the bundle_path() / PUBLIC_DIR helper looks for.
DATA = [
    # The compiled React app (index.html + assets/*)
    (str(ROOT / "dist"), "dist"),
    # The icon assets — renamed in the bundle to avoid colliding with src-ui/
    (str(ROOT / "src-ui" / "public"), "src-ui-public"),
]

# Hidden imports — modules that PyInstaller's static analysis doesn't find
# but we use at runtime.
HIDDEN_IMPORTS = [
    # uvicorn internals
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # pywebview uses platform-specific backends
    "webview.platforms.winforms",
    "webview.platforms.cocoa",
    "webview.platforms.gtk",
    "webview.platforms.qt",
    # our own modules (defensive — should be picked up automatically)
    "api",
    "api.server",
    "api.db",
    "api.ollama",
    "api.cards",
    "api.system",
    "api.enneagram",
    "api.enneagram_soul",
    "api.enneagram_quiz",
    "api.memory_categories",
    # aiosqlite is a common miss
    "aiosqlite",
    # Real diffusion (v0.15.2) — diffusers/transformers/torch are huge trees
    # with many dynamic imports. PyInstaller's static analysis misses most of
    # them, so we list the public submodules that get touched at runtime.
    "diffusers",
    "diffusers.pipelines",
    "diffusers.pipelines.stable_diffusion_xl",
    "diffusers.pipelines.stable_diffusion",
    "diffusers.schedulers",
    "diffusers.models",
    "diffusers.models.autoencoders",
    "diffusers.models.unets",
    "transformers",
    "transformers.models.clip",
    "transformers.models.llama",
    "accelerate",
    "safetensors",
    "safetensors.torch",
    "torch",
    "torchvision",
] + collect_submodules("uvicorn") + collect_submodules("diffusers.pipelines.stable_diffusion_xl") + collect_submodules("diffusers.pipelines.stable_diffusion")

# Excluded modules — stuff we know we don't need that would bloat the bundle.
# NOTE: do NOT exclude numpy / PIL — diffusers+transformers need them at
# runtime. matplotlib stays excluded (we don't use it).
EXCLUDES = [
    "tkinter",
    "test",
    "unittest",
    "pytest",
    "matplotlib",
    "PIL.ImageQt",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
    "gtk",
]

# Build the Analysis
a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATA,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    # Strip symbols for smaller bundle
    strip=False,
    upx=True,
    upx_exclude=[],
    # Console output? Windowed app — no console
    console=False,
    # Disable the bootloader checksum verification (faster startup)
    disable_windowed_traceback=False,
    target_arch=None,  # use host arch
    codesign_identity=None,
    entitlements_file=None,
)

# Remove duplicate / unused binaries
a.binaries = [b for b in a.binaries if b[0] not in EXCLUDES]

# Bundle-level exclusions
pyz = PYZ(a.pure, a.zipped_data)

# Decide one-folder vs one-file based on platform
# macOS: .app bundle is folder-style, prefer one-folder inside the .app
# Windows: one-folder is faster to launch and easier to debug
EXE = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # libs go in the COLLECT step
    name="OurNook",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    # Windowed app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icon — the .icns at the project root
    icon=str(ROOT / "icons" / "icon.icns") if IS_MACOS and (ROOT / "icons" / "icon.icns").exists() else None,
)


# Collect the bundle (one-folder mode)
coll = COLLECT(
    EXE,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OurNook",
)

# On macOS, wrap the EXE in a proper .app bundle so it shows up in Finder
# with a Dock icon, and the window has the right activation behavior.
if IS_MACOS:
    app = BUNDLE(
        coll,
        name="OurNook.app",
        icon=str(ROOT / "icons" / "icon.icns") if (ROOT / "icons" / "icon.icns").exists() else None,
        bundle_identifier="ai.ournook.desktop",
        info_plist={
            "CFBundleName": "OurNook",
            "CFBundleDisplayName": "OurNook",
            "CFBundleShortVersionString": "0.5.2",
            "CFBundleVersion": "0.5.2",
            "NSHumanReadableCopyright": "Copyright © 2026 The Sol AI",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # allow dark mode
            "CFBundleDocumentTypes": [],
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )
