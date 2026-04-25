# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for diagnostic error dialogs (§9.3, §10, §11.4)."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton
from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ui import error_dialogs
from stormfuse.ui.error_dialogs import (
    TROUBLESHOOTING_URL,
    DiagnosticAction,
    DiagnosticErrorDialog,
    DiagnosticGuidance,
    build_diagnostic_bundle,
    build_job_failure_guidance,
)


def test_build_diagnostic_bundle_includes_required_context(tmp_path) -> None:
    latest_log = tmp_path / "latest.log"
    latest_log.write_text("json line 1\njson line 2\n", encoding="utf-8")
    stderr_tail = "\n".join(f"stderr-{index:02d}" for index in range(1, 13))

    bundle = build_diagnostic_bundle(
        event="ffmpeg.exit",
        message="Combine failed",
        stderr_tail=stderr_tail,
        encoder=EncoderChoice.NVENC,
        latest_log_path=latest_log,
    )

    assert "App version:" in bundle
    assert "OS:" in bundle
    assert "Encoder state: NVENC_AVAILABLE" in bundle
    assert "Event: ffmpeg.exit" in bundle
    assert "Message: Combine failed" in bundle
    assert "stderr-01" not in bundle
    assert "stderr-03" in bundle
    assert "stderr-12" in bundle
    assert "json line 1" in bundle
    assert str(latest_log) in bundle


def test_diagnostic_dialog_shows_excerpt_and_copies_bundle(
    qtbot: QtBot, tmp_path, monkeypatch
) -> None:
    latest_log = tmp_path / "latest.log"
    latest_log.write_text("latest log body\n", encoding="utf-8")
    monkeypatch.setattr(error_dialogs, "LOG_DIR", tmp_path)
    stderr_tail = "\n".join(f"tail-{index:02d}" for index in range(1, 13))
    opened_urls: list[str] = []

    monkeypatch.setattr(
        error_dialogs.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )

    dialog = DiagnosticErrorDialog(
        title="Compress failed",
        message="ffmpeg exited with code 1",
        event="ffmpeg.exit",
        stderr_tail=stderr_tail,
        encoder=EncoderChoice.LIBX264,
        guidance=DiagnosticGuidance(
            summary="Compress failed while ffmpeg was processing the job.",
            why="ffmpeg exited with code 1",
            next_step="Try a larger target size or disable 2-pass and rerun.",
        ),
        action=DiagnosticAction(
            label="Open Troubleshooting",
            url=TROUBLESHOOTING_URL,
        ),
    )
    qtbot.addWidget(dialog)

    summary_label = dialog.findChild(QLabel, "diagnosticSummaryLabel")
    why_label = dialog.findChild(QLabel, "diagnosticWhyLabel")
    next_step_label = dialog.findChild(QLabel, "diagnosticNextStepLabel")
    event_label = dialog.findChild(QLabel, "diagnosticEventLabel")
    stderr_view = dialog.findChild(QPlainTextEdit, "diagnosticStderrView")
    copy_status = dialog.findChild(QLabel, "diagnosticCopyStatus")
    action_button = dialog.findChild(QPushButton, "diagnosticActionButton")
    send_button = dialog.findChild(QPushButton, "diagnosticSendButton")

    assert summary_label is not None
    assert why_label is not None
    assert next_step_label is not None
    assert event_label is not None
    assert stderr_view is not None
    assert copy_status is not None
    assert action_button is not None
    assert send_button is not None
    assert summary_label.text() == "Compress failed while ffmpeg was processing the job."
    assert why_label.text() == "Why: ffmpeg exited with code 1"
    assert (
        next_step_label.text() == "Try next: Try a larger target size or disable 2-pass and rerun."
    )
    assert event_label.text() == "Event: ffmpeg.exit"
    assert stderr_view.toPlainText() == "\n".join(f"tail-{index:02d}" for index in range(3, 13))

    action_button.click()
    dialog.copy_diagnostic()

    assert opened_urls == [TROUBLESHOOTING_URL]
    assert copy_status.text() == "Diagnostic copied to clipboard."
    clipboard_text = QApplication.clipboard().text()
    assert "Encoder state: LIBX264_FALLBACK" in clipboard_text
    assert "latest log body" in clipboard_text


def test_build_job_failure_guidance_mentions_report_file(tmp_path, monkeypatch) -> None:
    report_path = tmp_path / "ffmpeg-job-123.log"
    report_path.write_text("debug log\n", encoding="utf-8")
    monkeypatch.setattr(
        error_dialogs,
        "ffmpeg_report_path",
        lambda tool_name, job_id: tmp_path / f"{tool_name}-{job_id}.log",
    )

    guidance = build_job_failure_guidance(
        "compress",
        "ffmpeg.exit",
        "ffmpeg encode failed",
        job_id="job-123",
    )

    assert guidance.next_step is not None
    assert str(report_path) in guidance.next_step
