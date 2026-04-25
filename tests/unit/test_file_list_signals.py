# SPDX-License-Identifier: GPL-3.0-or-later
"""Signal tests for the combine file list widget."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from stormfuse.ui.widgets.file_list import FileListWidget


def test_add_paths_emits_files_added_once(qtbot: QtBot, tmp_path: Path) -> None:
    widget = FileListWidget()
    qtbot.addWidget(widget)

    added_events: list[list[Path]] = []

    widget.files_added.connect(lambda paths: added_events.append(list(paths)))
    widget.files_changed.connect(lambda: added_events.append([]))

    widget.add_paths([tmp_path / "alpha.mkv"])

    assert added_events[0] == [tmp_path / "alpha.mkv"]
    assert added_events[1] == []


def test_reorder_and_remove_emit_files_changed_but_not_files_added(
    qtbot: QtBot, tmp_path: Path
) -> None:
    widget = FileListWidget()
    qtbot.addWidget(widget)

    path_a = tmp_path / "alpha.mkv"
    path_b = tmp_path / "beta.mkv"
    widget.add_paths([path_a, path_b])

    added_events: list[list[Path]] = []

    widget.files_added.connect(lambda paths: added_events.append(list(paths)))
    widget.files_changed.connect(lambda: added_events.append([]))

    second_item = widget.item(1)
    assert second_item is not None
    second_item.setSelected(True)
    widget.move_up()

    first_item = widget.item(0)
    assert first_item is not None
    first_item.setSelected(True)
    widget.move_down()

    moved_item = widget.item(1)
    assert moved_item is not None
    moved_item.setSelected(True)
    widget.remove_selected()

    assert [event for event in added_events if event] == []
    assert len([event for event in added_events if not event]) == 3
