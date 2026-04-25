# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe-cache reuse tests for the Combine tab."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ui.combine_tab import CombineTab


def _probe(path: Path) -> FileProbe:
    return FileProbe(
        path=path,
        video=VideoStream(codec="h264", width=1920, height=1080, pix_fmt="yuv420p", fps=30.0),
        audio=AudioStream(codec="aac", sample_rate=48000, channels=2),
        duration_sec=60.0,
        size_bytes=1,
        raw={},
    )


def test_reorder_reuses_cached_probes_and_new_files_probe_incrementally(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path_a = tmp_path / "alpha_20260417-204926.mkv"
    path_b = tmp_path / "beta_20260417-205026.mkv"
    path_c = tmp_path / "charlie_20260417-205126.mkv"

    probe_calls: list[Path] = []
    probes = {path: _probe(path) for path in (path_a, path_b, path_c)}

    def fake_probe(path: Path) -> FileProbe:
        probe_calls.append(path)
        return probes[path]

    tab = CombineTab(probe_file=fake_probe)
    qtbot.addWidget(tab)
    tab.show()

    tab._file_list.add_paths([path_a, path_b])  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: len(probe_calls) == 2)

    first_item = tab._file_list.item(0)  # type: ignore[attr-defined]
    assert first_item is not None
    first_item.setSelected(True)
    tab._file_list.move_down()  # type: ignore[attr-defined]

    qtbot.wait(100)
    assert probe_calls == [path_a, path_b]

    tab._file_list.add_paths([path_c])  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: len(probe_calls) == 3)
    assert probe_calls == [path_a, path_b, path_c]
