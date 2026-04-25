# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for MainWindow behaviors (§5.4, §6.1, §11.4)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMenu, QTabWidget
from pytestqt.qtbot import QtBot

from stormfuse.config import APP_NAME, ORG_NAME
from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.jobs.base import Job
from stormfuse.ui import settings as ui_settings
from stormfuse.ui.main_window import MainWindow
from stormfuse.ui.settings_dialog import SettingsValues


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


def test_help_menu_includes_send_logs_action(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.NVENC,
    )
    qtbot.addWidget(window)
    window.show()

    help_menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "Help" and isinstance(action.menu(), QMenu)
    )

    assert [action.text() for action in help_menu.actions()] == [
        "Check for Updates",
        "About",
        "Open Logs",
        "Send Logs to Jas",
        "Clear Log Files",
    ]


def test_file_menu_includes_settings_action(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.NVENC,
    )
    qtbot.addWidget(window)
    window.show()

    settings_menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "Settings" and isinstance(action.menu(), QMenu)
    )

    assert [action.text() for action in settings_menu.actions()] == ["Edit Settings..."]


def test_settings_values_persist_and_reconfigure_debug_logging(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved_debug: list[bool] = []
    saved_auto_updates: list[bool] = []
    saved_beta_updates: list[bool] = []
    configured: list[bool] = []

    def remember_config(enabled: bool) -> None:
        configured.append(enabled)

    monkeypatch.setattr(
        "stormfuse.ui.main_window.ui_settings.debug_ffmpeg_logging_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "stormfuse.ui.main_window.ui_settings.set_debug_ffmpeg_logging_enabled",
        saved_debug.append,
    )
    monkeypatch.setattr(
        "stormfuse.ui.main_window.ui_settings.set_auto_check_updates",
        saved_auto_updates.append,
    )
    monkeypatch.setattr(
        "stormfuse.ui.main_window.ui_settings.set_allow_prerelease_updates",
        saved_beta_updates.append,
    )
    monkeypatch.setattr(
        "stormfuse.ui.main_window.configure_debug_logging",
        remember_config,
    )

    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.NVENC,
    )
    qtbot.addWidget(window)
    window.show()

    window._apply_settings_values(  # type: ignore[attr-defined]
        SettingsValues(
            debug_ffmpeg_logging=True,
            auto_check_updates=False,
            allow_prerelease_updates=True,
        )
    )

    assert saved_debug == [True]
    assert saved_auto_updates == [False]
    assert saved_beta_updates == [True]
    assert configured == [True, True]


def test_view_menu_updates_checked_theme_action(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved_mode = {"value": "system"}
    applied_modes: list[str] = []

    monkeypatch.setattr(
        "stormfuse.ui.main_window.ui_settings.theme_mode",
        lambda: saved_mode["value"],
    )
    monkeypatch.setattr(
        "stormfuse.ui.main_window.ui_settings.set_theme_mode",
        lambda mode: saved_mode.__setitem__("value", mode),
    )
    monkeypatch.setattr(
        "stormfuse.ui.main_window.apply_application_theme",
        lambda _app, mode: applied_modes.append(mode) or "light",
    )
    monkeypatch.setattr("stormfuse.ui.main_window.apply_widget_theme", lambda _widget: "light")

    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.NVENC,
    )
    qtbot.addWidget(window)
    window.show()

    view_menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "View" and isinstance(action.menu(), QMenu)
    )

    actions = {action.text(): action for action in view_menu.actions()}
    assert actions["System Default"].isChecked()

    actions["Dark Mode"].trigger()

    assert saved_mode["value"] == "dark"
    assert applied_modes[-1] == "dark"
    assert actions["Dark Mode"].isChecked()
    assert not actions["System Default"].isChecked()


def test_main_window_restores_persisted_theme_mode(qtbot: QtBot, tmp_path: Path) -> None:
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings(ORG_NAME, APP_NAME).clear()
    ui_settings.set_theme_mode("dark")

    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.NVENC,
    )
    qtbot.addWidget(window)
    window.show()

    view_menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "View" and isinstance(action.menu(), QMenu)
    )

    checked_actions = [action.text() for action in view_menu.actions() if action.isChecked()]
    assert checked_actions == ["Dark Mode"]


def test_startup_update_check_uses_saved_preference(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    window = MainWindow(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        encoder=EncoderChoice.NVENC,
    )
    qtbot.addWidget(window)

    monkeypatch.setattr(
        "stormfuse.ui.main_window.ui_settings.auto_check_updates_enabled",
        lambda: True,
    )
    monkeypatch.setattr(window, "_start_update_check", lambda *, manual: calls.append(manual))

    window._maybe_check_for_updates_on_startup()  # type: ignore[attr-defined]

    assert calls == [False]
