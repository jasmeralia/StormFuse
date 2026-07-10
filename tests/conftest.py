# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import platform
import sys
from functools import lru_cache

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@lru_cache(maxsize=1)
def _nvenc_available() -> bool:
    if sys.platform not in {"win32", "linux"}:
        return False

    from stormfuse.ffmpeg.encoders import EncoderChoice, detect_encoder
    from stormfuse.ffmpeg.locator import FfmpegNotFoundError, ffmpeg_path

    try:
        return detect_encoder(ffmpeg_path()) == EncoderChoice.NVENC
    except FfmpegNotFoundError:
        return False


def _is_wsl() -> bool:
    return "microsoft" in platform.uname().release.lower()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("functional"):
            if sys.platform not in {"win32", "linux"}:
                item.add_marker(pytest.mark.skip(reason="requires Windows or Linux"))
            if (
                sys.platform == "linux"
                and _is_wsl()
                and os.environ.get("STORMFUSE_RUN_FUNCTIONAL_ON_WSL") != "1"
            ):
                item.add_marker(
                    pytest.mark.skip(
                        reason=(
                            "WSL detected — functional tests are opt-in there via "
                            "STORMFUSE_RUN_FUNCTIONAL_ON_WSL=1; GPU/subprocess behavior "
                            "under WSL is inconsistent enough that we don't want CI-style "
                            "false confidence by default"
                        )
                    )
                )
        if item.get_closest_marker("requires_nvenc") and not _nvenc_available():
            item.add_marker(pytest.mark.skip(reason="requires working NVENC"))
