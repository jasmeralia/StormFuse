# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import sys
from functools import lru_cache

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@lru_cache(maxsize=1)
def _nvenc_available() -> bool:
    if sys.platform != "win32":
        return False

    from stormfuse.ffmpeg.encoders import EncoderChoice, detect_encoder
    from stormfuse.ffmpeg.locator import FfmpegNotFoundError, ffmpeg_path

    try:
        return detect_encoder(ffmpeg_path()) == EncoderChoice.NVENC
    except FfmpegNotFoundError:
        return False


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("windows_only") and sys.platform != "win32":
            item.add_marker(pytest.mark.skip(reason="requires Windows"))
        if item.get_closest_marker("requires_nvenc") and not _nvenc_available():
            item.add_marker(pytest.mark.skip(reason="requires working NVENC"))
