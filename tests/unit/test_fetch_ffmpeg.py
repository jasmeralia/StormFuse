# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for pinned ffmpeg archive metadata (§2.3, §12.1, §20)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest


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
        "ffmpeg-8.1-essentials_build.zip": (
            "8748283d821613d930b0e7be685aaa9df4ca6f0ad4d0c42fd02622b3623463c6"
        )
    }
    assert module.FFMPEG_URL.endswith("ffmpeg-8.1-essentials_build.zip")


def test_ffmpeg_source_notice_has_no_unresolved_placeholders() -> None:
    source_notice = (
        Path(__file__).resolve().parents[2] / "resources" / "licenses" / "FFMPEG-SOURCE.txt"
    ).read_text(encoding="utf-8")

    assert "(update after make fetch-ffmpeg)" not in source_notice
    assert "8748283d821613d930b0e7be685aaa9df4ca6f0ad4d0c42fd02622b3623463c6" in source_notice
    assert "Source commit    : 9047fa1b08" in source_notice


def test_fetch_ffmpeg_uses_original_download_filename_on_redirect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    archive_name = Path(module.FFMPEG_URL).name
    ffmpeg_dir = tmp_path / "ffmpeg"
    sha256_file = tmp_path / "ffmpeg.sha256"

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("ffmpeg-8.1-essentials_build/bin/ffmpeg.exe", b"ffmpeg-binary")
        archive.writestr("ffmpeg-8.1-essentials_build/bin/ffprobe.exe", b"ffprobe-binary")
    archive_bytes = archive_buffer.getvalue()
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    sha256_file.write_text(f"{archive_sha}  {archive_name}\n", encoding="utf-8")

    monkeypatch.setattr(module, "SHA256_FILE", sha256_file)
    monkeypatch.setattr(module, "FFMPEG_DIR", ffmpeg_dir)

    class RedirectedResponse:
        def __enter__(self) -> RedirectedResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return archive_bytes

        def geturl(self) -> str:
            return (
                "https://release-assets.githubusercontent.com/assets/"
                "20f97254-bd43-4133-afd5-023a591f278f"
            )

    monkeypatch.setattr(module, "urlopen", lambda _url: RedirectedResponse())

    module.main()

    assert (ffmpeg_dir / "ffmpeg.exe").read_bytes() == b"ffmpeg-binary"
    assert (ffmpeg_dir / "ffprobe.exe").read_bytes() == b"ffprobe-binary"
