# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows-only functional coverage for real ffmpeg jobs (§11.3)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ffmpeg.probe import probe
from stormfuse.jobs.base import JobError, JobResult
from stormfuse.jobs.combine import CombineJob
from stormfuse.jobs.compress import CompressJob


def _run_job(job: CombineJob | CompressJob) -> tuple[JobResult | None, JobError | None]:
    done: list[JobResult] = []
    failed: list[JobError] = []
    job.done.connect(done.append)
    job.failed.connect(failed.append)
    job.run()
    return (done[0] if done else None, failed[0] if failed else None)


@pytest.mark.windows_only
def test_combine_stream_copy_end_to_end(
    bundled_ffmpeg: Path,
    bundled_ffprobe: Path,
    generated_media: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    output = tmp_path / "combined-stream-copy.mkv"
    job = CombineJob(
        ffmpeg_exe=bundled_ffmpeg,
        ffprobe_exe=bundled_ffprobe,
        inputs=[generated_media["combine_stream_a"], generated_media["combine_stream_b"]],
        output=output,
        encoder=EncoderChoice.LIBX264,
    )

    with caplog.at_level(logging.INFO):
        result, error = _run_job(job)

    assert error is None
    assert result is not None
    assert output.exists()

    output_probe = probe(bundled_ffprobe, output)
    assert output_probe.video is not None
    assert output_probe.audio is not None
    assert output_probe.video.width == 640
    assert output_probe.video.height == 360
    assert output_probe.video.codec == "h264"
    assert output_probe.audio.codec == "aac"

    decision = next(
        record for record in caplog.records if getattr(record, "event", None) == "concat.decision"
    )
    assert decision.ctx["strategy"] == "STREAM_COPY"


@pytest.mark.windows_only
def test_combine_normalize_end_to_end(
    bundled_ffmpeg: Path,
    bundled_ffprobe: Path,
    generated_media: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    output = tmp_path / "combined-normalized.mkv"
    job = CombineJob(
        ffmpeg_exe=bundled_ffmpeg,
        ffprobe_exe=bundled_ffprobe,
        inputs=[
            generated_media["combine_normalize_small"],
            generated_media["combine_normalize_large"],
        ],
        output=output,
        encoder=EncoderChoice.LIBX264,
    )

    with caplog.at_level(logging.INFO):
        result, error = _run_job(job)

    assert error is None
    assert result is not None
    assert output.exists()

    output_probe = probe(bundled_ffprobe, output)
    assert output_probe.video is not None
    assert output_probe.audio is not None
    assert output_probe.video.width == 640
    assert output_probe.video.height == 360
    assert output_probe.video.pix_fmt == "yuv420p"
    assert output_probe.video.codec == "h264"
    assert output_probe.audio.codec == "aac"

    decision = next(
        record for record in caplog.records if getattr(record, "event", None) == "concat.decision"
    )
    assert decision.ctx["strategy"] == "NORMALIZE_THEN_CONCAT"
    assert decision.ctx["normalize_count"] == 1


@pytest.mark.windows_only
def test_compress_libx264_single_pass_end_to_end(
    bundled_ffmpeg: Path,
    bundled_ffprobe: Path,
    generated_media: dict[str, Path],
    tmp_path: Path,
) -> None:
    output = tmp_path / "compressed-single-pass.mp4"
    job = CompressJob(
        ffmpeg_exe=bundled_ffmpeg,
        ffprobe_exe=bundled_ffprobe,
        input_path=generated_media["compress_input"],
        output_path=output,
        target_gb=1.0,
        encoder=EncoderChoice.LIBX264,
        two_pass=False,
    )

    result, error = _run_job(job)

    assert error is None
    assert result is not None
    assert output.exists()
    assert output.stat().st_size < 1024**3

    output_probe = probe(bundled_ffprobe, output)
    assert output_probe.video is not None
    assert output_probe.audio is not None
    assert output_probe.video.codec == "h264"
    assert output_probe.audio.codec == "aac"


@pytest.mark.windows_only
def test_compress_libx264_two_pass_end_to_end(
    bundled_ffmpeg: Path,
    bundled_ffprobe: Path,
    generated_media: dict[str, Path],
    tmp_path: Path,
) -> None:
    output = tmp_path / "compressed-two-pass.mp4"
    job = CompressJob(
        ffmpeg_exe=bundled_ffmpeg,
        ffprobe_exe=bundled_ffprobe,
        input_path=generated_media["compress_input"],
        output_path=output,
        target_gb=1.0,
        encoder=EncoderChoice.LIBX264,
        two_pass=True,
    )

    result, error = _run_job(job)

    assert error is None
    assert result is not None
    assert output.exists()

    output_probe = probe(bundled_ffprobe, output)
    assert output_probe.video is not None
    assert output_probe.audio is not None
    assert output_probe.video.codec == "h264"
    assert output_probe.audio.codec == "aac"


@pytest.mark.windows_only
def test_cancelled_job_removes_partial_output(
    bundled_ffmpeg: Path,
    bundled_ffprobe: Path,
    generated_media: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    output = tmp_path / "cancelled.mp4"
    job = CompressJob(
        ffmpeg_exe=bundled_ffmpeg,
        ffprobe_exe=bundled_ffprobe,
        input_path=generated_media["cancel_input"],
        output_path=output,
        target_gb=1.0,
        encoder=EncoderChoice.LIBX264,
        two_pass=False,
    )

    done: list[JobResult] = []
    failed: list[JobError] = []
    job.done.connect(done.append)
    job.failed.connect(failed.append)

    cancel_timer = threading.Timer(0.5, job.cancel)
    try:
        with caplog.at_level(logging.INFO):
            cancel_timer.start()
            job.run()
    finally:
        cancel_timer.cancel()
        cancel_timer.join()

    assert job.is_cancelled
    assert done == []
    assert failed == []
    assert not output.exists()
    assert any(getattr(record, "event", None) == "job.cancel" for record in caplog.records)
    assert any(getattr(record, "event", None) == "ffmpeg.cancel" for record in caplog.records)


@pytest.mark.windows_only
@pytest.mark.requires_nvenc
def test_compress_nvenc_single_pass_end_to_end(
    bundled_ffmpeg: Path,
    bundled_ffprobe: Path,
    generated_media: dict[str, Path],
    tmp_path: Path,
) -> None:
    output = tmp_path / "compressed-nvenc.mp4"
    job = CompressJob(
        ffmpeg_exe=bundled_ffmpeg,
        ffprobe_exe=bundled_ffprobe,
        input_path=generated_media["compress_input"],
        output_path=output,
        target_gb=1.0,
        encoder=EncoderChoice.NVENC,
        two_pass=False,
    )

    result, error = _run_job(job)

    assert error is None
    assert result is not None
    assert output.exists()

    output_probe = probe(bundled_ffprobe, output)
    assert output_probe.video is not None
    assert output_probe.audio is not None
    assert output_probe.video.codec == "h264"
    assert output_probe.audio.codec == "aac"
