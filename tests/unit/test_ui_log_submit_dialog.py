# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for the log submission dialog."""

from __future__ import annotations

from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.encoders import EncoderChoice
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
