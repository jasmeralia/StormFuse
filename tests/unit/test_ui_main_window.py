# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for MainWindow behaviors (§5.4, §6.1, §11.4)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QTabWidget
from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.jobs.base import Job
from stormfuse.ui.main_window import MainWindow


class _WaitingJob(Job):
    def _run_job(self) -> None:
        while not self.is_cancelled:
            time.sleep(0.01)


def test_main_window_opens_with_both_tabs(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.NVENC,
    )
    qtbot.addWidget(window)
    window.show()

    tabs = window.findChild(QTabWidget)

    assert tabs is not None
    assert window.windowTitle() == "StormFuse"
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Combine", "Compress"]
    assert window._encoder_badge.text() == "NVENC"  # type: ignore[attr-defined]
    assert window._job_status.text() == "Idle"  # type: ignore[attr-defined]


def test_cancelled_job_resets_main_window_ui(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.LIBX264,
    )
    qtbot.addWidget(window)
    window.show()

    window._start_job(_WaitingJob(), "Combine")  # type: ignore[attr-defined]

    qtbot.waitUntil(window._combine_tab._cancel_btn.isEnabled)  # type: ignore[attr-defined]

    window._cancel_job()  # type: ignore[attr-defined]

    qtbot.waitUntil(lambda: window._current_job is None)  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: window._current_thread is None)  # type: ignore[attr-defined]

    assert window._job_status.text() == "Idle"  # type: ignore[attr-defined]
    assert window._combine_tab._phase_label.text() == "Cancelled"  # type: ignore[attr-defined]
    assert window._combine_tab._progress.value() == 0  # type: ignore[attr-defined]
    assert not window._combine_tab._cancel_btn.isEnabled()  # type: ignore[attr-defined]
    assert window._combine_tab._file_list.isEnabled()  # type: ignore[attr-defined]


def test_running_job_updates_status_bar_phase_and_runtime(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.LIBX264,
    )
    qtbot.addWidget(window)
    window.show()

    window._start_job(_WaitingJob(), "Combine")  # type: ignore[attr-defined]
    window._job_started_at = 100.0  # type: ignore[attr-defined]

    monkeypatch.setattr("stormfuse.ui.main_window.time.monotonic", lambda: 160.0)

    window._on_progress(0.25, "Encoding…")  # type: ignore[attr-defined]

    assert window._job_status.text() == "Running: Encoding…"  # type: ignore[attr-defined]
    assert window._elapsed_label.text() == "Elapsed: 01:00"  # type: ignore[attr-defined]
    assert window._eta_label.text() == "ETA: 03:00"  # type: ignore[attr-defined]
    assert window._elapsed_label.isVisible()  # type: ignore[attr-defined]
    assert window._eta_label.isVisible()  # type: ignore[attr-defined]

    window._cancel_job()  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: window._current_job is None)  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: window._current_thread is None)  # type: ignore[attr-defined]


def test_status_bar_menu_rechecks_nvenc_and_updates_badge(qtbot: QtBot, tmp_path: Path) -> None:
    detect_calls: list[Path] = []

    def fake_detect(ffmpeg_exe: Path) -> EncoderChoice:
        detect_calls.append(ffmpeg_exe)
        return EncoderChoice.NVENC

    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.LIBX264,
        detect_encoder_fn=fake_detect,
    )
    qtbot.addWidget(window)
    window.show()

    menu = window._build_status_menu()  # type: ignore[attr-defined]
    assert [action.text() for action in menu.actions()] == ["Re-check NVENC"]

    window._recheck_nvenc()  # type: ignore[attr-defined]

    assert detect_calls == [tmp_path / "ffmpeg.exe"]
    assert window._encoder_badge.text() == "NVENC"  # type: ignore[attr-defined]
    assert window._compress_tab._encoder_label.text() == "Encoder: NVENC (h264_nvenc)"  # type: ignore[attr-defined]
