# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for the update dialog."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot

from stormfuse.core.update_checker import UpdateInfo
from stormfuse.ui.update_dialog import UpdateDialog


def _update_info(*, is_prerelease: bool = False) -> UpdateInfo:
    return UpdateInfo(
        current_version="1.0.5",
        latest_version="1.0.6-beta.1" if is_prerelease else "1.0.6",
        release_name="StormFuse v1.0.6-beta.1" if is_prerelease else "StormFuse v1.0.6",
        release_notes="Line one\nLine two",
        download_url="https://example.invalid/StormFuse-Setup-1.0.6.exe",
        download_size=2_000_000,
        browser_url="https://github.com/jasmeralia/StormFuse/releases/tag/v1.0.6",
        is_prerelease=is_prerelease,
    )


def test_update_dialog_shows_release_details(qtbot: QtBot) -> None:
    dialog = UpdateDialog(_update_info(is_prerelease=True))
    qtbot.addWidget(dialog)
    dialog.show()

    labels = {label.objectName(): label.text() for label in dialog.findChildren(QLabel)}
    button_text = {button.text() for button in dialog.findChildren(QPushButton)}

    assert dialog.windowTitle() == "StormFuse Update Available"
    assert labels["updateCurrentVersionLabel"] == "1.0.5"
    assert labels["updateAvailableVersionLabel"] == "1.0.6-beta.1"
    assert labels["updateChannelLabel"] == "Beta / prerelease"
    assert "Download and Install" in button_text
    assert dialog._release_notes.toPlainText() == "Line one\nLine two"  # type: ignore[attr-defined]


def test_update_dialog_accepts_when_installer_launches(qtbot: QtBot, tmp_path: Path) -> None:
    launched: list[Path] = []
    exit_calls: list[bool] = []
    dialog = UpdateDialog(
        _update_info(),
        launch_installer_fn=lambda path: launched.append(path) or True,
        exit_after_launch_fn=lambda: exit_calls.append(True),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    installer_path = tmp_path / "StormFuse-Setup-1.0.6.exe"
    installer_path.write_bytes(b"MZ" + b"\0" * 32)

    dialog._on_download_finished(True, installer_path, "")  # type: ignore[attr-defined]

    assert launched == [installer_path]
    assert exit_calls == [True]
    assert dialog.result() == dialog.DialogCode.Accepted
