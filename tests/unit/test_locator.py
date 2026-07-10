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


def test_bundle_ffmpeg_dir_returns_none_without_meipass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(locator.sys, "_MEIPASS", raising=False)

    assert locator._bundle_ffmpeg_dir() is None


def test_bundle_ffmpeg_dir_resolves_under_meipass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(locator.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert locator._bundle_ffmpeg_dir() == tmp_path / "resources" / "ffmpeg"


def test_source_ffmpeg_dir_finds_repo_root_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_module_path = tmp_path / "src" / "stormfuse" / "ffmpeg" / "locator.py"
    fake_module_path.parent.mkdir(parents=True)
    fake_module_path.write_text("", encoding="utf-8")
    (tmp_path / "resources" / "ffmpeg").mkdir(parents=True)

    monkeypatch.setattr(locator, "__file__", str(fake_module_path))

    assert locator._source_ffmpeg_dir() == tmp_path / "resources" / "ffmpeg"


def test_source_ffmpeg_dir_returns_none_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_module_path = tmp_path / "src" / "stormfuse" / "ffmpeg" / "locator.py"
    fake_module_path.parent.mkdir(parents=True)
    fake_module_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(locator, "__file__", str(fake_module_path))

    assert locator._source_ffmpeg_dir() is None


def test_candidate_dirs_includes_bundle_then_source_when_both_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle_dir = tmp_path / "bundle"
    source_dir = tmp_path / "source"

    monkeypatch.setattr(locator, "_bundle_ffmpeg_dir", lambda: bundle_dir)
    monkeypatch.setattr(locator, "_source_ffmpeg_dir", lambda: source_dir)

    assert locator._candidate_dirs() == [bundle_dir, source_dir]


def test_candidate_dirs_omits_missing_bundle_and_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(locator, "_bundle_ffmpeg_dir", lambda: None)
    monkeypatch.setattr(locator, "_source_ffmpeg_dir", lambda: None)

    assert locator._candidate_dirs() == []
