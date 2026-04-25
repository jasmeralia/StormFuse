# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared subprocess helpers for ffmpeg/ffprobe invocations."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from stormfuse.config import ffmpeg_report_path

type CompletedProcess = subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]
type PopenProcess = subprocess.Popen[str] | subprocess.Popen[bytes]

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_FFREPORT_LEVEL = 48
_DEBUG_FFMPEG_LOGGING = {"enabled": False}


def configure_debug_logging(enabled: bool) -> None:
    """Set whether ffmpeg/ffprobe subprocesses should receive FFREPORT."""
    _DEBUG_FFMPEG_LOGGING["enabled"] = enabled


def build_ffreport_value(report_path: str) -> str:
    """Build an FFREPORT value, escaping paths for ffmpeg's parser."""
    escaped_path = report_path.replace("'", "'\\''")
    return f"file='{escaped_path}':level={_FFREPORT_LEVEL}"


def run(argv: list[str], **kwargs: Any) -> CompletedProcess:
    """Run *argv* with StormFuse's standard Windows subprocess flags."""
    updated = _with_ffreport(argv, _with_creationflags(kwargs))
    check = bool(updated.pop("check", False))
    return subprocess.run(argv, check=check, **updated)


def popen(argv: list[str], **kwargs: Any) -> PopenProcess:
    """Spawn *argv* with StormFuse's standard Windows subprocess flags."""
    return subprocess.Popen(argv, **_with_ffreport(argv, _with_creationflags(kwargs)))


def _with_creationflags(kwargs: dict[str, Any]) -> dict[str, Any]:
    updated = dict(kwargs)
    if sys.platform == "win32":
        current_flags = int(updated.get("creationflags", 0))
        updated["creationflags"] = current_flags | _CREATE_NO_WINDOW
    return updated


def _with_ffreport(argv: list[str], kwargs: dict[str, Any]) -> dict[str, Any]:
    updated = dict(kwargs)
    job_id = updated.pop("job_id", None)
    if not _DEBUG_FFMPEG_LOGGING["enabled"] or not job_id:
        return updated

    tool_name = _tool_name(argv)
    if tool_name not in {"ffmpeg", "ffprobe"}:
        return updated

    report_path = ffmpeg_report_path(tool_name, str(job_id))
    report_path.parent.mkdir(parents=True, exist_ok=True)

    base_env = updated.get("env")
    env = dict(os.environ if base_env is None else base_env)
    env["FFREPORT"] = build_ffreport_value(str(report_path))
    updated["env"] = env
    return updated


def _tool_name(argv: list[str]) -> str:
    executable = argv[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = executable.rsplit(".", 1)[0]
    return stem.casefold()
