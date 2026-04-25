# SPDX-License-Identifier: GPL-3.0-or-later
"""MainWindow — the application's single top-level window (§6.1)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from stormfuse.core.update_checker import UpdateInfo, check_for_updates
from stormfuse.ffmpeg._subprocess import configure_debug_logging
from stormfuse.ffmpeg.encoders import EncoderChoice, detect_encoder
from stormfuse.jobs.base import Job, JobError, JobResult
from stormfuse.jobs.combine import CombineJob
from stormfuse.jobs.compress import CompressJob
from stormfuse.logging_setup import clear_log_files, get_human_handler
from stormfuse.ui import settings as ui_settings
from stormfuse.ui.about_dialog import AboutDialog
from stormfuse.ui.combine_tab import CombineTab
from stormfuse.ui.compress_tab import CompressTab
from stormfuse.ui.log_pane import LogPane
from stormfuse.ui.menu_actions import open_log_dir, show_log_submit_dialog
from stormfuse.ui.settings_dialog import SettingsDialog, SettingsValues
from stormfuse.ui.theme import (
    apply_application_theme,
    apply_widget_theme,
    normalize_theme_mode,
    show_information_message,
)
from stormfuse.ui.update_dialog import UpdateDialog

log = logging.getLogger("ui.main_window")


class _UpdateCheckWorker(QObject):
    finished = pyqtSignal(object)

    def __init__(
        self,
        check_for_updates_fn: Callable[[bool], UpdateInfo | None],
        include_prerelease: bool,
    ) -> None:
        super().__init__()
        self._check_for_updates_fn = check_for_updates_fn
        self._include_prerelease = include_prerelease

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._check_for_updates_fn(self._include_prerelease)
        except Exception:
            log.exception(
                "Unhandled update check failure",
                extra={"event": "update.check.error", "ctx": {"error": "unexpected"}},
            )
            result = None
        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(
        self,
        ffmpeg_exe: Path,
        ffprobe_exe: Path,
        encoder: EncoderChoice,
        parent: QWidget | None = None,
        *,
        detect_encoder_fn: Callable[[Path], EncoderChoice] | None = None,
        check_updates_on_startup: bool = False,
        check_for_updates_fn: Callable[[bool], UpdateInfo | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._ffmpeg_exe = ffmpeg_exe
        self._ffprobe_exe = ffprobe_exe
        self._encoder = encoder
        self._detect_encoder = detect_encoder_fn or detect_encoder
        self._check_for_updates_fn = check_for_updates_fn or check_for_updates
        self._current_job: Job | None = None
        self._current_thread: QThread | None = None
        self._job_started_at: float | None = None
        self._job_progress: float = 0.0
        self._update_check_thread: QThread | None = None
        self._update_check_worker: _UpdateCheckWorker | None = None
        self._manual_update_check = False
        self._theme_mode = ui_settings.theme_mode()
        self._theme_actions: dict[str, QAction] = {}
        self._theme_action_group: QActionGroup | None = None

        self.setWindowTitle("StormFuse")
        self.setMinimumSize(700, 500)
        configure_debug_logging(ui_settings.debug_ffmpeg_logging_enabled())

        self._build_tabs(encoder)

        # Log pane
        self._log_pane = LogPane()
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_pane)

        # Wire log handler → log pane
        h = get_human_handler()
        if h:
            h.subscribe(self._log_pane.line_received.emit)

        self._build_status_bar()

        self._runtime_timer = QTimer(self)
        self._runtime_timer.setInterval(1000)
        self._runtime_timer.timeout.connect(self._refresh_runtime_status)

        self._recheck_nvenc_action = QAction("Re-check NVENC", self)
        self._recheck_nvenc_action.triggered.connect(self._recheck_nvenc)
        self._status_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._status_bar.customContextMenuRequested.connect(self._show_status_menu)

        # Menu bar
        self._build_menu()

        # Signal wiring
        self._wire_tab_signals()
        self._apply_theme_mode(self._theme_mode, persist=False)

        if check_updates_on_startup:
            QTimer.singleShot(0, self._maybe_check_for_updates_on_startup)

    # ------------------------------------------------------------------ #
    # Menu
    # ------------------------------------------------------------------ #

    def _wire_tab_signals(self) -> None:
        self._combine_tab.run_requested.connect(self._on_combine_run)
        self._combine_tab.cancel_requested.connect(self._cancel_job)
        self._compress_tab.run_requested.connect(self._on_compress_run)
        self._compress_tab.cancel_requested.connect(self._cancel_job)

    def _build_tabs(self, encoder: EncoderChoice) -> None:
        self._tabs = QTabWidget()
        self._combine_tab = CombineTab()
        self._compress_tab = CompressTab()
        self._combine_tab.set_encoder(encoder)
        self._compress_tab.set_encoder(encoder)
        self._tabs.addTab(self._combine_tab, "Combine")
        self._tabs.addTab(self._compress_tab, "Compress")
        self.setCentralWidget(self._tabs)

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._encoder_badge = QLabel(self._encoder_text())
        self._job_status = QLabel("Idle")
        self._elapsed_label = QLabel("")
        self._eta_label = QLabel("")
        self._status_bar.addWidget(self._encoder_badge)
        self._status_bar.addPermanentWidget(self._job_status)
        self._status_bar.addPermanentWidget(self._elapsed_label)
        self._status_bar.addPermanentWidget(self._eta_label)
        self._set_runtime_labels_visible(False)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        assert bar is not None

        file_menu = bar.addMenu("File")
        assert file_menu is not None
        exit_action = file_menu.addAction("Exit")
        assert exit_action is not None
        exit_action.triggered.connect(self.close)

        settings_menu = bar.addMenu("Settings")
        assert settings_menu is not None
        settings_action = settings_menu.addAction("Edit Settings...")
        assert settings_action is not None
        settings_action.triggered.connect(self._show_settings)

        view_menu = bar.addMenu("View")
        assert view_menu is not None
        self._build_theme_menu(view_menu)

        help_menu = bar.addMenu("Help")
        assert help_menu is not None

        about_action = help_menu.addAction("About")
        assert about_action is not None
        about_action.triggered.connect(self._show_about)

        update_action = help_menu.addAction("Check for Updates")
        assert update_action is not None
        update_action.triggered.connect(lambda: self._start_update_check(manual=True))

        clear_logs_action = help_menu.addAction("Clear Log Files")
        assert clear_logs_action is not None
        clear_logs_action.triggered.connect(self._clear_logs)

        logs_action = help_menu.addAction("Open Logs")
        assert logs_action is not None
        logs_action.triggered.connect(open_log_dir)

        send_logs_action = help_menu.addAction("Send Logs to Jas")
        assert send_logs_action is not None
        send_logs_action.triggered.connect(
            lambda: show_log_submit_dialog(self, encoder=self._encoder)
        )

    def _build_theme_menu(self, view_menu: QMenu) -> None:
        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        self._theme_actions = {}
        for mode, label in (
            ("system", "System Default"),
            ("light", "Light Mode"),
            ("dark", "Dark Mode"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, mode=mode: self._change_theme_mode(mode)
            )
            action_group.addAction(action)
            view_menu.addAction(action)
            self._theme_actions[mode] = action
        self._theme_action_group = action_group
        self._sync_theme_menu()

    # ------------------------------------------------------------------ #
    # Job management
    # ------------------------------------------------------------------ #

    @pyqtSlot(list, Path, object)
    def _on_combine_run(self, inputs: list[Path], output: Path, encoder: EncoderChoice) -> None:
        job = CombineJob(self._ffmpeg_exe, self._ffprobe_exe, inputs, output, encoder)
        self._start_job(job, "Combine")

    @pyqtSlot(Path, Path, float, object, bool)
    def _on_compress_run(
        self,
        input_path: Path,
        output_path: Path,
        target_gb: float,
        encoder: EncoderChoice,
        two_pass: bool,
    ) -> None:
        job = CompressJob(
            self._ffmpeg_exe,
            self._ffprobe_exe,
            input_path,
            output_path,
            target_gb,
            encoder,
            two_pass,
        )
        self._start_job(job, "Compress")

    def _start_job(self, job: Job, label: str) -> None:
        if self._current_job is not None:
            return  # single-job model

        self._current_job = job
        thread = QThread(self)
        self._current_thread = thread
        job.moveToThread(thread)

        job.progress.connect(self._on_progress)
        job.done.connect(self._on_job_done)
        job.failed.connect(self._on_job_failed)
        job.finished.connect(self._on_job_finished)
        job.finished.connect(thread.quit)
        thread.started.connect(job.run)
        thread.finished.connect(self._on_thread_finished)

        self._combine_tab.set_running(True)
        self._compress_tab.set_running(True)
        self._job_started_at = time.monotonic()
        self._job_progress = 0.0
        self._job_status.setText(f"Running: {label}")
        self._set_runtime_labels_visible(True)
        self._refresh_runtime_status()
        self._runtime_timer.start()

        thread.start()

    @pyqtSlot()
    def _cancel_job(self) -> None:
        if self._current_job:
            self._current_job.cancel()
            self._job_status.setText("Cancelling…")
            self._runtime_timer.stop()
            self._set_runtime_labels_visible(False)

    @pyqtSlot(float, str)
    def _on_progress(self, pct: float, phase: str) -> None:
        self._job_progress = max(0.0, min(pct, 1.0))
        self._job_status.setText(f"Running: {phase}")
        self._refresh_runtime_status()
        tab_idx = self._tabs.currentIndex()
        if tab_idx == 0:
            self._combine_tab.on_progress(pct, phase)
        else:
            self._compress_tab.on_progress(pct, phase)

    @pyqtSlot(object)
    def _on_job_done(self, result: JobResult) -> None:
        self._job_status.setText("Idle")
        self._finish_job()
        tab_idx = self._tabs.currentIndex()
        if tab_idx == 0:
            self._combine_tab.on_job_done(result)
        else:
            self._compress_tab.on_job_done(result)

    @pyqtSlot(object)
    def _on_job_failed(self, error: JobError) -> None:
        self._job_status.setText("Idle")
        self._finish_job()
        tab_idx = self._tabs.currentIndex()
        if tab_idx == 0:
            self._combine_tab.on_job_failed(error)
        else:
            self._compress_tab.on_job_failed(error)

    @pyqtSlot()
    def _on_job_finished(self) -> None:
        if self._current_job is None or not self._current_job.is_cancelled:
            return

        self._job_status.setText("Idle")
        self._finish_job()
        tab_idx = self._tabs.currentIndex()
        if tab_idx == 0:
            self._combine_tab.on_job_cancelled()
        else:
            self._compress_tab.on_job_cancelled()

    def _finish_job(self) -> None:
        if self._current_thread:
            self._current_thread.quit()
        self._runtime_timer.stop()
        self._job_started_at = None
        self._job_progress = 0.0
        self._set_runtime_labels_visible(False)
        self._current_job = None
        self._combine_tab.set_running(False)
        self._compress_tab.set_running(False)

    @pyqtSlot()
    def _on_thread_finished(self) -> None:
        if self._current_thread:
            self._current_thread.deleteLater()
            self._current_thread = None

    # ------------------------------------------------------------------ #
    # Menu actions
    # ------------------------------------------------------------------ #

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return
        self._apply_settings_values(dialog.values())

    def _apply_settings_values(self, values: SettingsValues) -> None:
        ui_settings.set_debug_ffmpeg_logging_enabled(values.debug_ffmpeg_logging)
        ui_settings.set_auto_check_updates(values.auto_check_updates)
        ui_settings.set_allow_prerelease_updates(values.allow_prerelease_updates)
        configure_debug_logging(values.debug_ffmpeg_logging)

    def _clear_logs(self) -> None:
        counts = clear_log_files()
        show_information_message(
            self,
            "Logs cleared",
            f"Deleted {counts['deleted']} file(s), "
            f"truncated {counts['truncated']} active file(s), "
            f"failed on {counts['failed']} file(s).",
        )

    def _maybe_check_for_updates_on_startup(self) -> None:
        if ui_settings.auto_check_updates_enabled():
            self._start_update_check(manual=False)

    def _start_update_check(self, *, manual: bool) -> None:
        if self._update_check_thread is not None:
            return

        include_prerelease = ui_settings.allow_prerelease_updates_enabled()
        self._manual_update_check = manual

        thread = QThread(self)
        worker = _UpdateCheckWorker(self._check_for_updates_fn, include_prerelease)
        worker.moveToThread(thread)

        self._update_check_thread = thread
        self._update_check_worker = worker

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_update_check_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_update_check(thread, worker))
        thread.start()

    @pyqtSlot(object)
    def _on_update_check_finished(self, result: object) -> None:
        if result is None:
            if self._manual_update_check:
                show_information_message(
                    self,
                    "StormFuse Updates",
                    "No newer update is available.",
                )
            return

        assert isinstance(result, UpdateInfo)
        UpdateDialog(result, self).exec()

    def _cleanup_update_check(self, thread: QThread, worker: _UpdateCheckWorker) -> None:
        if self._update_check_thread is thread:
            self._update_check_thread = None
        if self._update_check_worker is worker:
            self._update_check_worker = None
        self._manual_update_check = False
        worker.deleteLater()
        thread.deleteLater()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @pyqtSlot(QPoint)
    def _show_status_menu(self, pos: QPoint) -> None:
        menu = self._build_status_menu()
        menu.exec(self._status_bar.mapToGlobal(pos))

    def _build_status_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self._recheck_nvenc_action)
        return menu

    def _change_theme_mode(self, mode: str) -> None:
        self._apply_theme_mode(mode, persist=True)

    def _apply_theme_mode(self, mode: str, *, persist: bool) -> None:
        self._theme_mode = normalize_theme_mode(mode)
        if persist:
            ui_settings.set_theme_mode(self._theme_mode)
            self._theme_mode = ui_settings.theme_mode()

        qapp = QApplication.instance()
        if isinstance(qapp, QApplication):
            apply_application_theme(qapp, self._theme_mode)
        apply_widget_theme(self)
        self._sync_theme_menu()

    def _sync_theme_menu(self) -> None:
        for mode, action in self._theme_actions.items():
            action.setChecked(mode == self._theme_mode)

    def _recheck_nvenc(self) -> None:
        self.set_encoder(self._detect_encoder(self._ffmpeg_exe))

    def _refresh_runtime_status(self) -> None:
        if self._job_started_at is None:
            return

        elapsed_sec = max(0, int(time.monotonic() - self._job_started_at))
        self._elapsed_label.setText(f"Elapsed: {self._format_duration(elapsed_sec)}")

        if self._job_progress <= 0.0:
            self._eta_label.setText("ETA: --:--")
            return

        remaining_sec = int(elapsed_sec * (1.0 - self._job_progress) / self._job_progress)
        self._eta_label.setText(f"ETA: {self._format_duration(remaining_sec)}")

    def _set_runtime_labels_visible(self, visible: bool) -> None:
        self._elapsed_label.setVisible(visible)
        self._eta_label.setVisible(visible)

    def _format_duration(self, total_sec: int) -> str:
        hours, remainder = divmod(total_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _encoder_text(self) -> str:
        if self._encoder == EncoderChoice.NVENC:
            return "NVENC"
        return "libx264"

    def current_encoder(self) -> EncoderChoice:
        """Return the app's current encoder state."""
        return self._encoder

    def set_encoder(self, encoder: EncoderChoice) -> None:
        self._encoder = encoder
        self._encoder_badge.setText(self._encoder_text())
        self._combine_tab.set_encoder(encoder)
        self._compress_tab.set_encoder(encoder)
