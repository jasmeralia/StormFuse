# SPDX-License-Identifier: GPL-3.0-or-later
"""NVENC detection and ffmpeg encoder argument builders (§7.4, §5.3)."""

from __future__ import annotations

import logging
import subprocess
from enum import Enum, auto
from pathlib import Path

log = logging.getLogger("ffmpeg.encoders")


class EncoderChoice(Enum):
    NVENC = auto()
    LIBX264 = auto()


def detect_encoder(ffmpeg_exe: Path) -> EncoderChoice:
    """Run the two-step NVENC probe (§5.3) and return the encoder to use."""
    # Step 1: check if h264_nvenc appears in -encoders output
    try:
        result = subprocess.run(
            [str(ffmpeg_exe), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        log.info(
            "NVENC probe failed (cannot run ffmpeg)",
            extra={
                "event": "nvenc.probe",
                "ctx": {"result": "libx264_fallback", "reason": str(exc)},
            },
        )
        return EncoderChoice.LIBX264

    if "h264_nvenc" not in result.stdout:
        log.info(
            "h264_nvenc not listed in ffmpeg encoders",
            extra={
                "event": "nvenc.probe",
                "ctx": {"result": "libx264_fallback", "reason": "h264_nvenc not in -encoders"},
            },
        )
        return EncoderChoice.LIBX264

    # Step 2: try a tiny 1-frame test encode
    test_cmd = [
        str(ffmpeg_exe),
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
    ]
    try:
        test_result = subprocess.run(
            test_cmd,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        log.info(
            "NVENC test encode failed (OS error)",
            extra={
                "event": "nvenc.probe",
                "ctx": {"result": "libx264_fallback", "reason": str(exc)},
            },
        )
        return EncoderChoice.LIBX264

    if test_result.returncode == 0:
        log.info(
            "NVENC available",
            extra={"event": "nvenc.probe", "ctx": {"result": "nvenc"}},
        )
        return EncoderChoice.NVENC

    stderr_tail = test_result.stderr[-1000:].decode(errors="replace")
    log.info(
        "NVENC test encode failed",
        extra={
            "event": "nvenc.probe",
            "ctx": {
                "result": "libx264_fallback",
                "reason": "test encode non-zero exit",
                "returncode": test_result.returncode,
            },
            "ctx.stderr_tail": stderr_tail,
        },
    )
    return EncoderChoice.LIBX264


def compressed_video_args(
    choice: EncoderChoice,
    bitrate_k: int,
    *,
    two_pass: bool = False,
    pass_num: int = 1,
) -> list[str]:
    """Build video encoder args for the compress workflow (§5.2, §7.4)."""
    maxrate_k = int(bitrate_k * 1.5)
    bufsize_k = int(bitrate_k * 3.0)

    if choice == EncoderChoice.NVENC:
        args = [
            "-c:v",
            "h264_nvenc",
            "-b:v",
            f"{bitrate_k}k",
            "-maxrate",
            f"{maxrate_k}k",
            "-bufsize",
            f"{bufsize_k}k",
            "-preset",
            "p5",
            "-rc",
            "vbr",
            "-spatial-aq",
            "1",
            "-temporal-aq",
            "1",
        ]
        if two_pass:
            args += ["-multipass", "fullres"]
        return args

    # libx264
    if two_pass and pass_num == 1:
        return [
            "-c:v",
            "libx264",
            "-b:v",
            f"{bitrate_k}k",
            "-maxrate",
            f"{maxrate_k}k",
            "-bufsize",
            f"{bufsize_k}k",
            "-preset",
            "slow",
            "-pass",
            "1",
            "-an",
            "-f",
            "null",
        ]
    if two_pass and pass_num == 2:
        return [
            "-c:v",
            "libx264",
            "-b:v",
            f"{bitrate_k}k",
            "-maxrate",
            f"{maxrate_k}k",
            "-bufsize",
            f"{bufsize_k}k",
            "-preset",
            "slow",
            "-pass",
            "2",
        ]
    return [
        "-c:v",
        "libx264",
        "-b:v",
        f"{bitrate_k}k",
        "-maxrate",
        f"{maxrate_k}k",
        "-bufsize",
        f"{bufsize_k}k",
        "-preset",
        "slow",
    ]


def normalize_video_args(choice: EncoderChoice) -> list[str]:
    """Build video encoder args for normalize intermediates (CQ/CRF 18)."""
    if choice == EncoderChoice.NVENC:
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p5",
            "-rc",
            "vbr",
            "-cq",
            "18",
            "-b:v",
            "0",
            "-spatial-aq",
            "1",
            "-temporal-aq",
            "1",
        ]
    return [
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
    ]


def audio_args() -> list[str]:
    """Standard audio args: AAC 192k stereo 48 kHz (§5.2)."""
    return ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
