# SPDX-License-Identifier: GPL-3.0-or-later
"""Stream signature matching for stream-copy eligibility (§7.3, §5.1)."""

from __future__ import annotations

from dataclasses import dataclass

from stormfuse.ffmpeg.probe import FileProbe


@dataclass(frozen=True)
class VideoSignature:
    codec: str
    width: int
    height: int
    pix_fmt: str
    fps: float

    def __hash__(self) -> int:
        return hash((self.codec, self.width, self.height, self.pix_fmt, round(self.fps, 4)))


@dataclass(frozen=True)
class AudioSignature:
    codec: str
    sample_rate: int
    channels: int


def video_signature(probe: FileProbe) -> VideoSignature | None:
    if probe.video is None:
        return None
    return VideoSignature(
        codec=probe.video.codec,
        width=probe.video.width,
        height=probe.video.height,
        pix_fmt=probe.video.pix_fmt,
        fps=probe.video.fps,
    )


def audio_signature(probe: FileProbe) -> AudioSignature | None:
    if probe.audio is None:
        return None
    return AudioSignature(
        codec=probe.audio.codec,
        sample_rate=probe.audio.sample_rate,
        channels=probe.audio.channels,
    )


def container_family(probe: FileProbe) -> str:
    """Return the broad container family used for concat compatibility."""
    format_name = str(probe.raw.get("format", {}).get("format_name", "")).casefold()
    if any(part in {"matroska", "webm"} for part in format_name.split(",")):
        return "matroska"
    if any(part in {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"} for part in format_name.split(",")):
        return "mp4"

    suffix = probe.path.suffix.casefold()
    if suffix in {".mkv", ".webm"}:
        return "matroska"
    if suffix in {".mp4", ".m4v", ".mov"}:
        return "mp4"
    return suffix.removeprefix(".") or "unknown"


def signatures_match(a: FileProbe, b: FileProbe, *, fps_tolerance: float = 0.01) -> bool:
    """Return True if *a* and *b* have compatible streams for stream-copy concat."""
    if container_family(a) != container_family(b):
        return False

    av = a.video
    bv = b.video
    if av is None or bv is None:
        return av is None and bv is None
    if av.codec != bv.codec:
        return False
    if av.width != bv.width or av.height != bv.height:
        return False
    if av.pix_fmt != bv.pix_fmt:
        return False
    if abs(av.fps - bv.fps) > fps_tolerance:
        return False

    aa = a.audio
    ba = b.audio
    if aa is None or ba is None:
        return aa is None and ba is None
    if aa.codec != ba.codec:
        return False
    if aa.sample_rate != ba.sample_rate:
        return False
    return aa.channels == ba.channels


def describe_mismatch(a: FileProbe, b: FileProbe, *, fps_tolerance: float = 0.01) -> list[str]:
    """Return human-readable descriptions of mismatched fields between *a* and *b*."""
    mismatches: list[str] = []

    a_container = container_family(a)
    b_container = container_family(b)
    if a_container != b_container:
        mismatches.append(f"container: {a_container} vs {b_container}")

    av, bv = a.video, b.video
    if av is None and bv is None:
        pass
    elif av is None or bv is None:
        mismatches.append("video stream presence differs")
    else:
        if av.codec != bv.codec:
            mismatches.append(f"video codec: {av.codec} vs {bv.codec}")
        if av.width != bv.width or av.height != bv.height:
            mismatches.append(f"resolution: {av.width}x{av.height} vs {bv.width}x{bv.height}")
        if av.pix_fmt != bv.pix_fmt:
            mismatches.append(f"pixel format: {av.pix_fmt} vs {bv.pix_fmt}")
        if abs(av.fps - bv.fps) > fps_tolerance:
            mismatches.append(f"frame rate: {av.fps:.3f} vs {bv.fps:.3f}")

    aa, ba = a.audio, b.audio
    if aa is None and ba is None:
        pass
    elif aa is None or ba is None:
        mismatches.append("audio stream presence differs")
    else:
        if aa.codec != ba.codec:
            mismatches.append(f"audio codec: {aa.codec} vs {ba.codec}")
        if aa.sample_rate != ba.sample_rate:
            mismatches.append(f"sample rate: {aa.sample_rate} vs {ba.sample_rate}")
        if aa.channels != ba.channels:
            mismatches.append(f"channels: {aa.channels} vs {ba.channels}")

    return mismatches
