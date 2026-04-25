# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnostic error dialogs and clipboard bundles (§9.3, §10)."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stormfuse import __version__
from stormfuse.config import LOG_DIR
from stormfuse.ffmpeg.encoders import EncoderChoice

_MAX_STDERR_LINES = 10
TROUBLESHOOTING_URL = "https://github.com/jasmeralia/stormfuse#troubleshooting"


@dataclass(frozen=True)
class DiagnosticGuidance:
    """User-facing recovery copy for diagnostic dialogs."""

    summary: str
    why: str | None = None
    next_step: str | None = None


@dataclass(frozen=True)
class DiagnosticAction:
    """Optional user action exposed by the dialog."""

    label: str
    url: str


def show_diagnostic_dialog(
    parent: QWidget | None,
    *,
    title: str,
    message: str,
    event: str,
    stderr_tail: str = "",
    encoder: EncoderChoice | None = None,
    guidance: DiagnosticGuidance | None = None,
    action: DiagnosticAction | None = None,
) -> None:
    """Show a modal diagnostic dialog with a clipboard bundle action."""
    dialog = DiagnosticErrorDialog(
        parent,
        title=title,
        message=message,
        event=event,
        stderr_tail=stderr_tail,
        encoder=encoder,
        guidance=guidance,
        action=action,
    )
    dialog.exec()


class DiagnosticErrorDialog(QDialog):
    """Modal error dialog that can copy a full diagnostic bundle."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str,
        message: str,
        event: str,
        stderr_tail: str = "",
        encoder: EncoderChoice | None = None,
        guidance: DiagnosticGuidance | None = None,
        action: DiagnosticAction | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._message = message
        self._event = event
        self._stderr_tail = stderr_tail
        self._encoder = encoder
        self._guidance = guidance or DiagnosticGuidance(summary=message)
        self._action = action

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(640, 360)

        self._summary_label = self._make_label(
            "diagnosticSummaryLabel",
            self._guidance.summary,
        )
        self._why_label = self._make_label("diagnosticWhyLabel")
        if self._guidance.why:
            self._why_label.setText(f"Why: {self._guidance.why}")
        self._why_label.setVisible(bool(self._guidance.why))

        self._next_step_label = self._make_label("diagnosticNextStepLabel")
        if self._guidance.next_step:
            self._next_step_label.setText(f"Try next: {self._guidance.next_step}")
        self._next_step_label.setVisible(bool(self._guidance.next_step))

        self._event_label = QLabel(f"Event: {event}", self)
        self._event_label.setObjectName("diagnosticEventLabel")

        self._stderr_label = QLabel("Stderr tail (last 10 lines):", self)
        self._stderr_label.setObjectName("diagnosticStderrLabel")

        self._stderr_view = QPlainTextEdit(self)
        self._stderr_view.setObjectName("diagnosticStderrView")
        self._stderr_view.setReadOnly(True)
        self._stderr_view.setPlainText(format_stderr_excerpt(stderr_tail))

        self._copy_status = QLabel("", self)
        self._copy_status.setObjectName("diagnosticCopyStatus")

        button_box = self._build_button_box()

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary_label)
        layout.addWidget(self._why_label)
        layout.addWidget(self._next_step_label)
        layout.addWidget(self._event_label)
        layout.addWidget(self._stderr_label)
        layout.addWidget(self._stderr_view, stretch=1)
        layout.addWidget(self._copy_status)
        layout.addWidget(button_box)

    def _make_label(self, object_name: str, text: str = "") -> QLabel:
        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setObjectName(object_name)
        return label

    def _build_button_box(self) -> QDialogButtonBox:
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self._copy_button = QPushButton("Copy diagnostic", self)
        self._copy_button.setObjectName("copyDiagnosticButton")
        self._copy_button.clicked.connect(self.copy_diagnostic)
        button_box.addButton(self._copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        if self._action is not None:
            action_button = QPushButton(self._action.label, self)
            action_button.setObjectName("diagnosticActionButton")
            action_button.clicked.connect(self.open_action_url)
            button_box.addButton(action_button, QDialogButtonBox.ButtonRole.ActionRole)
        button_box.rejected.connect(self.reject)
        return button_box

    def diagnostic_bundle(self) -> str:
        """Return the clipboard-ready diagnostic bundle for this dialog."""
        return build_diagnostic_bundle(
            event=self._event,
            message=self._message,
            stderr_tail=self._stderr_tail,
            encoder=self._encoder,
        )

    def copy_diagnostic(self) -> None:
        """Copy the diagnostic bundle to the global clipboard."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            self._copy_status.setText("Clipboard unavailable.")
            return

        clipboard.setText(self.diagnostic_bundle())
        self._copy_status.setText("Diagnostic copied to clipboard.")

    def open_action_url(self) -> None:
        """Open the configured troubleshooting URL, if any."""
        if self._action is not None:
            QDesktopServices.openUrl(QUrl(self._action.url))


def build_job_failure_guidance(workflow: str, event: str, message: str) -> DiagnosticGuidance:
    """Translate job failure details into user-facing recovery guidance."""
    workflow_name = "Combine" if workflow == "combine" else "Compress"

    if event == "probe.error":
        target = "one of the selected files" if workflow == "combine" else "the selected input file"
        retry = (
            "Check that each file still exists locally, is an MKV/MP4, "
            "and is not locked by another app, then try again."
            if workflow == "combine"
            else "Check that the source file still exists locally and can be opened, "
            "then browse for it again and rerun."
        )
        return DiagnosticGuidance(
            summary=(
                f"{workflow_name} could not start because StormFuse could not inspect {target}."
            ),
            why=message,
            next_step=retry,
        )

    if workflow == "compress" and event == "job.fail" and message.startswith("Cannot compress:"):
        return DiagnosticGuidance(
            summary="Compress cannot fit this video under the current target size.",
            why=message,
            next_step="Increase the target size or shorten the source video, then try again.",
        )

    if event == "ffmpeg.exit":
        retry = (
            "Review the stderr excerpt below, confirm the output folder is writable, "
            "and rerun. If the inputs differ, keep the normalize path and try again."
            if workflow == "combine"
            else "Review the stderr excerpt below, confirm the output folder is writable, "
            "then try a larger target size or disable 2-pass and rerun."
        )
        return DiagnosticGuidance(
            summary=f"{workflow_name} failed while ffmpeg was processing the job.",
            why=message,
            next_step=retry,
        )

    return DiagnosticGuidance(
        summary=f"{workflow_name} failed.",
        why=message,
        next_step="Copy the diagnostic bundle, review the log excerpt, and try the job again.",
    )


def format_stderr_excerpt(stderr_tail: str) -> str:
    """Format the final stderr lines for dialog display."""
    lines = _stderr_lines(stderr_tail)
    if not lines:
        return "No stderr output captured."
    return "\n".join(lines)


def build_diagnostic_bundle(
    *,
    event: str,
    message: str,
    stderr_tail: str,
    encoder: EncoderChoice | None,
    latest_log_path: Path | None = None,
) -> str:
    """Build the clipboard diagnostic payload required by the spec."""
    stderr_excerpt = format_stderr_excerpt(stderr_tail)
    latest_path = latest_log_path or (LOG_DIR / "latest.log")
    latest_log = _read_latest_log(latest_path)

    return "\n".join(
        [
            "StormFuse diagnostic",
            f"App version: {__version__}",
            f"OS: {platform.platform()}",
            f"Encoder state: {format_encoder_state(encoder)}",
            f"Event: {event}",
            f"Message: {message}",
            "",
            "Stderr tail:",
            stderr_excerpt,
            "",
            f"latest.log: {latest_path}",
            latest_log,
        ]
    )


def format_encoder_state(encoder: EncoderChoice | None) -> str:
    """Format encoder state in the terms used by the design document."""
    if encoder == EncoderChoice.NVENC:
        return "NVENC_AVAILABLE"
    if encoder == EncoderChoice.LIBX264:
        return "LIBX264_FALLBACK"
    return "NOT_PROBED"


def _stderr_lines(stderr_tail: str) -> list[str]:
    return [line.rstrip() for line in stderr_tail.splitlines() if line.strip()][-_MAX_STDERR_LINES:]


def _read_latest_log(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"[Unable to read latest.log: {exc}]"

    if content:
        return content
    return "[latest.log is empty]"
