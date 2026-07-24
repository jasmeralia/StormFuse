# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for build/fetch_ffmpeg_linux.py."""

from __future__ import annotations

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "build" / "fetch_ffmpeg_linux.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_ffmpeg_linux_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


fetch_ffmpeg_linux = _load_module()


def test_pinned_archive_hashes_match_configured_downloads() -> None:
    expected = {
        "amd64": "0ba73bbd93472c7622f6dec26d334c5e62e64d858d072490b2844320970456cd",
        "arm64": "d3f90a71a38238466de2e4dc98537862d244e3307383435f94cbc4b8491033f8",
    }

    for arch, digest in expected.items():
        url = fetch_ffmpeg_linux.ARCHIVE_URLS[arch]
        archive_name = Path(url).name
        hash_file = REPO_ROOT / "build" / f"ffmpeg-linux-{arch}.sha256"
        assert fetch_ffmpeg_linux.load_expected_hash(hash_file, archive_name) == digest


def _static_archive(*, include_ffprobe: bool = True) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        binaries = {"ffmpeg": b"ffmpeg-binary"}
        if include_ffprobe:
            binaries["ffprobe"] = b"ffprobe-binary"
        for name, content in binaries.items():
            # Arbitrary nested path -- extract_binaries() matches on
            # basename alone regardless of the containing directory depth.
            member = tarfile.TarInfo(f"ffmpeg-build/bin/{name}")
            member.size = len(content)
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def test_parse_args_requires_supported_architecture() -> None:
    assert fetch_ffmpeg_linux.parse_args(["--arch", "amd64"]).arch == "amd64"
    assert fetch_ffmpeg_linux.parse_args(["--arch", "arm64"]).arch == "arm64"
    with pytest.raises(SystemExit):
        fetch_ffmpeg_linux.parse_args(["--arch", "i686"])


def test_load_expected_hash_reads_sha256sum_format(tmp_path: Path) -> None:
    hash_file = tmp_path / "ffmpeg.sha256"
    hash_file.write_text(
        "# comment\nabc123  ffmpeg-release-amd64-static.tar.xz\n",
        encoding="utf-8",
    )

    assert (
        fetch_ffmpeg_linux.load_expected_hash(
            hash_file,
            "ffmpeg-release-amd64-static.tar.xz",
        )
        == "abc123"
    )


def test_extract_binaries_writes_executable_files(tmp_path: Path) -> None:
    ffmpeg, ffprobe = fetch_ffmpeg_linux.extract_binaries(_static_archive(), tmp_path)

    assert ffmpeg.read_bytes() == b"ffmpeg-binary"
    assert ffprobe.read_bytes() == b"ffprobe-binary"
    assert ffmpeg.stat().st_mode & 0o111
    assert ffprobe.stat().st_mode & 0o111


def test_extract_binaries_rejects_incomplete_archive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ffprobe"):
        fetch_ffmpeg_linux.extract_binaries(
            _static_archive(include_ffprobe=False),
            tmp_path,
        )
