# SPDX-License-Identifier: GPL-3.0-or-later
"""Modal dialog for application updates."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stormfuse.core.update_checker import UpdateInfo, download_installer
from stormfuse.ui.theme import apply_widget_theme, show_warning_message

log = logging.getLogger("stormfuse.ui.update_dialog")


class _InstallerDownloadWorker(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(bool, object, str)

    def __init__(
        self,
        update_info: UpdateInfo,
        download_dir: Path,
        download_fn: Callable[[UpdateInfo, Path, Callable[[int, int], None]], Path],
    ) -> None:
        super().__init__()
        self._update_info = update_info
        self._download_dir = download_dir
        self._download_fn = download_fn

    @pyqtSlot()
    def run(self) -> None:
        try:
            path = self._download_fn(
                self._update_info,
                self._download_dir,
                self.progress.emit,
            )
        except (OSError, ValueError, TimeoutError) as exc:
            self.finished.emit(False, None, str(exc))
            return
        self.finished.emit(True, path, "")


class UpdateDialog(QDialog):
    """Show available update details and download the installer on demand."""

    def __init__(
        self,
        update_info: UpdateInfo,
        parent: QWidget | None = None,
        *,
        download_dir: Path | None = None,
        download_installer_fn: Callable[[UpdateInfo, Path, Callable[[int, int], None]], Path]
        | None = None,
        launch_installer_fn: Callable[[Path], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._update_info = update_info
        self._download_dir = download_dir or (Path.home() / "Downloads")
        self._download_installer_fn = download_installer_fn or download_installer
        self._launch_installer_fn = launch_installer_fn or _launch_installer
        self._download_thread: QThread | None = None
        self._download_worker: _InstallerDownloadWorker | None = None
        self._progress_dialog: QProgressDialog | None = None

        self.setWindowTitle("StormFuse Update Available")
        self.setModal(True)
        self.resize(680, 500)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "A newer StormFuse installer is available. Download it, then StormFuse will exit so "
            "the installer can replace the current build cleanly.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        details = QFormLayout()

        self._current_version_label = QLabel(update_info.current_version, self)
        self._current_version_label.setObjectName("updateCurrentVersionLabel")
        details.addRow("Current version:", self._current_version_label)

        self._available_version_label = QLabel(update_info.latest_version, self)
        self._available_version_label.setObjectName("updateAvailableVersionLabel")
        details.addRow("Available version:", self._available_version_label)

        self._channel_label = QLabel(
            "Beta / prerelease" if update_info.is_prerelease else "Stable release",
            self,
        )
        self._channel_label.setObjectName("updateChannelLabel")
        details.addRow("Channel:", self._channel_label)

        self._release_name_label = QLabel(update_info.release_name, self)
        self._release_name_label.setObjectName("updateReleaseNameLabel")
        self._release_name_label.setWordWrap(True)
        details.addRow("Release:", self._release_name_label)

        layout.addLayout(details)

        notes_label = QLabel("Release notes:", self)
        layout.addWidget(notes_label)

        self._release_notes = QPlainTextEdit(self)
        self._release_notes.setObjectName("updateReleaseNotes")
        self._release_notes.setReadOnly(True)
        self._release_notes.setPlainText(
            update_info.release_notes or "No release notes were provided."
        )
        layout.addWidget(self._release_notes, stretch=1)

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self._download_button = QPushButton("Download and Install", self)
        self._download_button.setObjectName("updateDownloadButton")
        self._download_button.clicked.connect(self._start_download)
        self._button_box.addButton(self._download_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)
        apply_widget_theme(self)

    def reject(self) -> None:
        if self._download_thread is not None:
            return
        super().reject()

    def _set_download_state(self, active: bool) -> None:
        self._download_button.setEnabled(not active)
        close_button = self._button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setEnabled(not active)

    def _start_download(self) -> None:
        if self._download_thread is not None:
            return

        self._set_download_state(True)
        progress = QProgressDialog("Downloading installer…", "", 0, 100, self)
        progress.setWindowTitle("Downloading Update")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setCancelButton(None)
        if self._update_info.download_size <= 0:
            progress.setRange(0, 0)
        self._progress_dialog = progress
        apply_widget_theme(progress)
        progress.show()

        thread = QThread(self)
        worker = _InstallerDownloadWorker(
            self._update_info,
            self._download_dir,
            self._download_installer_fn,
        )
        worker.moveToThread(thread)

        self._download_thread = thread
        self._download_worker = worker

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_download_progress)
        worker.finished.connect(self._on_download_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_download_thread(thread, worker))
        thread.start()

    @pyqtSlot(int, int)
    def _on_download_progress(self, received: int, total: int) -> None:
        if self._progress_dialog is None or total <= 0:
            return
        pct = min(100, int(received * 100 / total))
        self._progress_dialog.setValue(pct)

    @pyqtSlot(bool, object, str)
    def _on_download_finished(self, success: bool, path_obj: object, message: str) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog.deleteLater()
            self._progress_dialog = None

        self._set_download_state(False)
        if not success:
            show_warning_message(self, "Update Download Failed", message)
            return

        assert isinstance(path_obj, Path)
        if not self._launch_installer(path_obj):
            show_warning_message(
                self,
                "Installer Launch Failed",
                "The update downloaded successfully, but StormFuse could not start the installer.",
            )
            return

        self.accept()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.quit()

    def _launch_installer(self, path: Path) -> bool:
        try:
            launched = self._launch_installer_fn(path)
        except OSError as exc:
            log.warning(
                "Failed to launch installer",
                extra={
                    "event": "update.launch.error",
                    "ctx": {"path": str(path), "error": type(exc).__name__, "message": str(exc)},
                },
            )
            return False
        if not launched:
            log.warning(
                "Installer launch was rejected",
                extra={"event": "update.launch.error", "ctx": {"path": str(path)}},
            )
            return False

        log.info(
            "Installer launched",
            extra={"event": "update.launch", "ctx": {"path": str(path)}},
        )
        return True

    def _cleanup_download_thread(self, thread: QThread, worker: _InstallerDownloadWorker) -> None:
        if self._download_thread is thread:
            self._download_thread = None
        if self._download_worker is worker:
            self._download_worker = None
        worker.deleteLater()
        thread.deleteLater()


def _launch_installer(path: Path) -> bool:
    launched, _pid = QProcess.startDetached(str(path), [])
    return launched
