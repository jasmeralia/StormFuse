# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for persisted last-used directories."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from stormfuse.ui import settings


def test_qsettings_round_trip(tmp_path) -> None:
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))

    settings.remember_dir(settings.KEY_COMBINE_ADD, str(tmp_path / "videos"))

    assert settings.last_dir(settings.KEY_COMBINE_ADD) == str(tmp_path / "videos")


def test_update_preferences_round_trip(tmp_path) -> None:
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))

    settings.set_auto_check_updates(False)
    settings.set_allow_prerelease_updates(True)

    assert not settings.auto_check_updates_enabled()
    assert settings.allow_prerelease_updates_enabled()


def test_theme_mode_round_trip(tmp_path) -> None:
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))

    settings.set_theme_mode("dark")

    assert settings.theme_mode() == "dark"


def test_debug_ffmpeg_logging_round_trip(tmp_path) -> None:
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))

    settings.set_debug_ffmpeg_logging_enabled(True)

    assert settings.debug_ffmpeg_logging_enabled()
