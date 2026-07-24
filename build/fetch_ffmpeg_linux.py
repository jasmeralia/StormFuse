#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Download verified static Linux ffmpeg binaries for AppImage builds.

This is intentionally separate from the default Linux build path. Debian,
RPM, Flatpak, and Snap packages obtain ffmpeg through their package/runtime
mechanisms; only AppImage invokes this script.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
FFMPEG_DIR = REPO_ROOT / "resources" / "ffmpeg"
ARCHIVE_URLS = {
    "amd64": (
        "https://johnvansickle.com/ffmpeg/releases/"
        "ffmpeg-release-amd64-static.tar.xz"
    ),
    "arm64": (
        "https://johnvansickle.com/ffmpeg/releases/"
        "ffmpeg-release-arm64-static.tar.xz"
    ),
}


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_expected_hash(hash_file: Path, archive_name: str) -> str:
    """Load the pinned hash for one archive from a sha256sum-format file."""
    if not hash_file.exists():
        raise ValueError(f"{hash_file} not found. Cannot verify download.")
    for raw_line in hash_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        digest, separator, filename = line.partition("  ")
        if separator and filename.strip() == archive_name:
            return digest.strip()
    raise ValueError(f"{hash_file} does not include a hash for {archive_name}.")


def extract_binaries(data: bytes, destination: Path) -> tuple[Path, Path]:
    """Extract only ffmpeg and ffprobe from a verified tar archive."""
    destination.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, Path] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
        for member in archive.getmembers():
            basename = Path(member.name).name
            if basename not in {"ffmpeg", "ffprobe"} or not member.isfile():
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            target = destination / basename
            target.write_bytes(source.read())
            target.chmod(0o755)
            extracted[basename] = target

    missing = {"ffmpeg", "ffprobe"} - extracted.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Verified archive did not contain required binaries: {names}.")
    return extracted["ffmpeg"], extracted["ffprobe"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch pinned static Linux ffmpeg binaries for an AppImage build."
    )
    parser.add_argument("--arch", choices=sorted(ARCHIVE_URLS), required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    url = ARCHIVE_URLS[args.arch]
    archive_name = Path(urlparse(url).path).name
    hash_file = REPO_ROOT / "build" / f"ffmpeg-linux-{args.arch}.sha256"

    try:
        expected_hash = load_expected_hash(hash_file, archive_name)
        print(f"Downloading {url} …")
        with urlopen(url) as response:
            data = response.read()
        actual_hash = sha256_of(data)
        if actual_hash != expected_hash:
            raise ValueError(
                f"SHA-256 mismatch for {archive_name}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        ffmpeg, ffprobe = extract_binaries(data, FFMPEG_DIR)
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Verified {archive_name} ({len(data) // 1024 // 1024} MB).")
    print(f"Extracted {ffmpeg} and {ffprobe}.")


if __name__ == "__main__":
    main()
