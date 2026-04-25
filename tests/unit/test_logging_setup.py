# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for log-directory maintenance."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from stormfuse import logging_setup


def test_clear_log_files_deletes_ffmpeg_report_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(logging_setup, "LOG_DIR", tmp_path)

    active_log = tmp_path / "latest.log"
    active_log.write_text("active\n", encoding="utf-8")
    ffmpeg_report = tmp_path / "ffmpeg-job-123.log"
    ffmpeg_report.write_text("ffmpeg debug\n", encoding="utf-8")

    handler = logging.FileHandler(active_log, encoding="utf-8")
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    for old_handler in old_handlers:
        root.removeHandler(old_handler)
    root.addHandler(handler)

    try:
        counts = logging_setup.clear_log_files()
    finally:
        root.removeHandler(handler)
        handler.close()
        for old_handler in old_handlers:
            root.addHandler(old_handler)

    assert counts == {"deleted": 1, "truncated": 1, "failed": 0}
    assert "active\n" not in active_log.read_text(encoding="utf-8")
    assert not ffmpeg_report.exists()
