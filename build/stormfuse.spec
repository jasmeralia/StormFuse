# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for StormFuse (§12.2)

import sys
from pathlib import Path

REPO_ROOT = Path(SPEC).parent.parent  # type: ignore[name-defined]

# Single source of truth: src/stormfuse/config.py:APP_VERSION
# Read the version and write build/version.nsh so the NSIS installer
# never needs a hardcoded version string.
sys.path.insert(0, str(REPO_ROOT / "src"))
from stormfuse.config import APP_VERSION  # noqa: E402

(REPO_ROOT / "build" / "version.nsh").write_text(
    f'!define APP_VERSION "{APP_VERSION}"\n',
    encoding="utf-8",
)

a = Analysis(
    [str(REPO_ROOT / "src" / "stormfuse" / "__main__.py")],
    pathex=[str(REPO_ROOT / "src")],
    binaries=[
        (str(REPO_ROOT / "resources" / "ffmpeg" / "ffmpeg.exe"), "resources/ffmpeg"),
        (str(REPO_ROOT / "resources" / "ffmpeg" / "ffprobe.exe"), "resources/ffmpeg"),
    ],
    datas=[
        (str(REPO_ROOT / "resources" / "licenses"), "resources/licenses"),
        (str(REPO_ROOT / "resources" / "icons"), "resources/icons"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)  # type: ignore[name-defined]

exe = EXE(  # type: ignore[name-defined]
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StormFuse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(REPO_ROOT / "resources" / "icons" / "stormfuse.ico"),
)

coll = COLLECT(  # type: ignore[name-defined]
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="StormFuse",
)
