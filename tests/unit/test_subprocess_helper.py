# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the ffmpeg subprocess helper."""

from __future__ import annotations

from stormfuse.ffmpeg import _subprocess as subprocess_helper


def test_run_injects_creationflags_on_windows(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(subprocess_helper.sys, "platform", "win32")
    monkeypatch.setattr(subprocess_helper, "_CREATE_NO_WINDOW", 0x1234)

    def fake_run(argv: list[str], **kwargs: object) -> object:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(subprocess_helper.subprocess, "run", fake_run)

    subprocess_helper.run(["ffmpeg", "-version"], text=True)

    assert captured["argv"] == ["ffmpeg", "-version"]
    assert captured["kwargs"]["creationflags"] == 0x1234
    assert captured["kwargs"]["text"] is True


def test_popen_leaves_creationflags_unset_off_windows(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(subprocess_helper.sys, "platform", "linux")

    def fake_popen(argv: list[str], **kwargs: object) -> object:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(subprocess_helper.subprocess, "Popen", fake_popen)

    subprocess_helper.popen(["ffmpeg", "-version"], stdin=1)

    assert captured["argv"] == ["ffmpeg", "-version"]
    assert "creationflags" not in captured["kwargs"]
    assert captured["kwargs"]["stdin"] == 1
