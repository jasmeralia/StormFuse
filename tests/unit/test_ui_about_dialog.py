# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for the About dialog attribution (§2.4, §11.4)."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot

from stormfuse.config import APP_VERSION
from stormfuse.ui.about_dialog import AboutDialog


def test_about_dialog_contains_required_attribution_strings(qtbot: QtBot) -> None:
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    label_text = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    button_text = {button.text() for button in dialog.findChildren(QPushButton)}

    assert dialog.windowTitle() == "About StormFuse"
    assert f"StormFuse v{APP_VERSION}" in label_text
    assert "\u00a9 2026 Morgan Blackthorne, Winds of Storm" in label_text
    assert "Licensed under GPL v3." in label_text
    assert "PyQt6 (GPL v3) \u2014 Riverbank Computing" in label_text
    assert "FFmpeg (GPL v2) \u2014 ffmpeg.org, build by gyan.dev" in label_text
    assert "Developed with assistance from Claude (Anthropic) and Codex (OpenAI)." in label_text
    assert {"View Licenses", "GitHub", "Close"} <= button_text
