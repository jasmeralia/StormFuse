# SPDX-License-Identifier: GPL-3.0-or-later
"""Rendering tests for the combine file list widget."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from stormfuse.ui.widgets.file_list import FileListWidget


def test_item_text_is_empty_when_row_widget_renders_filename(qtbot: QtBot, tmp_path: Path) -> None:
    widget = FileListWidget()
    qtbot.addWidget(widget)

    widget.add_paths([tmp_path / "alpha.mkv", tmp_path / "beta.mkv"])

    assert widget.item(0) is not None
    assert widget.item(1) is not None
    assert widget.item(0).text() == ""
    assert widget.item(1).text() == ""
