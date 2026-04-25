# SPDX-License-Identifier: GPL-3.0-or-later
"""Menu action implementations requiring subprocess (§6.4).

This is the ONE module outside stormfuse.ffmpeg permitted to use subprocess
(for Explorer/file-manager launch only — see AGENTS.md §2 layering rules).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from stormfuse.config import LOG_DIR


def open_log_dir() -> None:
    """Open the log directory in the platform file manager (§6.4)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _open_folder(LOG_DIR)


def open_licenses_dir() -> None:
    """Open resources/licenses/ in the platform file manager."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "resources" / "licenses"
        if candidate.is_dir():
            _open_folder(candidate)
            return


def _open_folder(path: Path) -> None:
    if sys.platform == "win32":
        # Explorer launch is a deliberate user action, so this stays local instead of using the
        # ffmpeg-layer subprocess helper that suppresses console windows for background processes.
        subprocess.run(["explorer.exe", str(path)], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
