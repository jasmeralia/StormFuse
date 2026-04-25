# SPDX-License-Identifier: GPL-3.0-or-later
"""QSettings helpers for small pieces of UI state."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from stormfuse.config import APP_NAME, ORG_NAME

KEY_COMBINE_ADD = "dirs/combine_add_files"
KEY_COMBINE_OUT = "dirs/combine_output"
KEY_COMPRESS_IN = "dirs/compress_input"
KEY_COMPRESS_OUT = "dirs/compress_output"


def last_dir(key: str) -> str:
    """Return the last remembered directory for *key*, or an empty string."""
    value = QSettings(ORG_NAME, APP_NAME).value(key, "")
    return "" if value is None else str(value)


def remember_dir(key: str, path: str) -> None:
    """Persist *path* for *key*."""
    QSettings(ORG_NAME, APP_NAME).setValue(key, path)
