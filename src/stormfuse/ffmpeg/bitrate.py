# SPDX-License-Identifier: GPL-3.0-or-later
"""Bitrate math for the compress workflow (§5.2, §7.5).

All functions are pure — no I/O, no subprocess. Fully unit-testable on Linux.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

OVERHEAD_FRACTION: float = 0.01
AUDIO_BITRATE_BPS: int = 192_000


@dataclass(frozen=True)
class BitrateResult:
    video_bitrate_k: int  # kbps, for -b:v
    maxrate_k: int  # kbps, for -maxrate
    bufsize_k: int  # kbps, for -bufsize
    feasible: bool  # False when target is too small for audio alone
    reason: str  # human-readable explanation if not feasible


def compute_bitrate(target_gb: float, duration_sec: float) -> BitrateResult:
    """Compute video bitrate parameters for the given size target and duration.

    Returns a BitrateResult. If feasible is False, video_bitrate_k is 0
    and Run should be disabled.
    """
    if duration_sec <= 0:
        return BitrateResult(0, 0, 0, False, "Duration is zero or unknown")

    target_bytes = target_gb * 1024**3
    audio_bits_total = AUDIO_BITRATE_BPS * duration_sec
    video_bits_total = target_bytes * 8 * (1 - OVERHEAD_FRACTION) - audio_bits_total

    if video_bits_total <= 0:
        return BitrateResult(
            0,
            0,
            0,
            False,
            f"Target {target_gb:.1f} GB is too small for {duration_sec / 60:.1f} min of audio at"
            f" {AUDIO_BITRATE_BPS // 1000} kbps",
        )

    video_bitrate_k = math.floor(video_bits_total / duration_sec / 1000)
    if video_bitrate_k <= 0:
        return BitrateResult(
            0,
            0,
            0,
            False,
            "Computed video bitrate is zero — target too small for this duration",
        )

    maxrate_k = math.floor(video_bitrate_k * 1.5)
    bufsize_k = math.floor(video_bitrate_k * 3.0)

    return BitrateResult(
        video_bitrate_k=video_bitrate_k,
        maxrate_k=maxrate_k,
        bufsize_k=bufsize_k,
        feasible=True,
        reason="",
    )
