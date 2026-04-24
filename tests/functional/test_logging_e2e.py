# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows-only logging functional tests (§9.4, §11.3)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from stormfuse import logging_setup


@pytest.mark.windows_only
def test_clear_log_files_truncates_active_logs_and_deletes_stale_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logging_setup, "LOG_DIR", log_dir)

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    for handler in old_handlers:
        root.removeHandler(handler)

    try:
        json_handler, _ = logging_setup.setup_logging()
        latest_path = log_dir / "latest.log"
        session_path = Path(json_handler.baseFilename)
        stale_path = log_dir / "stale.log"

        stale_path.write_text("stale log\n", encoding="utf-8")
        logging.getLogger("stormfuse.functional").info("hello from functional test")

        for handler in root.handlers:
            handler.flush()

        assert session_path.read_text(encoding="utf-8")
        assert latest_path.read_text(encoding="utf-8")
        assert stale_path.read_text(encoding="utf-8") == "stale log\n"

        counts = logging_setup.clear_log_files()

        assert counts == {"deleted": 1, "truncated": 2, "failed": 0}
        assert session_path.read_text(encoding="utf-8") == ""
        assert latest_path.read_text(encoding="utf-8") == ""
        assert not stale_path.exists()
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        root.setLevel(logging.WARNING)
        logging_setup._state.human = None
        logging_setup._state.json_ = None
        for handler in old_handlers:
            root.addHandler(handler)
