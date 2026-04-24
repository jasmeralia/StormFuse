#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Download and verify the pinned gyan.dev ffmpeg build.

Reads the expected archive SHA-256 hash from build/ffmpeg.sha256.
Extracts ffmpeg.exe and ffprobe.exe into resources/ffmpeg/.
"""
from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

REPO_ROOT = Path(__file__).parent.parent
SHA256_FILE = REPO_ROOT / "build" / "ffmpeg.sha256"
FFMPEG_DIR = REPO_ROOT / "resources" / "ffmpeg"

# Pinned gyan.dev essentials build URL — update alongside ffmpeg.sha256
FFMPEG_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/"
    "ffmpeg-7.1.1-essentials_build.zip"
)


def load_expected_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not SHA256_FILE.exists():
        print(f"ERROR: {SHA256_FILE} not found. Cannot verify download.", file=sys.stderr)
        sys.exit(1)
    for line in SHA256_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sha, _, name = line.partition("  ")
        if name:
            hashes[name.strip()] = sha.strip()
    return hashes


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    expected = load_expected_hashes()
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

    # Derive archive_name from the original URL, not resp.geturl().
    # GitHub release redirects go through a CDN whose final URL has a UUID
    # path segment rather than the original filename, which breaks the hash
    # lookup in ffmpeg.sha256.
    archive_name = Path(urlparse(FFMPEG_URL).path).name

    print(f"Downloading {FFMPEG_URL} …")
    with urlopen(FFMPEG_URL) as resp:
        data = resp.read()

    actual_archive_hash = sha256_of(data)
    if archive_name not in expected:
        print(
            f"ERROR: {SHA256_FILE} does not include a hash for {archive_name}.",
            file=sys.stderr,
        )
        sys.exit(1)
    if actual_archive_hash != expected[archive_name]:
        print(
            f"SHA-256 MISMATCH for {archive_name}!\n"
            f"  expected: {expected[archive_name]}\n"
            f"  actual:   {actual_archive_hash}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"Downloaded {len(data) // 1024 // 1024} MB and verified {archive_name}.\n"
        "Extracting …"
    )

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            basename = Path(name).name
            if basename in ("ffmpeg.exe", "ffprobe.exe"):
                content = zf.read(name)
                dest = FFMPEG_DIR / basename
                dest.write_bytes(content)
                print(
                    f"  Extracted {basename} ({len(content) // 1024} KB, "
                    f"sha256={sha256_of(content)})"
                )

    print("ffmpeg binaries ready in", FFMPEG_DIR)


if __name__ == "__main__":
    main()
