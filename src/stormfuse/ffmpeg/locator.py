# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve ffmpeg/ffprobe binaries (§7.1).

Resolution order:
  Windows:
    1. PyInstaller bundle: sys._MEIPASS/resources/ffmpeg/{base}.exe
    2. Source tree:        <repo_root>/resources/ffmpeg/{base}.exe
    3. Raise FfmpegNotFoundError — no PATH fallback.
  Linux:
    1. PyInstaller bundle: sys._MEIPASS/resources/ffmpeg/{base}
    2. Source tree:        <repo_root>/resources/ffmpeg/{base}
    3. PATH via shutil.which({base})
    4. Raise FfmpegNotFoundError.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


class FfmpegNotFoundError(Exception):
    """Raised when ffmpeg/ffprobe cannot be located."""

    def __init__(self, binary: str) -> None:
        self.binary = binary
        if sys.platform == "linux":
            message = (
                f"Could not locate '{binary}'. "
                "Install ffmpeg (e.g. `sudo apt install ffmpeg`) and ensure it's on PATH."
            )
        else:
            message = (
                f"Could not locate bundled '{binary}'. "
                "The installation may be corrupted. "
                "Run 'make fetch-ffmpeg' to restore the bundled binaries."
            )
        super().__init__(message)


def _bundle_ffmpeg_dir() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    return Path(meipass) / "resources" / "ffmpeg"


def _source_ffmpeg_dir() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "resources" / "ffmpeg"
        if candidate.is_dir():
            return candidate
    return None


def _binary_name(base: str) -> str:
    if sys.platform == "win32":
        return f"{base}.exe"
    return base


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    bundle_dir = _bundle_ffmpeg_dir()
    if bundle_dir is not None:
        dirs.append(bundle_dir)
    source_dir = _source_ffmpeg_dir()
    if source_dir is not None:
        dirs.append(source_dir)
    return dirs


def _resolve_binary(base: str) -> Path:
    name = _binary_name(base)
    for directory in _candidate_dirs():
        candidate = directory / name
        if candidate.exists():
            return candidate

    if sys.platform == "linux":
        found = shutil.which(base)
        if found:
            return Path(found)

    raise FfmpegNotFoundError(name)


def ffmpeg_path() -> Path:
    return _resolve_binary("ffmpeg")


def ffprobe_path() -> Path:
    return _resolve_binary("ffprobe")


def icons_dir() -> Path:
    """Return the resources/icons directory from bundle or source tree."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "resources" / "icons"
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "resources" / "icons"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("resources/icons directory not found")
