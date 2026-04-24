# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for stormfuse.ffmpeg.bitrate (§11.2)."""

from __future__ import annotations

import math

from stormfuse.ffmpeg.bitrate import AUDIO_BITRATE_BPS, OVERHEAD_FRACTION, compute_bitrate


class TestComputeBitrate:
    def test_standard_case(self) -> None:
        # 9.5 GB, 1-hour video
        result = compute_bitrate(9.5, 3600.0)
        assert result.feasible
        assert result.video_bitrate_k > 0
        assert result.maxrate_k == math.floor(result.video_bitrate_k * 1.5)
        assert result.bufsize_k == math.floor(result.video_bitrate_k * 3.0)

    def test_known_value(self) -> None:
        # 9.5 GB, 3600 s
        target_bytes = 9.5 * 1024**3
        audio_bits = AUDIO_BITRATE_BPS * 3600
        video_bits = target_bytes * 8 * (1 - OVERHEAD_FRACTION) - audio_bits
        expected_k = math.floor(video_bits / 3600 / 1000)

        result = compute_bitrate(9.5, 3600.0)
        assert result.video_bitrate_k == expected_k

    def test_target_too_small(self) -> None:
        # 0.01 GB for a 1-hour video — audio alone consumes more than target
        result = compute_bitrate(0.01, 3600.0)
        assert not result.feasible
        assert result.video_bitrate_k == 0
        assert result.reason != ""

    def test_zero_duration(self) -> None:
        result = compute_bitrate(9.5, 0.0)
        assert not result.feasible
        assert "zero" in result.reason.lower() or "duration" in result.reason.lower()

    def test_negative_duration(self) -> None:
        result = compute_bitrate(9.5, -1.0)
        assert not result.feasible

    def test_small_target_large_file(self) -> None:
        # 0.01 GB, 1 hour — audio fills almost all available bits
        result = compute_bitrate(0.01, 3600.0)
        assert not result.feasible

    def test_short_clip_large_target(self) -> None:
        # 9.5 GB, 60-second clip → very high bitrate
        result = compute_bitrate(9.5, 60.0)
        assert result.feasible
        assert result.video_bitrate_k > 100_000  # well over 100 Mbps

    def test_maxrate_is_1_5x(self) -> None:
        result = compute_bitrate(9.5, 3600.0)
        assert result.feasible
        assert result.maxrate_k == math.floor(result.video_bitrate_k * 1.5)

    def test_bufsize_is_3x(self) -> None:
        result = compute_bitrate(9.5, 3600.0)
        assert result.feasible
        assert result.bufsize_k == math.floor(result.video_bitrate_k * 3.0)

    def test_reason_empty_when_feasible(self) -> None:
        result = compute_bitrate(9.5, 3600.0)
        assert result.feasible
        assert result.reason == ""

    def test_reason_populated_when_infeasible(self) -> None:
        result = compute_bitrate(0.01, 3600.0)
        assert not result.feasible
        assert len(result.reason) > 0
