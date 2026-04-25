# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for the Settings dialog."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QCheckBox
from pytestqt.qtbot import QtBot

from stormfuse.ui import settings_dialog
from stormfuse.ui.settings_dialog import SettingsDialog


def test_settings_dialog_loads_and_returns_update_and_diagnostic_values(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings_dialog.ui_settings, "debug_ffmpeg_logging_enabled", lambda: True)
    monkeypatch.setattr(settings_dialog.ui_settings, "auto_check_updates_enabled", lambda: False)
    monkeypatch.setattr(
        settings_dialog.ui_settings, "allow_prerelease_updates_enabled", lambda: True
    )

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    debug = dialog.findChild(QCheckBox, "settingsDebugFfmpegLogs")
    auto_updates = dialog.findChild(QCheckBox, "settingsAutoCheckUpdates")
    beta_updates = dialog.findChild(QCheckBox, "settingsAllowPrereleaseUpdates")

    assert debug is not None
    assert auto_updates is not None
    assert beta_updates is not None
    assert debug.isChecked()
    assert not auto_updates.isChecked()
    assert beta_updates.isChecked()

    debug.setChecked(False)
    auto_updates.setChecked(True)

    values = dialog.values()

    assert not values.debug_ffmpeg_logging
    assert values.auto_check_updates
    assert values.allow_prerelease_updates
