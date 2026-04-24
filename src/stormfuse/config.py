# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "StormFuse"
APP_VERSION = "1.0.0"
ORG_NAME = "Winds of Storm"


def _log_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        return Path(local_app_data) / APP_NAME / "logs"
    # Dev fallback for non-Windows
    return Path.home() / ".local" / "share" / APP_NAME / "logs"


LOG_DIR: Path = _log_root()
MAX_LOG_FILES: int = 20
