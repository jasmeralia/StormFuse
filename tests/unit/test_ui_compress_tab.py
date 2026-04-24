# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for Compress tab probe preflight (§5.2, §11.4)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QLabel, QSlider
from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.bitrate import compute_bitrate
from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ui.compress_tab import CompressTab


def _probe(path: Path, *, duration_sec: float = 120.0) -> FileProbe:
    return FileProbe(
        path=path,
        video=VideoStream(codec="h264", width=1920, height=1080, pix_fmt="yuv420p", fps=30.0),
        audio=AudioStream(codec="aac", sample_rate=48000, channels=2),
        duration_sec=duration_sec,
        size_bytes=1,
        raw={},
    )


def test_compress_tab_slider_updates_bitrate_preview(qtbot: QtBot) -> None:
    tab = CompressTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.set_duration(120.0)

    preview = tab.findChild(QLabel, "bitratePreview")
    slider = tab.findChild(QSlider)

    assert preview is not None
    assert slider is not None

    default_preview = compute_bitrate(tab._slider.gb_value(), 120.0).video_bitrate_k  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: preview.text() == f"\u2248 {default_preview:,} kbps video")

    slider.setValue(80)

    updated_preview = compute_bitrate(tab._slider.gb_value(), 120.0).video_bitrate_k  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: preview.text() == f"\u2248 {updated_preview:,} kbps video")


def test_compress_tab_probes_input_off_thread_and_enables_run(qtbot: QtBot, tmp_path: Path) -> None:
    path = tmp_path / "clip_20260417-204926.mkv"
    tab = CompressTab(probe_file=lambda actual_path: _probe(actual_path, duration_sec=95.0))
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    qtbot.waitUntil(lambda: tab._duration_sec == 95.0)  # type: ignore[attr-defined]

    assert tab._input_field.text() == str(path)  # type: ignore[attr-defined]
    assert tab._out_filename.text() == "clip_20260417-204926-compressed.mp4"  # type: ignore[attr-defined]
    assert tab._out_folder.text() == str(path.parent)  # type: ignore[attr-defined]
    assert tab._run_btn.isEnabled()  # type: ignore[attr-defined]
    assert tab._run_btn.toolTip() == ""  # type: ignore[attr-defined]


def test_compress_tab_shows_probe_failure_tooltip(qtbot: QtBot, tmp_path: Path) -> None:
    path = tmp_path / "broken.mp4"

    def fail_probe(actual_path: Path) -> FileProbe:
        raise RuntimeError(actual_path.name)

    tab = CompressTab(probe_file=fail_probe)
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    qtbot.waitUntil(lambda: "broken.mp4" in tab._run_btn.toolTip())  # type: ignore[attr-defined]

    assert not tab._run_btn.isEnabled()  # type: ignore[attr-defined]


def test_compress_tab_shows_infeasible_target_tooltip(qtbot: QtBot, tmp_path: Path) -> None:
    path = tmp_path / "marathon.mkv"
    tab = CompressTab(probe_file=lambda actual_path: _probe(actual_path, duration_sec=500_000.0))
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    qtbot.waitUntil(lambda: tab._duration_sec == 500_000.0)  # type: ignore[attr-defined]

    tooltip = tab._run_btn.toolTip()  # type: ignore[attr-defined]
    assert not tab._run_btn.isEnabled()  # type: ignore[attr-defined]
    assert "too small" in tooltip.lower()
    assert "192 kbps" in tooltip
    assert "increase the target size" in tooltip.lower()


def test_compress_tab_emits_output_path_from_folder_and_filename(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "clip.mkv"
    tab = CompressTab(probe_file=lambda actual_path: _probe(actual_path, duration_sec=95.0))
    qtbot.addWidget(tab)
    tab.show()

    received: list[tuple[Path, Path, float, object, bool]] = []
    tab.run_requested.connect(
        lambda input_path, output_path, target_gb, encoder, two_pass: received.append(
            (input_path, output_path, target_gb, encoder, two_pass)
        )
    )

    tab._set_input_path(path)  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: tab._duration_sec == 95.0)  # type: ignore[attr-defined]

    tab._out_filename.setText("custom-output.mp4")  # type: ignore[attr-defined]
    tab._out_folder.setText(str(tmp_path / "exports"))  # type: ignore[attr-defined]
    tab._run_btn.click()  # type: ignore[attr-defined]

    assert received
    input_path, output_path, target_gb, encoder, two_pass = received[0]
    assert input_path == path
    assert output_path == tmp_path / "exports" / "custom-output.mp4"
    assert target_gb == tab._slider.gb_value()  # type: ignore[attr-defined]
    assert encoder == tab._encoder  # type: ignore[attr-defined]
    assert two_pass is False
