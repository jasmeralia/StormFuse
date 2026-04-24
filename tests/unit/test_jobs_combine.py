# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for CombineJob progress weighting (§5.1, §11.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.concat import ConcatPlan, ConcatStrategy
from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ffmpeg.runner import ProgressEvent, RunResult
from stormfuse.ffmpeg.signatures import VideoSignature
from stormfuse.jobs.combine import CombineJob


def _probe(
    path: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    duration: float = 60.0,
) -> FileProbe:
    return FileProbe(
        path=path,
        video=VideoStream(codec="h264", width=width, height=height, pix_fmt="yuv420p", fps=30.0),
        audio=AudioStream(codec="aac", sample_rate=48000, channels=2),
        duration_sec=duration,
        size_bytes=1,
        raw={},
    )


def test_stream_copy_progress_uses_concat_fraction(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = [
        _probe(tmp_path / "a.mkv", duration=10.0),
        _probe(tmp_path / "b.mkv", duration=30.0),
    ]
    job = CombineJob(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        inputs=[probe.path for probe in probes],
        output=tmp_path / "combined.mkv",
        encoder=EncoderChoice.LIBX264,
    )
    progress_events: list[tuple[float, str]] = []
    job.progress.connect(lambda pct, phase: progress_events.append((pct, phase)))

    def fake_run_ffmpeg(*args: object, **kwargs: object) -> RunResult:
        on_progress = kwargs["on_progress"]
        assert callable(on_progress)
        on_progress(ProgressEvent(out_time_sec=20.0))
        return RunResult(argv=[], exit_code=0, duration_sec=0.01, stderr_tail="")

    monkeypatch.setattr("stormfuse.jobs.combine.run_ffmpeg", fake_run_ffmpeg)

    job._run_stream_copy(probes)

    assert progress_events == [(0.5, "Stream-copy concat…")]


def test_normalize_progress_weights_normalize_and_concat_by_duration(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy_probe = _probe(tmp_path / "copy.mkv", duration=30.0)
    normalize_probe = _probe(tmp_path / "normalize.mp4", width=1280, height=720, duration=10.0)
    plan = ConcatPlan(
        strategy=ConcatStrategy.NORMALIZE_THEN_CONCAT,
        inputs=[copy_probe, normalize_probe],
        target_sig=VideoSignature(
            codec="h264",
            width=1920,
            height=1080,
            pix_fmt="yuv420p",
            fps=30.0,
        ),
        copy_indices=[0],
        normalize_indices=[1],
        mismatches=[],
    )
    job = CombineJob(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        inputs=[probe.path for probe in plan.inputs],
        output=tmp_path / "combined.mkv",
        encoder=EncoderChoice.LIBX264,
    )
    progress_events: list[tuple[float, str]] = []
    job.progress.connect(lambda pct, phase: progress_events.append((pct, phase)))

    def fake_run_ffmpeg(*args: object, **kwargs: object) -> RunResult:
        on_progress = kwargs["on_progress"]
        assert callable(on_progress)
        output_path = Path(str(args[1][-1]))
        if output_path == job.output:
            on_progress(ProgressEvent(out_time_sec=20.0))
        else:
            on_progress(ProgressEvent(out_time_sec=5.0))
        return RunResult(argv=[], exit_code=0, duration_sec=0.01, stderr_tail="")

    monkeypatch.setattr("stormfuse.jobs.combine.run_ffmpeg", fake_run_ffmpeg)

    job._run_normalize_then_concat(plan)

    assert len(progress_events) == 2
    assert progress_events[0][0] == pytest.approx(0.1)
    assert progress_events[0][1] == "Normalizing normalize.mp4…"
    assert progress_events[1][0] == pytest.approx(0.6)
    assert progress_events[1][1] == "Concatenating…"


def test_cancelled_normalize_concat_cleans_output_and_temp_dir(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy_probe = _probe(tmp_path / "copy.mkv", duration=30.0)
    normalize_probe = _probe(tmp_path / "normalize.mp4", width=1280, height=720, duration=10.0)
    plan = ConcatPlan(
        strategy=ConcatStrategy.NORMALIZE_THEN_CONCAT,
        inputs=[copy_probe, normalize_probe],
        target_sig=VideoSignature(
            codec="h264",
            width=1920,
            height=1080,
            pix_fmt="yuv420p",
            fps=30.0,
        ),
        copy_indices=[0],
        normalize_indices=[1],
        mismatches=[],
    )
    job = CombineJob(
        ffmpeg_exe=tmp_path / "ffmpeg.exe",
        ffprobe_exe=tmp_path / "ffprobe.exe",
        inputs=[probe.path for probe in plan.inputs],
        output=tmp_path / "combined.mkv",
        encoder=EncoderChoice.LIBX264,
    )
    norm_dir = tmp_path / "stormfuse_norm"

    def fake_mkdtemp(prefix: str) -> str:
        assert prefix == "stormfuse_norm_"
        norm_dir.mkdir()
        return str(norm_dir)

    def fake_run_ffmpeg(*args: object, **kwargs: object) -> RunResult:
        output_path = Path(str(args[1][-1]))
        if output_path == job.output:
            output_path.write_text("partial", encoding="utf-8")
            job.cancel()
            return RunResult(argv=[], exit_code=255, duration_sec=0.01, stderr_tail="")

        output_path.write_text("normalized", encoding="utf-8")
        return RunResult(argv=[], exit_code=0, duration_sec=0.01, stderr_tail="")

    monkeypatch.setattr("stormfuse.jobs.combine.tempfile.mkdtemp", fake_mkdtemp)
    monkeypatch.setattr("stormfuse.jobs.combine.run_ffmpeg", fake_run_ffmpeg)

    job._run_normalize_then_concat(plan)

    assert not job.output.exists()
    assert not norm_dir.exists()
