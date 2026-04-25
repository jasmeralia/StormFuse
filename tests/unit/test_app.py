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

    def exec(self) -> int:
        return 0


def test_run_app_offers_troubleshooting_when_ffmpeg_is_missing(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_show(parent, **kwargs) -> None:
        captured["parent"] = parent
        captured.update(kwargs)

    monkeypatch.setattr(app_module, "setup_logging", lambda: None)
    monkeypatch.setattr(app_module, "ExceptionHookingApplication", _FakeApplication)
    monkeypatch.setattr(app_module, "install_sys_hook", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "install_thread_hook", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "enable_fault_handler", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "install_qt_message_handler", lambda: None)
    monkeypatch.setattr(app_module, "install_signal_hooks", lambda: None)
    monkeypatch.setattr(app_module, "apply_application_theme", lambda *_args, **_kwargs: "light")
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


def test_run_app_enables_startup_update_checks(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeWindow:
        def __init__(self, ffmpeg_exe, ffprobe_exe, encoder, **kwargs) -> None:
            captured["ffmpeg_exe"] = ffmpeg_exe
            captured["ffprobe_exe"] = ffprobe_exe
            captured["encoder"] = encoder
            captured.update(kwargs)

        def show(self) -> None:
            captured["shown"] = True

    monkeypatch.setattr(app_module, "setup_logging", lambda: None)
    monkeypatch.setattr(app_module, "ExceptionHookingApplication", _FakeApplication)
    monkeypatch.setattr(app_module, "install_sys_hook", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "install_thread_hook", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "enable_fault_handler", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "install_qt_message_handler", lambda: None)
    monkeypatch.setattr(app_module, "install_signal_hooks", lambda: None)
    monkeypatch.setattr(app_module, "apply_application_theme", lambda *_args, **_kwargs: "light")
    monkeypatch.setattr(app_module, "icons_dir", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(app_module, "ffmpeg_path", lambda: "ffmpeg.exe")
    monkeypatch.setattr(app_module, "ffprobe_path", lambda: "ffprobe.exe")
    monkeypatch.setattr(app_module, "detect_encoder", lambda _path: "NVENC")
    monkeypatch.setattr(app_module, "MainWindow", _FakeWindow)

    exit_code = app_module.run_app()

    assert exit_code == 0
    assert captured["check_updates_on_startup"] is True
    assert captured["shown"] is True
