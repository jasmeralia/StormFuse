# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from stormfuse.ffmpeg.locator import FfmpegNotFoundError, ffmpeg_path, ffprobe_path
from tests.fixtures.generate_media import generate_functional_media


@pytest.fixture(scope="session")
def bundled_ffmpeg() -> Path:
    try:
        return ffmpeg_path()
    except FfmpegNotFoundError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="session")
def bundled_ffprobe() -> Path:
    try:
        return ffprobe_path()
    except FfmpegNotFoundError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="session")
def generated_media(
    tmp_path_factory: pytest.TempPathFactory, bundled_ffmpeg: Path
) -> dict[str, Path]:
    media_dir = tmp_path_factory.mktemp("functional-media")
    return generate_functional_media(bundled_ffmpeg, media_dir)
