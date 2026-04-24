# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for application startup error handling (§7.1, §10, §11.2)."""

from __future__ import annotations

import stormfuse.app as app_module
from stormfuse.ffmpeg.locator import FfmpegNotFoundError
from stormfuse.ui.error_dialogs import TROUBLESHOOTING_URL


class _FakeApplication:
    def __init__(self, argv: list[str]) -> None:
        self.argv = argv

    def setApplicationName(self, _: str) -> None:
        pass

    def setApplicationVersion(self, _: str) -> None:
        pass

    def setOrganizationName(self, _: str) -> None:
        pass

    def setWindowIcon(self, _: object) -> None:
        pass


def test_run_app_offers_troubleshooting_when_ffmpeg_is_missing(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_show(parent, **kwargs) -> None:
        captured["parent"] = parent
        captured.update(kwargs)

    monkeypatch.setattr(app_module, "setup_logging", lambda: None)
    monkeypatch.setattr(app_module, "QApplication", _FakeApplication)
    monkeypatch.setattr(app_module, "icons_dir", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(
        app_module,
        "ffmpeg_path",
        lambda: (_ for _ in ()).throw(FfmpegNotFoundError("ffmpeg.exe")),
    )
    monkeypatch.setattr(app_module, "show_diagnostic_dialog", fake_show)

    exit_code = app_module.run_app()

    assert exit_code == 1
    assert captured["parent"] is None
    assert captured["title"] == "StormFuse — Missing ffmpeg"
    assert captured["event"] == "app.ffmpeg_missing"
    guidance = captured["guidance"]
    action = captured["action"]
    assert guidance.summary == (
        "StormFuse could not start because the bundled ffmpeg files are missing."
    )
    assert action.label == "Open Troubleshooting"
    assert action.url == TROUBLESHOOTING_URL
    assert "make fetch-ffmpeg" in str(captured["message"])
