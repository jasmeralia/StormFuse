# SPDX-License-Identifier: GPL-3.0-or-later
"""QSettings helpers for small pieces of UI state."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from stormfuse.config import (
    ALLOW_PRERELEASE_UPDATES,
    APP_NAME,
    AUTO_CHECK_UPDATES,
    DEBUG_FFMPEG_LOGGING,
    ORG_NAME,
)

KEY_COMBINE_ADD = "dirs/combine_add_files"
KEY_COMBINE_OUT = "dirs/combine_output"
KEY_COMPRESS_IN = "dirs/compress_input"
KEY_COMPRESS_OUT = "dirs/compress_output"
KEY_THEME_MODE = "appearance/theme_mode"
KEY_DEBUG_FFMPEG_LOGGING = "diagnostics/debug_ffmpeg_logging"
KEY_UPDATE_AUTO_CHECK = "updates/auto_check"
KEY_UPDATE_ALLOW_PRERELEASE = "updates/allow_prerelease"


def last_dir(key: str) -> str:
    """Return the last remembered directory for *key*, or an empty string."""
    value = QSettings(ORG_NAME, APP_NAME).value(key, "")
    return "" if value is None else str(value)


def remember_dir(key: str, path: str) -> None:
    """Persist *path* for *key*."""
    QSettings(ORG_NAME, APP_NAME).setValue(key, path)


def bool_value(key: str, default: bool) -> bool:
    """Return a persisted bool, accepting both native bools and string values."""
    value = QSettings(ORG_NAME, APP_NAME).value(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def remember_bool(key: str, value: bool) -> None:
    """Persist *value* for *key*."""
    QSettings(ORG_NAME, APP_NAME).setValue(key, value)


def theme_mode() -> str:
    """Return the persisted theme mode."""
    value = QSettings(ORG_NAME, APP_NAME).value(KEY_THEME_MODE, "system")
    normalized = "" if value is None else str(value).strip().lower()
    if normalized in {"light", "dark"}:
        return normalized
    return "system"


def set_theme_mode(mode: str) -> None:
    """Persist the theme mode preference."""
    normalized = str(mode).strip().lower()
    if normalized not in {"system", "light", "dark"}:
        normalized = "system"
    QSettings(ORG_NAME, APP_NAME).setValue(KEY_THEME_MODE, normalized)


def debug_ffmpeg_logging_enabled() -> bool:
    """Return whether per-job ffmpeg debug reports are enabled."""
    return bool_value(KEY_DEBUG_FFMPEG_LOGGING, DEBUG_FFMPEG_LOGGING)


def set_debug_ffmpeg_logging_enabled(enabled: bool) -> None:
    """Persist the ffmpeg debug-report preference."""
    remember_bool(KEY_DEBUG_FFMPEG_LOGGING, enabled)


def auto_check_updates_enabled() -> bool:
    """Return whether StormFuse should check for updates at startup."""
    return bool_value(KEY_UPDATE_AUTO_CHECK, AUTO_CHECK_UPDATES)


def set_auto_check_updates(enabled: bool) -> None:
    """Persist the startup auto-update preference."""
    remember_bool(KEY_UPDATE_AUTO_CHECK, enabled)


def allow_prerelease_updates_enabled() -> bool:
    """Return whether prerelease updates are included during checks."""
    return bool_value(KEY_UPDATE_ALLOW_PRERELEASE, ALLOW_PRERELEASE_UPDATES)


def set_allow_prerelease_updates(enabled: bool) -> None:
    """Persist the prerelease update preference."""
    remember_bool(KEY_UPDATE_ALLOW_PRERELEASE, enabled)
