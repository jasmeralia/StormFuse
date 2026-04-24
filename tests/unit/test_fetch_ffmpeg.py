# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for pinned ffmpeg archive metadata (§2.3, §12.1, §20)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "build" / "fetch_ffmpeg.py"
    spec = importlib.util.spec_from_file_location("fetch_ffmpeg", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pinned_archive_hash_matches_configured_download() -> None:
    module = _load_module()

    expected = module.load_expected_hashes()

    assert expected == {
        "ffmpeg-7.1.1-essentials_build.zip": (
            "04861d3339c5ebe38b56c19a15cf2c0cc97f5de4fa8910e4d47e5e6404e4a2d4"
        )
    }
    assert module.FFMPEG_URL.endswith("ffmpeg-7.1.1-essentials_build.zip")


def test_ffmpeg_source_notice_has_no_unresolved_placeholders() -> None:
    source_notice = (
        Path(__file__).resolve().parents[2] / "resources" / "licenses" / "FFMPEG-SOURCE.txt"
    ).read_text(encoding="utf-8")

    assert "(update after make fetch-ffmpeg)" not in source_notice
    assert "04861d3339c5ebe38b56c19a15cf2c0cc97f5de4fa8910e4d47e5e6404e4a2d4" in source_notice
    assert "Source commit    : db69d06" in source_notice
