# SPDX-License-Identifier: GPL-3.0-or-later
"""Timeout coverage for NVENC detection."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from stormfuse.ffmpeg.encoders import EncoderChoice, detect_encoder


def test_timeout_expired_falls_back_and_logs_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_run(
        argv: list[str], *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if argv[-1] == "-hwaccels":
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="cuda\n", stderr="")
        if argv[-1] == "-encoders":
            return subprocess.CompletedProcess(
                args=argv,
                returncode=0,
                stdout="Encoders:\n V..... h264_nvenc\n",
                stderr="",
            )
        raise subprocess.TimeoutExpired(argv, timeout=10, stderr="hung nvenc probe")

    monkeypatch.setattr("stormfuse.ffmpeg.encoders.run", fake_run)

    with caplog.at_level(logging.INFO, logger="ffmpeg.encoders"):
        assert detect_encoder(tmp_path / "ffmpeg.exe") == EncoderChoice.LIBX264

    record = next(record for record in caplog.records if record.event == "nvenc.probe_timeout")
    assert record.ctx["timeout_sec"] == 10
    assert record.ctx["stderr_tail"] == ["hung nvenc probe"]
