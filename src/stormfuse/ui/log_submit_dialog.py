# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog for sending local diagnostic logs to the developer."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stormfuse.config import LOG_DIR
from stormfuse.core.log_uploader import LogUploader
from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ui.theme import apply_widget_theme, show_information_message, show_warning_message


class _UploadWorker(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, uploader: LogUploader, user_notes: str) -> None:
        super().__init__()
        self._uploader = uploader
        self._user_notes = user_notes

    @pyqtSlot()
    def run(self) -> None:
        success, message = self._uploader.upload(self._user_notes)
        self.finished.emit(success, message)


class LogSubmitDialog(QDialog):
    """Collect user notes and upload the current local log bundle."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        encoder: EncoderChoice | None = None,
        uploader_factory: Callable[[EncoderChoice | None], LogUploader] | None = None,
    ) -> None:
        super().__init__(parent)
        self._encoder = encoder
        self._uploader_factory = uploader_factory or (lambda encoder: LogUploader(encoder=encoder))
        self._upload_thread: QThread | None = None
        self._upload_worker: _UploadWorker | None = None

        self.setWindowTitle("Send Logs to Developer")
        self.resize(560, 360)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Describe what happened and what you were doing before the problem occurred.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setObjectName("logSubmitNotesEdit")
        self._notes_edit.setPlaceholderText(
            "Example: Selected two MP4 files, clicked Combine, and ffmpeg failed immediately."
        )
        self._notes_edit.textChanged.connect(self._update_character_counter)
        layout.addWidget(self._notes_edit, stretch=1)

        self._counter_label = QLabel("", self)
        self._counter_label.setObjectName("logSubmitCounterLabel")
        layout.addWidget(self._counter_label)

        privacy_notice = QLabel(
            "This sends:\n"
            f"- all files currently in {LOG_DIR}\n"
            "- app version, hostname, username, OS version, and OS platform\n"
            "- encoder state (NVENC or libx264)\n"
            "- the notes you type here",
            self,
        )
        privacy_notice.setObjectName("logSubmitPrivacyNotice")
        privacy_notice.setWordWrap(True)
        layout.addWidget(privacy_notice)

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setObjectName("logSubmitProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("", self)
        self._status_label.setObjectName("logSubmitStatusLabel")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self._send_button = QPushButton("Send", self)
        self._send_button.setObjectName("logSubmitSendButton")
        self._send_button.clicked.connect(self._start_upload)
        self._button_box.addButton(self._send_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._update_character_counter()
        apply_widget_theme(self)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is not None and self._upload_thread is not None:
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self._upload_thread is not None:
            return
        super().reject()

    def _update_character_counter(self) -> None:
        count = len(self._notes_edit.toPlainText())
        self._counter_label.setText(f"{count} characters")

    def _set_upload_state(self, active: bool) -> None:
        self._notes_edit.setEnabled(not active)
        self._send_button.setEnabled(not active)
        cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setEnabled(not active)
        self._progress_bar.setVisible(active)

    def _start_upload(self) -> None:
        if self._upload_thread is not None:
            return

        self._set_upload_state(True)
        self._status_label.setText("Sending logs…")

        thread = QThread(self)
        worker = _UploadWorker(
            self._uploader_factory(self._encoder),
            self._notes_edit.toPlainText(),
        )
        worker.moveToThread(thread)

        self._upload_thread = thread
        self._upload_worker = worker

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_upload_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_upload_thread(thread, worker))
        thread.start()

    @pyqtSlot(bool, str)
    def _on_upload_finished(self, success: bool, message: str) -> None:
        self._status_label.setText(message)
        self._set_upload_state(False)
        if success:
            show_information_message(self, "Logs Sent", message)
            self.accept()
            return
        show_warning_message(self, "Log Submission Failed", message)

    def _cleanup_upload_thread(self, thread: QThread, worker: _UploadWorker) -> None:
        if self._upload_thread is thread:
            self._upload_thread = None
        if self._upload_worker is worker:
            self._upload_worker = None
        worker.deleteLater()
        thread.deleteLater()
