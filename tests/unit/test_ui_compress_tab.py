# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for Compress tab probe preflight (§5.2, §11.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QLabel, QSlider
from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.bitrate import compute_bitrate
from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ui import compress_tab as compress_tab_module
from stormfuse.ui.compress_tab import MIN_SOURCE_BYTES, CompressTab


def _probe(path: Path, *, duration_sec: float = 120.0) -> FileProbe:
    return FileProbe(
        path=path,
        video=VideoStream(codec="h264", width=1920, height=1080, pix_fmt="yuv420p", fps=30.0),
        audio=AudioStream(codec="aac", sample_rate=48000, channels=2),
        duration_sec=duration_sec,
        size_bytes=1,
        raw={},
    )


# Stub file size that is comfortably above the 9.5 GB rejection threshold so
# tests focused on slider / probe behavior don't trip the size guard.
def _large_file_size(_path: Path) -> int:
    return 12_000_000_000


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
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=95.0),
        file_size=_large_file_size,
    )
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

    tab = CompressTab(probe_file=fail_probe, file_size=_large_file_size)
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    qtbot.waitUntil(lambda: "broken.mp4" in tab._run_btn.toolTip())  # type: ignore[attr-defined]

    assert not tab._run_btn.isEnabled()  # type: ignore[attr-defined]


def test_compress_tab_shows_infeasible_target_tooltip(qtbot: QtBot, tmp_path: Path) -> None:
    path = tmp_path / "marathon.mkv"
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=500_000.0),
        file_size=_large_file_size,
    )
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
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=95.0),
        file_size=_large_file_size,
    )
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


def test_compress_tab_shows_source_size_when_input_loaded(qtbot: QtBot, tmp_path: Path) -> None:
    path = tmp_path / "huge.mkv"
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=600.0),
        file_size=lambda _p: 12_340_000_000,
    )
    qtbot.addWidget(tab)
    tab.show()

    assert tab._source_size_label.text() == ""  # type: ignore[attr-defined]

    tab._set_input_path(path)  # type: ignore[attr-defined]

    assert tab._source_size_label.text() == "Source size: 12.34 GB"  # type: ignore[attr-defined]
    assert tab._input_field.text() == str(path)  # type: ignore[attr-defined]


def test_compress_tab_rejects_file_already_under_threshold(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        compress_tab_module,
        "show_warning_message",
        lambda _self, title, message: warnings.append((title, message)) or 0,
    )

    path = tmp_path / "already_small.mp4"
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=600.0),
        file_size=lambda _p: MIN_SOURCE_BYTES - 1,
    )
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    assert len(warnings) == 1
    title, message = warnings[0]
    assert title == "File already under target"
    assert "9.5 GB" in message
    assert "already_small.mp4" in message
    assert tab._input_field.text() == ""  # type: ignore[attr-defined]
    assert tab._source_size_label.text() == ""  # type: ignore[attr-defined]
    assert not tab._run_btn.isEnabled()  # type: ignore[attr-defined]


def test_compress_tab_accepts_file_exactly_at_threshold(qtbot: QtBot, tmp_path: Path) -> None:
    path = tmp_path / "just_big_enough.mkv"
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=600.0),
        file_size=lambda _p: MIN_SOURCE_BYTES,
    )
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    assert tab._input_field.text() == str(path)  # type: ignore[attr-defined]
    assert "9.50 GB" in tab._source_size_label.text()  # type: ignore[attr-defined]


def test_compress_tab_surfaces_stat_error(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        compress_tab_module,
        "show_warning_message",
        lambda _self, title, message: warnings.append((title, message)) or 0,
    )

    def _stat_fails(_p: Path) -> int:
        raise PermissionError("permission denied")

    path = tmp_path / "unreadable.mkv"
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=600.0),
        file_size=_stat_fails,
    )
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    assert len(warnings) == 1
    title, message = warnings[0]
    assert title == "Cannot read file"
    assert "permission denied" in message
    assert tab._input_field.text() == ""  # type: ignore[attr-defined]


def test_compress_tab_caps_slider_max_below_source_size(qtbot: QtBot, tmp_path: Path) -> None:
    # Source is 9.7 GB; slider max should drop to 9.6 GB so the target stays
    # strictly below the source (any target >= source is a no-op).
    path = tmp_path / "just_over.mkv"
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=600.0),
        file_size=lambda _p: 9_700_000_000,
    )
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    assert tab._slider._slider.maximum() == 96  # type: ignore[attr-defined]
    assert tab._slider.gb_value() <= 9.6  # type: ignore[attr-defined]


def test_compress_tab_keeps_slider_max_at_10gb_for_large_source(
    qtbot: QtBot, tmp_path: Path
) -> None:
    # Source > 10 GB: the slider's existing 10.0 GB ceiling is already strictly
    # below source size, so it should not be lowered.
    path = tmp_path / "huge.mkv"
    tab = CompressTab(
        probe_file=lambda actual_path: _probe(actual_path, duration_sec=600.0),
        file_size=lambda _p: 25_000_000_000,
    )
    qtbot.addWidget(tab)
    tab.show()

    tab._set_input_path(path)  # type: ignore[attr-defined]

    assert tab._slider._slider.maximum() == 100  # type: ignore[attr-defined]


def test_size_slider_set_max_gb_clamps_value_and_label(qtbot: QtBot) -> None:
    from stormfuse.ui.widgets.size_slider import SizeSlider

    slider = SizeSlider()
    qtbot.addWidget(slider)

    slider.set_max_gb(7.5)
    assert slider._slider.maximum() == 75  # type: ignore[attr-defined]
    assert slider._max_label.text() == "7.5 GB"  # type: ignore[attr-defined]
    # Default value of 9.5 GB must be clamped down to the new ceiling.
    assert slider.gb_value() == 7.5

    # Restoring to 10.0 GB should not move the current value back up.
    slider.set_max_gb(10.0)
    assert slider._slider.maximum() == 100  # type: ignore[attr-defined]
    assert slider._max_label.text() == "10.0 GB"  # type: ignore[attr-defined]
    assert slider.gb_value() == 7.5
