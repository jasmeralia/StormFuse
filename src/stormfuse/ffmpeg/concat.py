# SPDX-License-Identifier: GPL-3.0-or-later
"""Concat strategy decision and plan (§7.6, §5.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from stormfuse.ffmpeg.probe import FileProbe
from stormfuse.ffmpeg.signatures import (
    AudioSignature,
    VideoSignature,
    audio_signature,
    container_family,
    signatures_match,
)


class ConcatStrategy(Enum):
    STREAM_COPY = auto()
    NORMALIZE_THEN_CONCAT = auto()


@dataclass
class MismatchDetail:
    input_index: int
    path: Path
    fields: list[str]  # human-readable mismatch descriptions vs normalize target


@dataclass
class ConcatPlan:
    strategy: ConcatStrategy
    inputs: list[FileProbe]
    target_sig: VideoSignature | None  # only set for NORMALIZE_THEN_CONCAT
    copy_indices: list[int]  # indices that can remain on stream-copy path
    normalize_indices: list[int]  # indices that need re-encoding
    mismatches: list[MismatchDetail]  # populated for NORMALIZE_THEN_CONCAT

    def to_log_ctx(self) -> dict[str, object]:
        """Serializable dict for structured logging."""
        copy_index_set = set(self.copy_indices)
        return {
            "strategy": self.strategy.name,
            "input_count": len(self.inputs),
            "copy_count": len(self.copy_indices),
            "copy_indices": self.copy_indices,
            "normalize_count": len(self.normalize_indices),
            "normalize_indices": self.normalize_indices,
            "target_sig": (
                {
                    "codec": self.target_sig.codec,
                    "width": self.target_sig.width,
                    "height": self.target_sig.height,
                    "pix_fmt": self.target_sig.pix_fmt,
                    "fps": self.target_sig.fps,
                }
                if self.target_sig
                else None
            ),
            "inputs": [
                {
                    "index": index,
                    "path": str(probe.path),
                    "action": "copy" if index in copy_index_set else "normalize",
                }
                for index, probe in enumerate(self.inputs)
            ],
            "mismatches": [
                {"index": m.input_index, "path": str(m.path), "fields": m.fields}
                for m in self.mismatches
            ],
        }


_NORMALIZED_AUDIO_SIG = AudioSignature(codec="aac", sample_rate=48000, channels=2)


def _pick_target(probes: list[FileProbe]) -> VideoSignature | None:
    """Pick the normalize target: largest pixel count, tiebreak by highest fps."""
    best: tuple[int, float, FileProbe] | None = None
    for probe in probes:
        video = probe.video
        if video is None:
            continue
        pixels = video.width * video.height
        best_pixels = -1 if best is None else best[0]
        best_fps = -1.0 if best is None else best[1]
        if best is None or (pixels, video.fps) > (best_pixels, best_fps):
            best = (pixels, video.fps, probe)

    if best is None:
        return None

    video = best[2].video
    assert video is not None
    return VideoSignature(
        codec="h264",
        width=video.width,
        height=video.height,
        pix_fmt="yuv420p",
        fps=video.fps,
    )


def _copy_eligible(
    probe: FileProbe,
    target_sig: VideoSignature,
    *,
    fps_tolerance: float,
) -> bool:
    """Return True if *probe* already matches the normalize output signature."""
    video = probe.video
    audio = audio_signature(probe)
    if video is None or audio is None:
        return False
    return (
        container_family(probe) == "matroska"
        and video.codec == target_sig.codec
        and video.width == target_sig.width
        and video.height == target_sig.height
        and video.pix_fmt == target_sig.pix_fmt
        and abs(video.fps - target_sig.fps) <= fps_tolerance
        and audio == _NORMALIZED_AUDIO_SIG
    )


def _describe_target_mismatch(
    probe: FileProbe,
    target_sig: VideoSignature,
    *,
    fps_tolerance: float,
) -> list[str]:
    """Return field-level reasons *probe* cannot stay on the copy path."""
    mismatches: list[str] = []
    video = probe.video
    audio = audio_signature(probe)
    container = container_family(probe)

    if container != "matroska":
        mismatches.append(f"container: {container} vs matroska")

    if video is None:
        mismatches.append("missing video stream")
    else:
        if video.codec != target_sig.codec:
            mismatches.append(f"video codec: {video.codec} vs {target_sig.codec}")
        if video.width != target_sig.width or video.height != target_sig.height:
            mismatches.append(
                "resolution: "
                f"{video.width}x{video.height} vs {target_sig.width}x{target_sig.height}"
            )
        if video.pix_fmt != target_sig.pix_fmt:
            mismatches.append(f"pixel format: {video.pix_fmt} vs {target_sig.pix_fmt}")
        if abs(video.fps - target_sig.fps) > fps_tolerance:
            mismatches.append(f"frame rate: {video.fps:.3f} vs {target_sig.fps:.3f}")

    if audio is None:
        mismatches.append("missing audio stream")
    else:
        if audio.codec != _NORMALIZED_AUDIO_SIG.codec:
            mismatches.append(f"audio codec: {audio.codec} vs {_NORMALIZED_AUDIO_SIG.codec}")
        if audio.sample_rate != _NORMALIZED_AUDIO_SIG.sample_rate:
            mismatches.append(
                f"sample rate: {audio.sample_rate} vs {_NORMALIZED_AUDIO_SIG.sample_rate}"
            )
        if audio.channels != _NORMALIZED_AUDIO_SIG.channels:
            mismatches.append(f"channels: {audio.channels} vs {_NORMALIZED_AUDIO_SIG.channels}")

    return mismatches


def make_concat_plan(probes: list[FileProbe], *, fps_tolerance: float = 0.01) -> ConcatPlan:
    """Decide the concat strategy for *probes* and return a ConcatPlan."""
    if not probes:
        raise ValueError("No inputs provided to make_concat_plan")

    reference = probes[0]
    all_match = all(
        signatures_match(reference, probe, fps_tolerance=fps_tolerance) for probe in probes[1:]
    )
    if all_match:
        return ConcatPlan(
            strategy=ConcatStrategy.STREAM_COPY,
            inputs=probes,
            target_sig=None,
            copy_indices=list(range(len(probes))),
            normalize_indices=[],
            mismatches=[],
        )

    target_sig = _pick_target(probes)
    if target_sig is None:
        raise ValueError("Cannot normalize concat inputs without a video stream")

    copy_indices: list[int] = []
    normalize_indices: list[int] = []
    mismatches: list[MismatchDetail] = []
    for index, probe in enumerate(probes):
        if _copy_eligible(probe, target_sig, fps_tolerance=fps_tolerance):
            copy_indices.append(index)
            continue

        mismatches.append(
            MismatchDetail(
                input_index=index,
                path=probe.path,
                fields=_describe_target_mismatch(
                    probe,
                    target_sig,
                    fps_tolerance=fps_tolerance,
                ),
            )
        )
        normalize_indices.append(index)

    return ConcatPlan(
        strategy=ConcatStrategy.NORMALIZE_THEN_CONCAT,
        inputs=probes,
        target_sig=target_sig,
        copy_indices=copy_indices,
        normalize_indices=normalize_indices,
        mismatches=mismatches,
    )
