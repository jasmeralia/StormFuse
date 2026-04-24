# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for ffprobe logging and parsing (§7.2, §9)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stormfuse.ffmpeg.probe import ProbeError, probe
from stormfuse.jobs.base import Job

FAKE_FFPROBE = Path("/fake/ffprobe.exe")


def test_probe_logs_bound_job_id(caplog: pytest.LogCaptureFixture) -> None:
    class ProbeJob(Job):
        def __init__(self) -> None:
            self.probed = False
            super().__init__()

        def _run_job(self) -> None:
            probe(FAKE_FFPROBE, Path("/videos/input.mkv"))
            self.probed = True

    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "r_frame_rate": "30000/1001",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
        ],
        "format": {"duration": "12.5", "size": "12345"},
    }
    result = MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
    job = ProbeJob()

    with (
        caplog.at_level(logging.DEBUG, logger="ffmpeg.probe"),
        patch("stormfuse.ffmpeg.probe.subprocess.run", return_value=result),
    ):
        job.run()

    assert job.probed
    probe_records = [record for record in caplog.records if record.name == "ffmpeg.probe"]
    assert probe_records
    assert {record.event for record in probe_records} == {"probe.start", "probe.result"}
    assert all(record.job_id == job.job_id for record in probe_records)


def test_probe_error_logs_job_id(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.ERROR, logger="ffmpeg.probe"),
        patch(
            "stormfuse.ffmpeg.probe.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="line 1\nline 2\n"),
        ),
        pytest.raises(ProbeError),
    ):
        probe(FAKE_FFPROBE, Path("/videos/bad.mkv"), job_id="combine-018bcfe568000000123456789abc")

    error_record = next(record for record in caplog.records if record.event == "probe.error")
    assert error_record.job_id == "combine-018bcfe568000000123456789abc"
    assert error_record.ctx["stderr_tail"] == ["line 1", "line 2"]
