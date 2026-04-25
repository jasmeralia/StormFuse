# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the ffmpeg subprocess helper."""

from __future__ import annotations

from pathlib import Path

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


def test_run_omits_ffreport_when_debug_logging_disabled(monkeypatch) -> None:
    captured: dict[str, object] = {}
    subprocess_helper.configure_debug_logging(False)

    def fake_run(argv: list[str], **kwargs: object) -> object:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(subprocess_helper.subprocess, "run", fake_run)

    subprocess_helper.run(["ffprobe", "-version"], text=True, job_id="job-123")

    assert captured["argv"] == ["ffprobe", "-version"]
    assert "env" not in captured["kwargs"]


def test_popen_sets_ffreport_for_ffmpeg_when_enabled(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    subprocess_helper.configure_debug_logging(True)
    monkeypatch.setattr(
        subprocess_helper,
        "ffmpeg_report_path",
        lambda tool_name, job_id: tmp_path / "StormFuse Logs" / f"{tool_name}-{job_id}.log",
    )

    def fake_popen(argv: list[str], **kwargs: object) -> object:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(subprocess_helper.subprocess, "Popen", fake_popen)

    try:
        subprocess_helper.popen(
            ["C:\\ffmpeg\\bin\\ffmpeg.exe", "-version"], stdin=1, job_id="job-123"
        )
    finally:
        subprocess_helper.configure_debug_logging(False)

    assert captured["argv"] == ["C:\\ffmpeg\\bin\\ffmpeg.exe", "-version"]
    assert captured["kwargs"]["stdin"] == 1
    assert captured["kwargs"]["env"]["FFREPORT"] == subprocess_helper.build_ffreport_value(
        str(tmp_path / "StormFuse Logs" / "ffmpeg-job-123.log")
    )


def test_build_ffreport_value_quotes_windows_paths_with_spaces() -> None:
    value = subprocess_helper.build_ffreport_value(
        r"C:\Users\Morgan\App Data\StormFuse\logs\ffprobe-job-123.log"
    )

    assert value == r"file='C:\Users\Morgan\App Data\StormFuse\logs\ffprobe-job-123.log':level=48"


def test_run_sets_ffreport_for_ffprobe_when_enabled(monkeypatch) -> None:
    captured: dict[str, object] = {}
    subprocess_helper.configure_debug_logging(True)
    monkeypatch.setattr(
        subprocess_helper,
        "ffmpeg_report_path",
        lambda tool_name, job_id: Path(f"/tmp/stormfuse-logs/{tool_name}-{job_id}.log"),
    )

    def fake_run(argv: list[str], **kwargs: object) -> object:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(subprocess_helper.subprocess, "run", fake_run)

    try:
        subprocess_helper.run(["/opt/ffprobe", "-version"], text=True, job_id="probe-job")
    finally:
        subprocess_helper.configure_debug_logging(False)

    assert captured["argv"] == ["/opt/ffprobe", "-version"]
    assert captured["kwargs"]["env"]["FFREPORT"] == subprocess_helper.build_ffreport_value(
        str(Path("/tmp/stormfuse-logs/ffprobe-probe-job.log"))
    )
