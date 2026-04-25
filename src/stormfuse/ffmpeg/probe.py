# SPDX-License-Identifier: GPL-3.0-or-later
"""ffprobe wrapper returning typed dataclasses (§7.2)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stormfuse.ffmpeg._subprocess import run
from stormfuse.logging_setup import current_job_id

log = logging.getLogger("ffmpeg.probe")

_FFPROBE_FLAGS = [
    "-v",
    "error",
    "-print_format",
    "json",
    "-show_streams",
    "-show_format",
]


class ProbeError(Exception):
    def __init__(self, path: Path, stderr_tail: str) -> None:
        self.path = path
        self.stderr_tail = stderr_tail
        super().__init__(f"ffprobe failed on {path}: {stderr_tail[:200]}")


@dataclass(frozen=True)
class VideoStream:
    codec: str
    width: int
    height: int
    pix_fmt: str
    fps: float


@dataclass(frozen=True)
class AudioStream:
    codec: str
    sample_rate: int
    channels: int


@dataclass
class FileProbe:
    path: Path
    video: VideoStream | None
    audio: AudioStream | None
    duration_sec: float
    size_bytes: int
    raw: dict[str, Any]


def _parse_fps(r_frame_rate: str) -> float:
    if "/" in r_frame_rate:
        num_s, den_s = r_frame_rate.split("/", 1)
        num, den = float(num_s), float(den_s)
        if den > 0:
            return num / den
    try:
        return float(r_frame_rate)
    except ValueError:
        return 0.0


def probe(ffprobe_exe: Path, path: Path, *, job_id: str | None = None) -> FileProbe:
    """Run ffprobe on *path* and return a FileProbe."""
    resolved_job_id = job_id or current_job_id()

    log.debug(
        "Probing file",
        extra=_log_extra("probe.start", {"path": str(path)}, resolved_job_id),
    )

    cmd = [str(ffprobe_exe), *_FFPROBE_FLAGS, "--", str(path)]

    try:
        result = run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            job_id=resolved_job_id,
        )
    except OSError as exc:
        stderr_tail = str(exc)
        log.error(
            "ffprobe OS error",
            extra=_log_extra(
                "probe.error",
                {"path": str(path), "error": stderr_tail},
                resolved_job_id,
            ),
        )
        raise ProbeError(path, stderr_tail) from exc

    if result.returncode != 0:
        stderr_text = result.stderr if isinstance(result.stderr, str) else result.stderr.decode()
        stderr_tail = stderr_text[-2000:]
        log.error(
            "ffprobe exited non-zero",
            extra=_log_extra(
                "probe.error",
                {
                    "path": str(path),
                    "returncode": result.returncode,
                    "stderr_tail": stderr_tail.splitlines()[-20:],
                },
                resolved_job_id,
            ),
        )
        raise ProbeError(path, stderr_tail)

    stdout_text = result.stdout if isinstance(result.stdout, str) else result.stdout.decode()
    data: dict[str, Any] = json.loads(stdout_text)
    streams: list[dict[str, Any]] = data.get("streams", [])
    fmt: dict[str, Any] = data.get("format", {})

    video_stream: VideoStream | None = None
    audio_stream: AudioStream | None = None

    for s in streams:
        if s.get("codec_type") == "video" and video_stream is None:
            video_stream = VideoStream(
                codec=s.get("codec_name", ""),
                width=int(s.get("width", 0)),
                height=int(s.get("height", 0)),
                pix_fmt=s.get("pix_fmt", ""),
                fps=_parse_fps(s.get("r_frame_rate", "0/1")),
            )
        elif s.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = AudioStream(
                codec=s.get("codec_name", ""),
                sample_rate=int(s.get("sample_rate", 0)),
                channels=int(s.get("channels", 0)),
            )

    duration_sec = float(fmt.get("duration", 0.0))
    size_bytes = int(fmt.get("size", 0))

    fp = FileProbe(
        path=path,
        video=video_stream,
        audio=audio_stream,
        duration_sec=duration_sec,
        size_bytes=size_bytes,
        raw=data,
    )

    log.debug(
        "Probe complete",
        extra=_log_extra(
            "probe.result",
            {
                "path": str(path),
                "duration_sec": duration_sec,
                "video": (
                    f"{video_stream.codec} {video_stream.width}x{video_stream.height}"
                    f"@{video_stream.fps:.2f} {video_stream.pix_fmt}"
                )
                if video_stream
                else None,
                "audio": (
                    f"{audio_stream.codec} {audio_stream.sample_rate}Hz {audio_stream.channels}ch"
                )
                if audio_stream
                else None,
            },
            resolved_job_id,
        ),
    )

    return fp


def _log_extra(event: str, ctx: dict[str, object], job_id: str | None) -> dict[str, object]:
    extra: dict[str, object] = {"event": event, "ctx": ctx}
    if job_id is not None:
        extra["job_id"] = job_id
    return extra
