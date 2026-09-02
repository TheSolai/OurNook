# -*- mode: python ; coding: utf-8 -*-
"""
OurNook — Windows PyInstaller spec.

This is the same as OurNook.spec but without the macOS .app bundle wrapper
(it produces a one-folder bundle at dist/OurNook/OurNook.exe).

Build with (on Windows, or in a Windows CI runner):
  pyinstaller OurNook-windows.spec

Output:
  dist/OurNook/OurNook.exe       (the launcher)
  dist/OurNook/_internal/        (Python + deps)
  dist/OurNook/data/dist/        (frontend)
  dist/OurNook/data/src-ui-public/  (icons)
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()
ENTRY = str(ROOT / "our_nook.py")

DATA = [
    (str(ROOT / "dist"), "dist"),
    (str(ROOT / "src-ui" / "public"), "src-ui-public"),
]

HIDDEN_IMPORTS = [
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
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
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
    "aiosqlite",
    "clr_loader",
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
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
    "gtk",
]

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
    strip=False,
    upx=True,
    console=False,  # windowed app
    disable_windowed_traceback=False,
    target_arch=None,
)

a.binaries = [b for b in a.binaries if b[0] not in EXCLUDES]

pyz = PYZ(a.pure, a.zipped_data)

EXE = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OurNook",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    # Icon — the .ico from the Tauri build
    icon=str(ROOT / "nook-tauri" / "icons" / "icon.ico") if (ROOT / "nook-tauri" / "icons" / "icon.ico").exists() else None,
)

coll = COLLECT(
    EXE,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="OurNook",
)
