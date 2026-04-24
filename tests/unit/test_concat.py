# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for stormfuse.ffmpeg.concat (§11.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stormfuse.ffmpeg.concat import ConcatStrategy, make_concat_plan
from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream


def _probe(
    name: str = "a.mkv",
    vcodec: str = "h264",
    width: int = 1920,
    height: int = 1080,
    pix_fmt: str = "yuv420p",
    fps: float = 30.0,
    acodec: str = "aac",
    sample_rate: int = 48000,
    channels: int = 2,
    duration: float = 60.0,
) -> FileProbe:
    return FileProbe(
        path=Path(name),
        video=VideoStream(codec=vcodec, width=width, height=height, pix_fmt=pix_fmt, fps=fps),
        audio=AudioStream(codec=acodec, sample_rate=sample_rate, channels=channels),
        duration_sec=duration,
        size_bytes=0,
        raw={},
    )


class TestMakeConcatPlan:
    def test_raises_on_empty(self) -> None:
        with pytest.raises(ValueError):
            make_concat_plan([])

    def test_single_input_stream_copy(self) -> None:
        plan = make_concat_plan([_probe()])
        assert plan.strategy == ConcatStrategy.STREAM_COPY
        assert plan.copy_indices == [0]
        assert plan.normalize_indices == []

    def test_identical_inputs_stream_copy(self) -> None:
        probes = [_probe(f"{i}.mkv") for i in range(3)]
        plan = make_concat_plan(probes)
        assert plan.strategy == ConcatStrategy.STREAM_COPY
        assert plan.copy_indices == [0, 1, 2]
        assert len(plan.normalize_indices) == 0
        assert len(plan.mismatches) == 0

    def test_resolution_mismatch_normalizes_only_non_matching_inputs(self) -> None:
        a = _probe("a.mkv", width=1920, height=1080)
        b = _probe("b.mkv", width=1280, height=720)
        plan = make_concat_plan([a, b])
        assert plan.strategy == ConcatStrategy.NORMALIZE_THEN_CONCAT
        assert plan.copy_indices == [0]
        assert plan.normalize_indices == [1]

    def test_fps_mismatch_normalize(self) -> None:
        a = _probe("a.mkv", fps=60.0)
        b = _probe("b.mkv", fps=30.0)
        plan = make_concat_plan([a, b])
        assert plan.strategy == ConcatStrategy.NORMALIZE_THEN_CONCAT
        assert plan.copy_indices == [0]
        assert plan.normalize_indices == [1]

    def test_codec_mismatch_normalize(self) -> None:
        a = _probe("a.mkv", vcodec="h264")
        b = _probe("b.mkv", vcodec="hevc")
        plan = make_concat_plan([a, b])
        assert plan.strategy == ConcatStrategy.NORMALIZE_THEN_CONCAT
        assert plan.copy_indices == [0]
        assert plan.normalize_indices == [1]

    def test_target_sig_uses_largest_dimensions_with_normalize_output_format(self) -> None:
        small = _probe("small.mkv", width=1280, height=720)
        large = _probe("large.mkv", width=1920, height=1080, vcodec="hevc", pix_fmt="yuv444p")
        plan = make_concat_plan([small, large])
        if plan.strategy == ConcatStrategy.NORMALIZE_THEN_CONCAT:
            assert plan.target_sig is not None
            assert plan.target_sig.codec == "h264"
            assert plan.target_sig.width == 1920
            assert plan.target_sig.height == 1080
            assert plan.target_sig.pix_fmt == "yuv420p"
            assert plan.normalize_indices == [0, 1]

    def test_target_sig_none_for_stream_copy(self) -> None:
        probes = [_probe(), _probe("b.mkv")]
        plan = make_concat_plan(probes)
        assert plan.strategy == ConcatStrategy.STREAM_COPY
        assert plan.target_sig is None

    def test_larger_input_stays_copy_eligible_only_if_it_matches_normalize_output(self) -> None:
        smaller = _probe("small.mkv", width=1280, height=720)
        larger = _probe("large.mkv", width=1920, height=1080)
        plan = make_concat_plan([smaller, larger])
        assert plan.strategy == ConcatStrategy.NORMALIZE_THEN_CONCAT
        assert plan.copy_indices == [1]
        assert plan.normalize_indices == [0]

    def test_log_ctx_serializable(self) -> None:
        a = _probe("a.mkv", width=1920)
        b = _probe("b.mkv", width=1280)
        plan = make_concat_plan([a, b])
        ctx = plan.to_log_ctx()
        json.dumps(ctx)  # must not raise
        assert ctx["copy_indices"] == [0]
        assert ctx["normalize_indices"] == [1]
        assert ctx["inputs"] == [
            {"index": 0, "path": "a.mkv", "action": "copy"},
            {"index": 1, "path": "b.mkv", "action": "normalize"},
        ]

    def test_mismatches_populated_for_normalize(self) -> None:
        a = _probe("a.mkv", vcodec="h264")
        b = _probe("b.mkv", vcodec="hevc")
        plan = make_concat_plan([a, b])
        assert plan.strategy == ConcatStrategy.NORMALIZE_THEN_CONCAT
        assert len(plan.mismatches) > 0
        assert any("codec" in f.lower() for m in plan.mismatches for f in m.fields)

    def test_audio_mismatch_forces_normalize_even_when_video_matches_target(self) -> None:
        copy_eligible = _probe("a.mkv", width=1920, height=1080)
        needs_audio_normalize = _probe("b.mkv", width=1280, height=720, acodec="ac3")
        plan = make_concat_plan([needs_audio_normalize, copy_eligible])
        assert plan.strategy == ConcatStrategy.NORMALIZE_THEN_CONCAT
        assert plan.copy_indices == [1]
        assert plan.normalize_indices == [0]
        mismatch_fields = {field for mismatch in plan.mismatches for field in mismatch.fields}
        assert any("audio codec" in field.lower() for field in mismatch_fields)
