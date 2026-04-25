# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for persisted last-used directories."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from stormfuse.ui import settings


def test_qsettings_round_trip(tmp_path) -> None:
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))

    settings.remember_dir(settings.KEY_COMBINE_ADD, str(tmp_path / "videos"))

    assert settings.last_dir(settings.KEY_COMBINE_ADD) == str(tmp_path / "videos")
