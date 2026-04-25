# SPDX-License-Identifier: GPL-3.0-or-later
"""GitHub Releases update checks and installer downloads."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from stormfuse.config import APP_VERSION

log = logging.getLogger("stormfuse.core.update_checker")

_GITHUB_RELEASES_API = "https://api.github.com/repos/jasmeralia/StormFuse/releases"
_INSTALLER_RE = re.compile(r"^StormFuse-Setup-.*\.exe$", re.IGNORECASE)
_PRERELEASE_TOKEN_RE = re.compile(r"([a-zA-Z]+)(\d*)")
_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)(?:[-+._]?([0-9A-Za-z.-]+))?$")
_DEFAULT_TIMEOUT_SEC = 5
_DOWNLOAD_TIMEOUT_SEC = 30
_DOWNLOAD_CHUNK_SIZE = 1024 * 64
_MIN_INSTALLER_BYTES = 1024 * 1024
_UNKNOWN_TOTAL = -1


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    release_name: str
    release_notes: str
    download_url: str
    download_size: int
    browser_url: str
    is_prerelease: bool


class _InstallerAsset(TypedDict):
    name: str
    browser_download_url: str
    size: int


def check_for_updates(include_prerelease: bool = False) -> UpdateInfo | None:
    """Return a newer installer release, or None when up to date or on soft failure."""
    current_version = _normalize_version(APP_VERSION)
    request = Request(
        _GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"StormFuse/{current_version}",
        },
    )
    log.info(
        "Checking for updates",
        extra={
            "event": "update.check.start",
            "ctx": {
                "current_version": current_version,
                "include_prerelease": include_prerelease,
            },
        },
    )
    try:
        with urlopen(request, timeout=_DEFAULT_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        log.warning(
            "Update check failed",
            extra={
                "event": "update.check.error",
                "ctx": {"error": type(exc).__name__, "message": str(exc)},
            },
        )
        return None

    if not isinstance(payload, list):
        log.warning(
            "Update check returned malformed payload",
            extra={
                "event": "update.check.error",
                "ctx": {"error": "invalid_payload", "payload_type": type(payload).__name__},
            },
        )
        return None

    current_key = _version_key(current_version)
    for release in payload:
        info = _parse_release(release, current_version=current_version)
        if info is None:
            continue
        if info.is_prerelease and not include_prerelease:
            continue
        if _version_key(info.latest_version) <= current_key:
            continue
        log.info(
            "Update available",
            extra={
                "event": "update.check.available",
                "ctx": {
                    "current_version": current_version,
                    "latest_version": info.latest_version,
                    "prerelease": info.is_prerelease,
                    "browser_url": info.browser_url,
                },
            },
        )
        return info

    log.info(
        "No update available",
        extra={
            "event": "update.check.none",
            "ctx": {
                "current_version": current_version,
                "include_prerelease": include_prerelease,
            },
        },
    )
    return None


def download_installer(
    update: UpdateInfo,
    destination_dir: Path,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path:
    """Download, validate, and return the local installer path."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / _download_filename(update)
    temp_path = destination.with_suffix(destination.suffix + ".part")
    progress = progress_cb or (lambda _received, _total: None)
    progress(0, update.download_size if update.download_size > 0 else _UNKNOWN_TOTAL)
    request = Request(update.download_url, headers={"User-Agent": f"StormFuse/{APP_VERSION}"})

    log.info(
        "Downloading installer update",
        extra={
            "event": "update.download.start",
            "ctx": {
                "version": update.latest_version,
                "destination": str(destination),
                "download_url": update.download_url,
            },
        },
    )
    try:
        with urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SEC) as response:
            header_total = response.headers.get("Content-Length")
            total = _content_length(header_total, update.download_size)
            bytes_written = 0
            with temp_path.open("wb") as handle:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    bytes_written += len(chunk)
                    progress(bytes_written, total)
        temp_path.replace(destination)
        validate_downloaded_installer(destination, expected_size=update.download_size)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
        for path in (temp_path, destination):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        log.warning(
            "Installer download failed",
            extra={
                "event": "update.download.error",
                "ctx": {
                    "version": update.latest_version,
                    "destination": str(destination),
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            },
        )
        raise

    log.info(
        "Installer downloaded",
        extra={
            "event": "update.download.success",
            "ctx": {
                "version": update.latest_version,
                "destination": str(destination),
                "bytes": destination.stat().st_size,
            },
        },
    )
    return destination


def validate_downloaded_installer(path: Path, *, expected_size: int = 0) -> None:
    """Reject obviously invalid downloads before launch."""
    if not path.is_file():
        raise ValueError("Installer download is missing.")

    size = path.stat().st_size
    if size < _MIN_INSTALLER_BYTES:
        raise ValueError("Installer download is too small to be valid.")
    if expected_size > 0 and size != expected_size:
        raise ValueError("Installer download size does not match the release asset.")

    with path.open("rb") as handle:
        header = handle.read(2)
    if header != b"MZ":
        raise ValueError("Installer download is not a Windows executable.")


def _parse_release(release: object, *, current_version: str) -> UpdateInfo | None:
    if not isinstance(release, dict):
        return None
    if bool(release.get("draft")):
        return None

    tag_name = release.get("tag_name")
    if not isinstance(tag_name, str):
        return None
    latest_version = _normalize_version(tag_name)
    if not latest_version:
        return None

    asset = _matching_asset(release.get("assets"))
    if asset is None:
        return None

    browser_url = release.get("html_url")
    if not isinstance(browser_url, str):
        browser_url = f"https://github.com/jasmeralia/StormFuse/releases/tag/v{latest_version}"

    release_name = release.get("name")
    if not isinstance(release_name, str) or not release_name.strip():
        release_name = f"StormFuse v{latest_version}"

    notes = release.get("body")
    if not isinstance(notes, str):
        notes = ""

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        release_name=release_name,
        release_notes=notes.strip(),
        download_url=asset["browser_download_url"],
        download_size=asset["size"],
        browser_url=browser_url,
        is_prerelease=bool(release.get("prerelease")),
    )


def _matching_asset(assets: object) -> _InstallerAsset | None:
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        download_url = asset.get("browser_download_url")
        size = asset.get("size")
        if (
            isinstance(name, str)
            and _INSTALLER_RE.match(name)
            and isinstance(download_url, str)
            and isinstance(size, int)
            and size > 0
        ):
            return {
                "name": name,
                "browser_download_url": download_url,
                "size": size,
            }
    return None


def _normalize_version(value: str) -> str:
    return value.strip().lstrip("vV")


def _version_key(value: str) -> tuple[tuple[int, ...], int, tuple[int, int, str]]:
    normalized = _normalize_version(value)
    match = _VERSION_RE.fullmatch(normalized)
    if not match:
        return (tuple(), 0, (0, 0, normalized.lower()))

    release_part = tuple(int(segment) for segment in match.group(1).split("."))
    prerelease = match.group(2)
    if prerelease is None:
        return (release_part, 1, (0, 0, ""))

    label, number = _parse_prerelease(prerelease)
    return (release_part, 0, (_prerelease_rank(label), number, label))


def _parse_prerelease(value: str) -> tuple[str, int]:
    token = re.split(r"[.\-_]", value, maxsplit=1)[0]
    match = _PRERELEASE_TOKEN_RE.fullmatch(token)
    if match is None:
        return value.lower(), 0
    number = match.group(2)
    return match.group(1).lower(), int(number) if number else 0


def _prerelease_rank(label: str) -> int:
    if label in {"alpha", "a"}:
        return 0
    if label in {"beta", "b"}:
        return 1
    if label in {"rc", "pre", "preview"}:
        return 2
    return 3


def _download_filename(update: UpdateInfo) -> str:
    parsed = urlparse(update.download_url)
    filename = Path(parsed.path).name
    if filename and _INSTALLER_RE.match(filename):
        return filename
    return f"StormFuse-Setup-{update.latest_version}.exe"


def _content_length(header_total: str | None, asset_total: int) -> int:
    if header_total is not None:
        try:
            total = int(header_total)
        except ValueError:
            total = 0
        else:
            if total > 0:
                return total
    return asset_total if asset_total > 0 else _UNKNOWN_TOTAL
