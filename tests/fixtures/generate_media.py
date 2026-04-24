# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate synthetic media fixtures for Windows functional tests (§11.3)."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MediaSpec:
    filename: str
    duration_sec: float
    width: int
    height: int
    fps: int
    container: str
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    sample_rate: int = 48_000
    channels: int = 2
    pixel_format: str = "yuv420p"
    tone_hz: int = 660
    video_args: tuple[str, ...] = field(default_factory=lambda: ("-preset", "ultrafast"))


FUNCTIONAL_MEDIA_SPECS: dict[str, MediaSpec] = {
    "combine_stream_a": MediaSpec(
        filename="combine-stream-a.mkv",
        duration_sec=1,
        width=640,
        height=360,
        fps=30,
        container="mkv",
        tone_hz=660,
    ),
    "combine_stream_b": MediaSpec(
        filename="combine-stream-b.mkv",
        duration_sec=1,
        width=640,
        height=360,
        fps=30,
        container="mkv",
        tone_hz=880,
    ),
    "combine_normalize_small": MediaSpec(
        filename="combine-normalize-small.mp4",
        duration_sec=1,
        width=320,
        height=240,
        fps=24,
        container="mp4",
        tone_hz=510,
    ),
    "combine_normalize_large": MediaSpec(
        filename="combine-normalize-large.mkv",
        duration_sec=1,
        width=640,
        height=360,
        fps=30,
        container="mkv",
        tone_hz=930,
    ),
    "compress_input": MediaSpec(
        filename="compress-input.mp4",
        duration_sec=12,
        width=1280,
        height=720,
        fps=30,
        container="mp4",
        tone_hz=720,
    ),
    "cancel_input": MediaSpec(
        filename="cancel-input.mp4",
        duration_sec=8,
        width=1920,
        height=1080,
        fps=60,
        container="mp4",
        tone_hz=410,
    ),
}


class MediaGenerationError(RuntimeError):
    def __init__(self, output: Path, stderr_tail: str) -> None:
        self.output = output
        self.stderr_tail = stderr_tail
        super().__init__(f"ffmpeg failed while generating {output.name}: {stderr_tail}")


def generate_media(ffmpeg_exe: Path, output_dir: Path, spec: MediaSpec) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / spec.filename

    video_src = (
        f"testsrc2=size={spec.width}x{spec.height}:rate={spec.fps}:duration={spec.duration_sec}"
    )
    audio_src = (
        f"sine=frequency={spec.tone_hz}:sample_rate={spec.sample_rate}:duration={spec.duration_sec}"
    )

    argv = [
        str(ffmpeg_exe),
        "-hide_banner",
        "-y",
        "-f",
        "lavfi",
        "-i",
        video_src,
        "-f",
        "lavfi",
        "-i",
        audio_src,
        "-c:v",
        spec.video_codec,
        *spec.video_args,
        "-pix_fmt",
        spec.pixel_format,
        "-c:a",
        spec.audio_codec,
        "-b:a",
        spec.audio_bitrate,
        "-ar",
        str(spec.sample_rate),
        "-ac",
        str(spec.channels),
        "-shortest",
    ]
    if spec.container == "mp4":
        argv += ["-movflags", "+faststart"]
    argv += ["--", str(output_path)]

    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaGenerationError(output_path, "\n".join(result.stderr.splitlines()[-20:]))

    return output_path


def generate_functional_media(ffmpeg_exe: Path, output_dir: Path) -> dict[str, Path]:
    generated: dict[str, Path] = {}
    for name, spec in FUNCTIONAL_MEDIA_SPECS.items():
        generated[name] = generate_media(ffmpeg_exe, output_dir, spec)
    return generated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ffmpeg_exe", type=Path, help="Path to ffmpeg executable")
    parser.add_argument("output_dir", type=Path, help="Directory to write generated media into")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    generate_functional_media(args.ffmpeg_exe, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
