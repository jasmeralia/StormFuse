# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for stormfuse.ffmpeg.encoders (§11.2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from stormfuse.ffmpeg.encoders import (
    EncoderChoice,
    audio_args,
    compressed_video_args,
    detect_encoder,
    normalize_video_args,
)


class TestCompressedVideoArgs:
    def test_nvenc_single_pass(self) -> None:
        args = compressed_video_args(EncoderChoice.NVENC, 8000)
        assert "-c:v" in args
        idx = args.index("-c:v")
        assert args[idx + 1] == "h264_nvenc"
        assert "-b:v" in args
        assert "8000k" in args
        # No multipass when two_pass=False
        assert "-multipass" not in args

    def test_nvenc_two_pass(self) -> None:
        args = compressed_video_args(EncoderChoice.NVENC, 8000, two_pass=True)
        assert "-multipass" in args
        idx = args.index("-multipass")
        assert args[idx + 1] == "fullres"

    def test_x264_single_pass(self) -> None:
        args = compressed_video_args(EncoderChoice.LIBX264, 8000)
        assert "-c:v" in args
        idx = args.index("-c:v")
        assert args[idx + 1] == "libx264"
        assert "-pass" not in args

    def test_x264_pass1(self) -> None:
        args = compressed_video_args(EncoderChoice.LIBX264, 8000, two_pass=True, pass_num=1)
        assert "-pass" in args
        assert "1" in args
        assert "-an" in args  # no audio in pass 1
        assert "-f" in args  # null muxer

    def test_x264_pass2(self) -> None:
        args = compressed_video_args(EncoderChoice.LIBX264, 8000, two_pass=True, pass_num=2)
        assert "-pass" in args
        assert "2" in args
        assert "-an" not in args  # audio re-enabled in pass 2

    def test_maxrate_is_1_5x(self) -> None:
        args = compressed_video_args(EncoderChoice.LIBX264, 10000)
        assert "-maxrate" in args
        idx = args.index("-maxrate")
        assert args[idx + 1] == "15000k"

    def test_bufsize_is_3x(self) -> None:
        args = compressed_video_args(EncoderChoice.LIBX264, 10000)
        assert "-bufsize" in args
        idx = args.index("-bufsize")
        assert args[idx + 1] == "30000k"

    def test_returns_list_of_strings(self) -> None:
        args = compressed_video_args(EncoderChoice.NVENC, 8000)
        assert all(isinstance(a, str) for a in args)


class TestNormalizeVideoArgs:
    def test_nvenc_uses_cq_18(self) -> None:
        args = normalize_video_args(EncoderChoice.NVENC)
        assert "-cq" in args
        idx = args.index("-cq")
        assert args[idx + 1] == "18"

    def test_x264_uses_crf_18(self) -> None:
        args = normalize_video_args(EncoderChoice.LIBX264)
        assert "-crf" in args
        idx = args.index("-crf")
        assert args[idx + 1] == "18"

    def test_returns_list_of_strings(self) -> None:
        assert all(isinstance(a, str) for a in normalize_video_args(EncoderChoice.NVENC))
        assert all(isinstance(a, str) for a in normalize_video_args(EncoderChoice.LIBX264))


class TestAudioArgs:
    def test_contains_required_flags(self) -> None:
        args = audio_args()
        assert "-c:a" in args
        assert "aac" in args
        assert "-b:a" in args
        assert "192k" in args
        assert "-ar" in args
        assert "48000" in args
        assert "-ac" in args
        assert "2" in args

    def test_returns_list_of_strings(self) -> None:
        assert all(isinstance(a, str) for a in audio_args())


class TestDetectEncoder:
    def test_returns_libx264_when_ffmpeg_cannot_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise OSError("ffmpeg missing")

        monkeypatch.setattr("stormfuse.ffmpeg.encoders.run", fake_run)

        assert detect_encoder(tmp_path / "ffmpeg.exe") == EncoderChoice.LIBX264

    def test_returns_libx264_when_nvenc_is_not_listed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def fake_run(
            argv: list[str], *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if argv[-1] == "-hwaccels":
                return subprocess.CompletedProcess(
                    args=argv, returncode=0, stdout="cuda\n", stderr=""
                )
            return subprocess.CompletedProcess(
                args=argv,
                returncode=0,
                stdout="Encoders:\n V..... libx264",
                stderr="",
            )

        monkeypatch.setattr("stormfuse.ffmpeg.encoders.run", fake_run)

        assert detect_encoder(tmp_path / "ffmpeg.exe") == EncoderChoice.LIBX264

    def test_returns_nvenc_when_probe_and_test_encode_succeed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls: list[list[str]] = []

        def fake_run(
            argv: list[str], *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            if argv[-1] == "-hwaccels":
                return subprocess.CompletedProcess(
                    args=argv,
                    returncode=0,
                    stdout="Hardware acceleration methods:\ncuda\n",
                    stderr="",
                )
            if argv[-1] == "-encoders":
                return subprocess.CompletedProcess(
                    args=argv,
                    returncode=0,
                    stdout="Encoders:\n V..... h264_nvenc\n V..... libx264",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=argv,
                returncode=0,
                stdout="",
                stderr="",
            )

        monkeypatch.setattr("stormfuse.ffmpeg.encoders.run", fake_run)

        assert detect_encoder(tmp_path / "ffmpeg.exe") == EncoderChoice.NVENC
        assert calls == [
            [str(tmp_path / "ffmpeg.exe"), "-hide_banner", "-hwaccels"],
            [str(tmp_path / "ffmpeg.exe"), "-hide_banner", "-encoders"],
            [
                str(tmp_path / "ffmpeg.exe"),
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:d=0.05",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
        ]

    def test_returns_libx264_when_test_encode_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls = 0

        def fake_run(
            argv: list[str], *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal calls
            calls += 1
            if calls == 1:
                return subprocess.CompletedProcess(
                    args=argv,
                    returncode=0,
                    stdout="Hardware acceleration methods:\ncuda\n",
                    stderr="",
                )
            if calls == 2:
                return subprocess.CompletedProcess(
                    args=argv,
                    returncode=0,
                    stdout="Encoders:\n V..... h264_nvenc\n V..... libx264",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=argv,
                returncode=1,
                stdout="",
                stderr="NVENC unavailable",
            )

        monkeypatch.setattr("stormfuse.ffmpeg.encoders.run", fake_run)

        assert detect_encoder(tmp_path / "ffmpeg.exe") == EncoderChoice.LIBX264

    def test_respects_force_encoder_override(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("STORMFUSE_FORCE_ENCODER", "nvenc")
        monkeypatch.setattr(
            "stormfuse.ffmpeg.encoders.run",
            lambda *_args, **_kwargs: pytest.fail("detect_encoder should skip probes"),
        )

        assert detect_encoder(tmp_path / "ffmpeg.exe") == EncoderChoice.NVENC

        monkeypatch.setenv("STORMFUSE_FORCE_ENCODER", "libx264")
        assert detect_encoder(tmp_path / "ffmpeg.exe") == EncoderChoice.LIBX264
        monkeypatch.delenv("STORMFUSE_FORCE_ENCODER", raising=False)
