# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "StormFuse"
APP_VERSION = "1.0.13"
ORG_NAME = "Winds of Storm"
LOG_UPLOAD_ENDPOINT = "https://stormfuse.jasmer.tools/logs/upload"
LOG_UPLOAD_ENABLED = False
AUTO_CHECK_UPDATES = True
ALLOW_PRERELEASE_UPDATES = False
DEBUG_FFMPEG_LOGGING = False


def _log_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        return Path(local_app_data) / APP_NAME / "logs"
    # Dev fallback for non-Windows
    return Path.home() / ".local" / "share" / APP_NAME / "logs"


LOG_DIR: Path = _log_root()
MAX_LOG_FILES: int = 20


def ffmpeg_report_path(tool_name: str, job_id: str) -> Path:
    """Return the per-job FFREPORT path for *tool_name*."""
    return LOG_DIR / f"{tool_name}-{job_id}.log"
