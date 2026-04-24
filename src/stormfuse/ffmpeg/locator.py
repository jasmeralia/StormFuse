# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve bundled ffmpeg/ffprobe binaries (§7.1).

Resolution order:
  1. PyInstaller bundle: sys._MEIPASS/resources/ffmpeg/
  2. Source tree:        <repo_root>/resources/ffmpeg/
  3. Raise FfmpegNotFoundError — no PATH fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path


class FfmpegNotFoundError(Exception):
    """Raised when the bundled ffmpeg/ffprobe cannot be located."""

    def __init__(self, binary: str) -> None:
        self.binary = binary
        super().__init__(
            f"Could not locate bundled '{binary}'. "
            "The installation may be corrupted. "
            "Run 'make fetch-ffmpeg' to restore the bundled binaries."
        )


def _ffmpeg_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "resources" / "ffmpeg"
    # Source tree: walk up from this file until we find the repo root
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "resources" / "ffmpeg"
        if candidate.is_dir():
            return candidate
    raise FfmpegNotFoundError("resources/ffmpeg directory")


def _resolve_binary(name: str) -> Path:
    d = _ffmpeg_dir()
    p = d / name
    if not p.exists():
        raise FfmpegNotFoundError(name)
    return p


def ffmpeg_path() -> Path:
    return _resolve_binary("ffmpeg.exe")


def ffprobe_path() -> Path:
    return _resolve_binary("ffprobe.exe")


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
