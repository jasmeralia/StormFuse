# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for the log submission dialog."""

from __future__ import annotations

from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ui import log_submit_dialog as dialog_module
from stormfuse.ui.log_submit_dialog import LogSubmitDialog


def test_log_submit_dialog_updates_counter_and_lists_privacy_notice(qtbot: QtBot) -> None:
    dialog = LogSubmitDialog(encoder=EncoderChoice.NVENC)
    qtbot.addWidget(dialog)

    dialog._notes_edit.setPlainText("Need help")

    assert dialog._counter_label.text() == "9 characters"
    assert (
        "hostname" in dialog.findChild(type(dialog._status_label), "logSubmitPrivacyNotice").text()
    )
    assert (
        "encoder state"
        in dialog.findChild(type(dialog._status_label), "logSubmitPrivacyNotice").text().lower()
    )


def test_successful_upload_clears_log_files(qtbot: QtBot, monkeypatch) -> None:
    cleared = []
    monkeypatch.setattr(dialog_module, "clear_log_files", lambda: cleared.append(True))
    monkeypatch.setattr(dialog_module, "show_information_message", lambda *_a, **_kw: None)
    monkeypatch.setattr(dialog_module, "show_warning_message", lambda *_a, **_kw: None)

    dialog = LogSubmitDialog(encoder=EncoderChoice.NVENC)
    qtbot.addWidget(dialog)

    dialog._on_upload_finished(True, "Logs sent (ID: abc123)")

    assert cleared, "clear_log_files should be called after a successful upload"


def test_failed_upload_does_not_clear_log_files(qtbot: QtBot, monkeypatch) -> None:
    cleared = []
    monkeypatch.setattr(dialog_module, "clear_log_files", lambda: cleared.append(True))
    monkeypatch.setattr(dialog_module, "show_information_message", lambda *_a, **_kw: None)
    monkeypatch.setattr(dialog_module, "show_warning_message", lambda *_a, **_kw: None)

    dialog = LogSubmitDialog(encoder=EncoderChoice.NVENC)
    qtbot.addWidget(dialog)

    dialog._on_upload_finished(False, "Upload failed (HTTP 500).")

    assert not cleared, "clear_log_files should not be called after a failed upload"
