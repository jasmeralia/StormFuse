# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for global error-handling hooks."""

from __future__ import annotations

import logging
import sys
import threading

import pytest

from stormfuse import error_handling


def test_install_sys_hook_replaces_sys_excepthook() -> None:
    original = sys.excepthook
    try:
        hook = error_handling.install_sys_hook()
        assert sys.excepthook is hook
    finally:
        sys.excepthook = original


def test_install_thread_hook_replaces_threading_excepthook() -> None:
    original = threading.excepthook
    try:
        hook = error_handling.install_thread_hook()
        assert threading.excepthook is hook
    finally:
        threading.excepthook = original


def test_installed_sys_hook_logs_event_and_calls_dialog_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    original = sys.excepthook
    captured: list[error_handling.UnhandledError] = []

    try:
        error_handling.install_sys_hook(captured.append)
        with caplog.at_level(logging.ERROR, logger="stormfuse.error_handling"):
            try:
                raise RuntimeError("boom")
            except RuntimeError as exc:
                sys.excepthook(type(exc), exc, exc.__traceback__)
    finally:
        sys.excepthook = original

    assert len(captured) == 1
    assert captured[0].event == "app.unhandled"
    assert "RuntimeError: boom" in captured[0].stderr_tail

    record = next(record for record in caplog.records if record.event == "app.unhandled")
    assert "boom" in record.getMessage()
    assert record.ctx["stderr_tail"]


def test_snapshot_previous_fatal_log_moves_crash_to_session_file(tmp_path) -> None:
    fatal_log = tmp_path / "fatal_errors.log"
    fatal_log.write_text(
        "Windows fatal exception: access violation\n  File Windows fatal exception\n",
        encoding="utf-8",
    )

    report = error_handling.snapshot_previous_fatal_log(tmp_path)

    assert report is not None
    assert report.path.name.startswith("fatal_errors-")
    assert report.path.read_text(encoding="utf-8") == report.content
    assert report.truncated
    assert fatal_log.read_text(encoding="utf-8") == ""


def test_snapshot_previous_fatal_log_ignores_empty_file(tmp_path) -> None:
    (tmp_path / "fatal_errors.log").write_text("", encoding="utf-8")

    assert error_handling.snapshot_previous_fatal_log(tmp_path) is None
