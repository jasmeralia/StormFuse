# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for the Combine tab preview (§6.2, §11.4)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QToolButton
from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ui.combine_tab import CombineTab


def _probe(
    path: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: float = 30.0,
    video_codec: str = "h264",
    audio_codec: str = "aac",
) -> FileProbe:
    return FileProbe(
        path=path,
        video=VideoStream(
            codec=video_codec,
            width=width,
            height=height,
            pix_fmt="yuv420p",
            fps=fps,
        ),
        audio=AudioStream(codec=audio_codec, sample_rate=48000, channels=2),
        duration_sec=60.0,
        size_bytes=1,
        raw={},
    )


def test_combine_tab_shows_stream_copy_preview(qtbot: QtBot, tmp_path: Path) -> None:
    path_a = tmp_path / "a_20260417-204926.mkv"
    path_b = tmp_path / "b_20260417-205026.mkv"
    probes = {
        path_a: _probe(path_a),
        path_b: _probe(path_b),
    }

    tab = CombineTab(probe_file=lambda path: probes[path])
    qtbot.addWidget(tab)
    tab.show()

    tab._file_list.add_paths([path_b, path_a])  # type: ignore[attr-defined]

    strategy_label = tab.findChild(QLabel, "strategyLabel")
    why_label = tab.findChild(QLabel, "strategyWhy")

    assert strategy_label is not None
    assert why_label is not None
    qtbot.waitUntil(lambda: strategy_label.text() == "Will stream-copy concat")
    assert strategy_label.text() == "Will stream-copy concat"
    assert why_label.isHidden()


def test_combine_tab_shows_normalize_preview_and_mismatch_tooltip(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path_a = tmp_path / "a_20260417-204926.mkv"
    path_b = tmp_path / "b_20260417-205026.mkv"
    probes = {
        path_a: _probe(path_a, width=1920, height=1080),
        path_b: _probe(path_b, width=1280, height=720),
    }

    tab = CombineTab(probe_file=lambda path: probes[path])
    qtbot.addWidget(tab)
    tab.show()

    tab._file_list.add_paths([path_a, path_b])  # type: ignore[attr-defined]

    strategy_label = tab.findChild(QLabel, "strategyLabel")
    why_label = tab.findChild(QLabel, "strategyWhy")
    details_label = tab.findChild(QLabel, "strategyDetails")
    toggle = tab.findChild(QToolButton)

    assert strategy_label is not None
    assert why_label is not None
    assert details_label is not None
    assert toggle is not None

    qtbot.waitUntil(lambda: strategy_label.text() == "Will normalize 1 of 2 inputs")
    assert strategy_label.text() == "Will normalize 1 of 2 inputs"
    assert why_label.toolTip() == "b_20260417-205026.mkv: resolution: 1280x720 vs 1920x1080"

    toggle.click()

    assert details_label.isVisible()
    assert "Target normalize signature: 1920x1080@30.00 h264/aac" in details_label.text()
    assert "Copy path: a_20260417-204926.mkv" in details_label.text()
    assert "Normalize: b_20260417-205026.mkv" in details_label.text()


def test_combine_tab_splits_default_output_filename_and_folder(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path_a = tmp_path / "a_20260417-204926.mkv"
    path_b = tmp_path / "b_20260417-205026.mkv"
    probes = {
        path_a: _probe(path_a),
        path_b: _probe(path_b),
    }

    tab = CombineTab(probe_file=lambda path: probes[path])
    qtbot.addWidget(tab)
    tab.show()

    tab._file_list.add_paths([path_a, path_b])  # type: ignore[attr-defined]

    qtbot.waitUntil(lambda: tab._out_filename.text() == "a_20260417-204926-combined.mkv")  # type: ignore[attr-defined]

    assert tab._out_filename.text() == "a_20260417-204926-combined.mkv"  # type: ignore[attr-defined]
    assert tab._out_folder.text() == str(tmp_path)  # type: ignore[attr-defined]


def test_combine_tab_emits_output_path_from_folder_and_filename(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path_a = tmp_path / "a_20260417-204926.mkv"
    path_b = tmp_path / "b_20260417-205026.mkv"
    probes = {
        path_a: _probe(path_a),
        path_b: _probe(path_b),
    }

    tab = CombineTab(probe_file=lambda path: probes[path])
    qtbot.addWidget(tab)
    tab.show()

    received: list[tuple[list[Path], Path, object]] = []
    tab.run_requested.connect(
        lambda inputs, output, encoder: received.append((inputs, output, encoder))
    )

    tab._file_list.add_paths([path_a, path_b])  # type: ignore[attr-defined]
    qtbot.waitUntil(tab._run_btn.isEnabled)  # type: ignore[attr-defined]

    tab._out_filename.setText("joined.mkv")  # type: ignore[attr-defined]
    tab._out_folder.setText(str(tmp_path / "exports"))  # type: ignore[attr-defined]
    qtbot.mouseClick(tab._run_btn, Qt.MouseButton.LeftButton)  # type: ignore[attr-defined]

    assert received == [([path_a, path_b], tmp_path / "exports" / "joined.mkv", tab._encoder)]  # type: ignore[attr-defined]
