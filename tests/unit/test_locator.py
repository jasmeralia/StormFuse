# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for ffmpeg binary resolution (§7.1, §11.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stormfuse.ffmpeg import locator


def test_linux_ffmpeg_path_uses_path_when_no_local_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    system_ffmpeg = tmp_path / "bin" / "ffmpeg"
    monkeypatch.setattr(locator.sys, "platform", "linux")
    monkeypatch.setattr(locator, "_candidate_dirs", lambda: [])
    monkeypatch.setattr(locator.shutil, "which", lambda name: str(system_ffmpeg))

    assert locator.ffmpeg_path() == system_ffmpeg


def test_linux_ffprobe_path_raises_linux_guidance_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(locator.sys, "platform", "linux")
    monkeypatch.setattr(locator, "_candidate_dirs", lambda: [])
    monkeypatch.setattr(locator.shutil, "which", lambda _name: None)

    with pytest.raises(locator.FfmpegNotFoundError) as exc_info:
        locator.ffprobe_path()

    message = str(exc_info.value)
    assert "sudo apt install ffmpeg" in message
    assert "on PATH" in message
    assert "make fetch-ffmpeg" not in message


def test_windows_ffmpeg_path_uses_bundled_exe_without_path_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundled_dir = tmp_path / "resources" / "ffmpeg"
    bundled_dir.mkdir(parents=True)
    bundled_ffmpeg = bundled_dir / "ffmpeg.exe"
    bundled_ffmpeg.write_text("", encoding="utf-8")
    which_calls: list[str] = []

    def fake_which(name: str) -> None:
        which_calls.append(name)

    monkeypatch.setattr(locator.sys, "platform", "win32")
    monkeypatch.setattr(locator, "_candidate_dirs", lambda: [bundled_dir])
    monkeypatch.setattr(locator.shutil, "which", fake_which)

    assert locator.ffmpeg_path() == bundled_ffmpeg
    assert which_calls == []
