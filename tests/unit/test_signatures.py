# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for stormfuse.ffmpeg.signatures (§11.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ffmpeg.signatures import (
    AudioSignature,
    VideoSignature,
    describe_mismatch,
    signatures_match,
)


def _make_probe(
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
        path=Path("fake.mkv"),
        video=VideoStream(codec=vcodec, width=width, height=height, pix_fmt=pix_fmt, fps=fps),
        audio=AudioStream(codec=acodec, sample_rate=sample_rate, channels=channels),
        duration_sec=duration,
        size_bytes=0,
        raw={},
    )


class TestVideoSignature:
    def test_frozen(self) -> None:
        sig = VideoSignature("h264", 1920, 1080, "yuv420p", 30.0)
        with pytest.raises((AttributeError, TypeError)):
            sig.codec = "hevc"  # type: ignore[misc]

    def test_hashable(self) -> None:
        sig = VideoSignature("h264", 1920, 1080, "yuv420p", 30.0)
        assert hash(sig) is not None
        s: set[VideoSignature] = {sig}
        assert sig in s

    def test_equality(self) -> None:
        a = VideoSignature("h264", 1920, 1080, "yuv420p", 30.0)
        b = VideoSignature("h264", 1920, 1080, "yuv420p", 30.0)
        assert a == b


class TestAudioSignature:
    def test_frozen(self) -> None:
        sig = AudioSignature("aac", 48000, 2)
        with pytest.raises((AttributeError, TypeError)):
            sig.codec = "opus"  # type: ignore[misc]

    def test_hashable(self) -> None:
        sig = AudioSignature("aac", 48000, 2)
        assert hash(sig) is not None


class TestSignaturesMatch:
    def test_identical_probes_match(self) -> None:
        a = _make_probe()
        b = _make_probe()
        assert signatures_match(a, b)

    def test_video_codec_mismatch(self) -> None:
        a = _make_probe(vcodec="h264")
        b = _make_probe(vcodec="hevc")
        assert not signatures_match(a, b)

    def test_width_mismatch(self) -> None:
        a = _make_probe(width=1920)
        b = _make_probe(width=1280)
        assert not signatures_match(a, b)

    def test_height_mismatch(self) -> None:
        a = _make_probe(height=1080)
        b = _make_probe(height=720)
        assert not signatures_match(a, b)

    def test_pix_fmt_mismatch(self) -> None:
        a = _make_probe(pix_fmt="yuv420p")
        b = _make_probe(pix_fmt="yuv444p")
        assert not signatures_match(a, b)

    def test_fps_within_tolerance(self) -> None:
        a = _make_probe(fps=30.0)
        b = _make_probe(fps=30.005)
        assert signatures_match(a, b)

    def test_fps_outside_tolerance(self) -> None:
        a = _make_probe(fps=30.0)
        b = _make_probe(fps=29.97)
        assert not signatures_match(a, b)

    def test_fps_tolerance_parameter(self) -> None:
        a = _make_probe(fps=30.0)
        b = _make_probe(fps=29.97)
        assert signatures_match(a, b, fps_tolerance=0.1)

    def test_audio_codec_mismatch(self) -> None:
        a = _make_probe(acodec="aac")
        b = _make_probe(acodec="opus")
        assert not signatures_match(a, b)

    def test_audio_sample_rate_mismatch(self) -> None:
        a = _make_probe(sample_rate=48000)
        b = _make_probe(sample_rate=44100)
        assert not signatures_match(a, b)

    def test_audio_channels_mismatch(self) -> None:
        a = _make_probe(channels=2)
        b = _make_probe(channels=1)
        assert not signatures_match(a, b)


class TestDescribeMismatch:
    def test_no_mismatch_returns_empty(self) -> None:
        a = _make_probe()
        b = _make_probe()
        assert describe_mismatch(a, b) == []

    def test_codec_mismatch_described(self) -> None:
        a = _make_probe(vcodec="h264")
        b = _make_probe(vcodec="hevc")
        msgs = describe_mismatch(a, b)
        assert any("codec" in m.lower() for m in msgs)

    def test_resolution_mismatch_described(self) -> None:
        a = _make_probe(width=1920, height=1080)
        b = _make_probe(width=1280, height=720)
        msgs = describe_mismatch(a, b)
        assert any("resolution" in m.lower() or "x" in m for m in msgs)

    def test_fps_mismatch_described(self) -> None:
        a = _make_probe(fps=60.0)
        b = _make_probe(fps=30.0)
        msgs = describe_mismatch(a, b)
        assert any("frame rate" in m.lower() or "fps" in m.lower() for m in msgs)

    def test_multiple_mismatches(self) -> None:
        a = _make_probe(vcodec="h264", fps=60.0)
        b = _make_probe(vcodec="hevc", fps=30.0)
        msgs = describe_mismatch(a, b)
        assert len(msgs) >= 2
