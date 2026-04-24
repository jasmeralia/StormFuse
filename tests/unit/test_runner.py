# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for stormfuse.ffmpeg.runner argv construction (§11.2).

No real subprocesses. subprocess.Popen is patched with a mock.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stormfuse.ffmpeg.runner import ProgressEvent, RunResult, _parse_progress_block, run_ffmpeg
from stormfuse.jobs.base import Job

FAKE_FFMPEG = Path("/fake/ffmpeg.exe")


def _make_mock_proc(returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode
    proc.stderr = iter([])  # empty stderr
    proc.stdin = MagicMock()
    return proc


class TestParseProgressBlock:
    def test_out_time_us(self) -> None:
        lines = ["out_time_us=4000000", "speed=1.00x"]
        ev = _parse_progress_block(lines)
        assert ev.out_time_sec == pytest.approx(4.0)

    def test_speed(self) -> None:
        lines = ["speed=2.5x"]
        ev = _parse_progress_block(lines)
        assert ev.speed == pytest.approx(2.5)

    def test_frame(self) -> None:
        lines = ["frame=150"]
        ev = _parse_progress_block(lines)
        assert ev.frame == 150

    def test_bitrate(self) -> None:
        lines = ["bitrate=1234.5kbits/s"]
        ev = _parse_progress_block(lines)
        assert ev.bitrate_kbps == pytest.approx(1234.5)

    def test_empty_block(self) -> None:
        ev = _parse_progress_block([])
        assert ev.out_time_sec == 0.0
        assert ev.speed == 0.0


class TestRunFfmpeg:
    def test_runner_logs_bound_job_id(self, caplog: pytest.LogCaptureFixture) -> None:
        class RunnerJob(Job):
            def _run_job(self) -> None:
                run_ffmpeg(FAKE_FFMPEG, [])

        job = RunnerJob()

        with (
            caplog.at_level(logging.INFO, logger="ffmpeg.runner"),
            patch("stormfuse.ffmpeg.runner.subprocess.Popen", return_value=_make_mock_proc()),
        ):
            job.run()

        runner_records = [record for record in caplog.records if record.name == "ffmpeg.runner"]
        assert runner_records
        assert {record.event for record in runner_records} == {"ffmpeg.start", "ffmpeg.exit"}
        assert all(record.job_id == job.job_id for record in runner_records)

    def test_basic_argv_construction(self) -> None:
        captured: list[list[str]] = []

        def fake_popen(args: list[str], **kwargs: object) -> MagicMock:
            captured.append(list(args))
            return _make_mock_proc()

        with patch("stormfuse.ffmpeg.runner.subprocess.Popen", side_effect=fake_popen):
            run_ffmpeg(FAKE_FFMPEG, ["-i", "input.mkv", "output.mkv"])

        assert len(captured) == 1
        argv = captured[0]
        assert argv[0] == str(FAKE_FFMPEG)
        assert "-hide_banner" in argv
        assert "-y" in argv
        assert "-i" in argv
        assert "input.mkv" in argv

    def test_no_shell_true(self) -> None:
        with patch("stormfuse.ffmpeg.runner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _make_mock_proc()
            run_ffmpeg(FAKE_FFMPEG, [])
            _, kwargs = mock_popen.call_args
            assert not kwargs.get("shell", False)

    def test_returns_run_result(self) -> None:
        with patch("stormfuse.ffmpeg.runner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _make_mock_proc(returncode=0)
            result = run_ffmpeg(FAKE_FFMPEG, [])
        assert isinstance(result, RunResult)
        assert result.succeeded

    def test_nonzero_exit_not_succeeded(self) -> None:
        with patch("stormfuse.ffmpeg.runner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _make_mock_proc(returncode=1)
            result = run_ffmpeg(FAKE_FFMPEG, [])
        assert not result.succeeded
        assert result.exit_code == 1

    def test_progress_flag_added_when_callback_given(self) -> None:
        captured: list[list[str]] = []

        def fake_popen(args: list[str], **kwargs: object) -> MagicMock:
            captured.append(list(args))
            return _make_mock_proc()

        def noop_progress(ev: ProgressEvent) -> None:
            pass

        with patch("stormfuse.ffmpeg.runner.subprocess.Popen", side_effect=fake_popen):
            run_ffmpeg(FAKE_FFMPEG, [], on_progress=noop_progress)

        assert "-progress" in captured[0]
        assert "-nostats" in captured[0]

    def test_os_error_returns_failed_result(self) -> None:
        with patch("stormfuse.ffmpeg.runner.subprocess.Popen", side_effect=OSError("no such file")):
            result = run_ffmpeg(FAKE_FFMPEG, [])
        assert not result.succeeded
        assert result.exit_code == -1

    def test_cancel_logs_single_structured_event(self, caplog: pytest.LogCaptureFixture) -> None:
        cancel_event = threading.Event()
        cancel_event.set()

        proc = _make_mock_proc(returncode=255)
        proc.poll.side_effect = [None, 0, 0, 0]

        with (
            caplog.at_level(logging.INFO, logger="ffmpeg.runner"),
            patch("stormfuse.ffmpeg.runner.subprocess.Popen", return_value=proc),
        ):
            result = run_ffmpeg(FAKE_FFMPEG, [], cancel_event=cancel_event)

        assert not result.succeeded
        events = [getattr(record, "event", None) for record in caplog.records]
        assert "ffmpeg.cancel" in events
        assert "ffmpeg.cancel.q" not in events
        assert "ffmpeg.cancel.terminate" not in events
        assert "ffmpeg.cancel.kill" not in events

        cancel_record = next(record for record in caplog.records if record.event == "ffmpeg.cancel")
        assert cancel_record.ctx["cancel_step"] == "q"

    def test_progress_logs_include_job_id(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        progress_path = tmp_path / "progress.txt"
        job_id = "combine-018bcfe568000000123456789abc"
        callback_events: list[ProgressEvent] = []

        def fake_mkstemp(prefix: str, suffix: str) -> tuple[int, str]:
            fd = os.open(progress_path, os.O_CREAT | os.O_RDWR)
            return fd, str(progress_path)

        def fake_popen(args: list[str], **kwargs: object) -> MagicMock:
            progress_arg = args[args.index("-progress") + 1]
            Path(progress_arg).write_text(
                "out_time_us=1000000\n"
                "frame=30\n"
                "progress=continue\n"
                "out_time_us=2500000\n"
                "speed=1.25x\n"
                "bitrate=900.0kbits/s\n"
                "frame=75\n"
                "progress=end\n",
                encoding="utf-8",
            )
            proc = _make_mock_proc(returncode=0)
            proc.stderr = iter([b"encoded frame\n"])
            proc.poll.side_effect = [None, None, 0, 0]
            return proc

        with (
            caplog.at_level(logging.DEBUG, logger="ffmpeg.runner"),
            patch("stormfuse.ffmpeg.runner.tempfile.mkstemp", side_effect=fake_mkstemp),
            patch("stormfuse.ffmpeg.runner.subprocess.Popen", side_effect=fake_popen),
        ):
            run_ffmpeg(
                FAKE_FFMPEG,
                ["-i", "input.mkv", "output.mkv"],
                on_progress=callback_events.append,
                job_id=job_id,
            )

        progress_records = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "ffmpeg.progress"
        ]
        assert callback_events
        assert progress_records
        assert all(record.job_id == job_id for record in progress_records)
        assert any(
            record.event == "ffmpeg.start" and record.job_id == job_id for record in caplog.records
        )
        assert any(
            record.event == "ffmpeg.stderr" and record.job_id == job_id for record in caplog.records
        )
        assert any(
            record.event == "ffmpeg.exit" and record.job_id == job_id for record in caplog.records
        )
