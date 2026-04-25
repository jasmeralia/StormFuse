# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared subprocess helpers for ffmpeg/ffprobe invocations."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

type CompletedProcess = subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]
type PopenProcess = subprocess.Popen[str] | subprocess.Popen[bytes]

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run(argv: list[str], **kwargs: Any) -> CompletedProcess:
    """Run *argv* with StormFuse's standard Windows subprocess flags."""
    updated = _with_creationflags(kwargs)
    check = bool(updated.pop("check", False))
    return subprocess.run(argv, check=check, **updated)


def popen(argv: list[str], **kwargs: Any) -> PopenProcess:
    """Spawn *argv* with StormFuse's standard Windows subprocess flags."""
    return subprocess.Popen(argv, **_with_creationflags(kwargs))


def _with_creationflags(kwargs: dict[str, Any]) -> dict[str, Any]:
    updated = dict(kwargs)
    if sys.platform == "win32":
        current_flags = int(updated.get("creationflags", 0))
        updated["creationflags"] = current_flags | _CREATE_NO_WINDOW
    return updated
