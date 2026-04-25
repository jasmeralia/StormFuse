# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for Combine file ordering rules (§5.1, §11.4)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ui.widgets.file_list import FileListWidget


def _probe(path: Path) -> FileProbe:
    return FileProbe(
        path=path,
        video=VideoStream(codec="h264", width=1920, height=1080, pix_fmt="yuv420p", fps=30.0),
        audio=AudioStream(codec="aac", sample_rate=48000, channels=2),
        duration_sec=60.0,
        size_bytes=1,
        raw={},
    )


def test_add_paths_sorts_by_filename_case_insensitively(qtbot: QtBot, tmp_path: Path) -> None:
    widget = FileListWidget()
    qtbot.addWidget(widget)

    paths = [
        tmp_path / "zeta.mkv",
        tmp_path / "Alpha.mkv",
        tmp_path / "beta.mkv",
        tmp_path / "Alpha.mkv",
    ]

    widget.add_paths(paths)

    assert [path.name for path in widget.all_paths()] == ["Alpha.mkv", "beta.mkv", "zeta.mkv"]


def test_sort_by_timestamp_preserves_unparseable_positions(qtbot: QtBot, tmp_path: Path) -> None:
    widget = FileListWidget()
    qtbot.addWidget(widget)

    paths = [
        tmp_path / "alpha-no-ts.mkv",
        tmp_path / "bravo_20260417-204926.mkv",
        tmp_path / "charlie-no-ts.mkv",
        tmp_path / "delta_20260416-204926.mkv",
    ]
    widget.add_paths(paths)

    widget.sort_by_timestamp()

    assert [path.name for path in widget.all_paths()] == [
        "alpha-no-ts.mkv",
        "delta_20260416-204926.mkv",
        "charlie-no-ts.mkv",
        "bravo_20260417-204926.mkv",
    ]
    first_item = widget.item(0)
    second_item = widget.item(1)
    third_item = widget.item(2)
    fourth_item = widget.item(3)

    assert first_item is not None
    assert second_item is not None
    assert third_item is not None
    assert fourth_item is not None
    assert first_item.text() == ""
    assert second_item.text() == ""
    assert third_item.text() == ""
    assert fourth_item.text() == ""

    first_row = widget.itemWidget(first_item)
    second_row = widget.itemWidget(second_item)
    third_row = widget.itemWidget(third_item)
    fourth_row = widget.itemWidget(fourth_item)

    assert first_row is not None
    assert second_row is not None
    assert third_row is not None
    assert fourth_row is not None
    assert first_row.findChild(QLabel, "basenameLabel").text() == "alpha-no-ts.mkv"  # type: ignore[union-attr]
    assert second_row.findChild(QLabel, "basenameLabel").text() == "delta_20260416-204926.mkv"  # type: ignore[union-attr]
    assert third_row.findChild(QLabel, "basenameLabel").text() == "charlie-no-ts.mkv"  # type: ignore[union-attr]
    assert fourth_row.findChild(QLabel, "basenameLabel").text() == "bravo_20260417-204926.mkv"  # type: ignore[union-attr]


def test_row_widget_shows_timestamp_and_probe_badges(qtbot: QtBot, tmp_path: Path) -> None:
    widget = FileListWidget()
    qtbot.addWidget(widget)

    path = tmp_path / "clip_20260417-204926.mkv"
    widget.add_paths([path])
    widget.set_probe_results({path: _probe(path)})

    item = widget.item(0)
    assert item is not None
    row_widget = widget.itemWidget(item)

    assert row_widget is not None
    timestamp_badge = row_widget.findChild(QLabel, "timestampBadge")
    probe_badge = row_widget.findChild(QLabel, "probeBadge")

    assert timestamp_badge is not None
    assert probe_badge is not None
    assert timestamp_badge.text() == "2026-04-17 20:49:26"
    assert probe_badge.text() == "1920x1080@30.00 h264/aac"


def test_row_widget_shows_warning_badge_when_timestamp_is_missing(
    qtbot: QtBot, tmp_path: Path
) -> None:
    widget = FileListWidget()
    qtbot.addWidget(widget)

    path = tmp_path / "untagged.mkv"
    widget.add_paths([path])

    item = widget.item(0)
    assert item is not None
    row_widget = widget.itemWidget(item)

    assert row_widget is not None
    warning_badge = row_widget.findChild(QLabel, "timestampWarning")
    assert warning_badge is not None
    assert warning_badge.text() == "⚠"
