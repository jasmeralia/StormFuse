# SPDX-License-Identifier: GPL-3.0-or-later
"""NVENC detection and ffmpeg encoder argument builders (§7.4, §5.3)."""

from __future__ import annotations

import logging
import os
import subprocess
from enum import Enum, auto
from pathlib import Path

from stormfuse.ffmpeg._subprocess import run

log = logging.getLogger("ffmpeg.encoders")

_PROBE_TIMEOUT_SEC = 10


class EncoderChoice(Enum):
    NVENC = auto()
    LIBX264 = auto()


def detect_encoder(ffmpeg_exe: Path) -> EncoderChoice:
    """Run the two-step NVENC probe (§5.3) and return the encoder to use."""
    forced_choice = _forced_encoder_choice()
    if forced_choice is not None:
        log.info(
            "Skipping encoder detection due to STORMFUSE_FORCE_ENCODER",
            extra={
                "event": "nvenc.probe_skipped",
                "ctx": {
                    "forced_encoder": _encoder_name(forced_choice),
                    "env_var": "STORMFUSE_FORCE_ENCODER",
                },
            },
        )
        return forced_choice

    return _detect_encoder_impl(ffmpeg_exe)


def _detect_encoder_impl(ffmpeg_exe: Path) -> EncoderChoice:
    _log_hwaccels(ffmpeg_exe)

    # Step 1: check if h264_nvenc appears in -encoders output
    try:
        result = run(
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

    encoder_stdout = _output_text(result.stdout)
    log.debug(
        "NVENC probe encoder listing",
        extra={
            "event": "nvenc.probe",
            "ctx": {
                "step": "encoders",
                "stdout_excerpt": encoder_stdout[:500],
                "returncode": result.returncode,
            },
        },
    )

    if "h264_nvenc" not in encoder_stdout:
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
        test_result = run(
            test_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_PROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        log.info(
            "NVENC test encode timed out",
            extra={
                "event": "nvenc.probe_timeout",
                "ctx": {
                    "result": "libx264_fallback",
                    "timeout_sec": _PROBE_TIMEOUT_SEC,
                    "argv": test_cmd,
                    "stderr_tail": _stderr_tail(getattr(exc, "stderr", "")),
                },
            },
        )
        return EncoderChoice.LIBX264
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

    stderr_tail = _stderr_tail(test_result.stderr)
    log.info(
        "NVENC test encode failed",
        extra={
            "event": "nvenc.probe",
            "ctx": {
                "result": "libx264_fallback",
                "reason": "test encode non-zero exit",
                "returncode": test_result.returncode,
                "stderr_tail": stderr_tail,
            },
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


def _forced_encoder_choice() -> EncoderChoice | None:
    raw_value = os.environ.get("STORMFUSE_FORCE_ENCODER", "").strip().casefold()
    if raw_value == "nvenc":
        return EncoderChoice.NVENC
    if raw_value == "libx264":
        return EncoderChoice.LIBX264
    if raw_value:
        log.warning(
            "Ignoring invalid STORMFUSE_FORCE_ENCODER value",
            extra={
                "event": "nvenc.probe",
                "ctx": {"reason": "invalid override", "override": raw_value},
            },
        )
    return None


def _log_hwaccels(ffmpeg_exe: Path) -> None:
    argv = [str(ffmpeg_exe), "-hide_banner", "-hwaccels"]
    try:
        result = run(
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        log.info(
            "Unable to inspect ffmpeg hwaccels",
            extra={
                "event": "nvenc.hwaccels",
                "ctx": {"error": str(exc)},
            },
        )
        return

    stdout = _output_text(result.stdout)
    stdout_lower = stdout.casefold()
    listed = [line.strip() for line in stdout.splitlines() if line.strip()]
    log.info(
        "ffmpeg hwaccels inspected",
        extra={
            "event": "nvenc.hwaccels",
            "ctx": {
                "returncode": result.returncode,
                "has_cuda": "cuda" in stdout_lower,
                "mentions_nvenc": "nvenc" in stdout_lower,
                "stdout_excerpt": stdout[:500],
                "available": listed[-20:],
            },
        },
    )


def _stderr_tail(stderr: str | bytes | None) -> list[str]:
    if stderr is None:
        return []
    text = _output_text(stderr)
    return text.splitlines()[-20:]


def _encoder_name(choice: EncoderChoice) -> str:
    if choice == EncoderChoice.NVENC:
        return "nvenc"
    return "libx264"


def _output_text(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
