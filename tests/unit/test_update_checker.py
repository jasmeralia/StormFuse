# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for update checks and installer download validation."""

from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from stormfuse.config import APP_VERSION
from stormfuse.core import update_checker
from stormfuse.core.update_checker import (
    UpdateInfo,
    check_for_updates,
    download_installer,
    validate_downloaded_installer,
)


def _next_patch_version() -> str:
    major, minor, patch = APP_VERSION.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


class _FakeResponse:
    def __init__(self, body: bytes, *, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self._offset = 0
        self.headers = headers or {}

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        if self._offset >= len(self._body):
            return b""
        if _size < 0:
            chunk = self._body[self._offset :]
            self._offset = len(self._body)
            return chunk
        chunk = self._body[self._offset : self._offset + _size]
        self._offset += len(chunk)
        return chunk


def test_check_for_updates_returns_none_when_already_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_version = APP_VERSION
    payload = [
        {
            "tag_name": f"v{current_version}",
            "name": f"StormFuse v{current_version}",
            "body": "Current release",
            "draft": False,
            "prerelease": False,
            "html_url": (
                f"https://github.com/jasmeralia/StormFuse/releases/tag/v{current_version}"
            ),
            "assets": [
                {
                    "name": f"StormFuse-Setup-{current_version}.exe",
                    "browser_download_url": (
                        f"https://example.invalid/StormFuse-Setup-{current_version}.exe"
                    ),
                    "size": update_checker._MIN_INSTALLER_BYTES,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda request, timeout: _FakeResponse(json.dumps(payload).encode("utf-8")),
    )

    assert check_for_updates() is None


def test_check_for_updates_returns_stable_release(monkeypatch: pytest.MonkeyPatch) -> None:
    next_version = _next_patch_version()
    payload = [
        {
            "tag_name": f"v{next_version}",
            "name": f"StormFuse v{next_version}",
            "body": "Bug fixes",
            "draft": False,
            "prerelease": False,
            "html_url": f"https://github.com/jasmeralia/StormFuse/releases/tag/v{next_version}",
            "assets": [
                {
                    "name": f"StormFuse-Setup-{next_version}.exe",
                    "browser_download_url": (
                        f"https://example.invalid/StormFuse-Setup-{next_version}.exe"
                    ),
                    "size": update_checker._MIN_INSTALLER_BYTES,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda request, timeout: _FakeResponse(json.dumps(payload).encode("utf-8")),
    )

    info = check_for_updates()

    assert info is not None
    assert info.current_version == APP_VERSION
    assert info.latest_version == next_version
    assert info.release_name == f"StormFuse v{next_version}"
    assert info.release_notes == "Bug fixes"
    assert not info.is_prerelease


def test_check_for_updates_gates_prereleases(monkeypatch: pytest.MonkeyPatch) -> None:
    prerelease_version = f"{_next_patch_version()}-beta.1"
    payload = [
        {
            "tag_name": f"v{prerelease_version}",
            "name": f"StormFuse v{prerelease_version}",
            "body": "Preview build",
            "draft": False,
            "prerelease": True,
            "html_url": (
                f"https://github.com/jasmeralia/StormFuse/releases/tag/v{prerelease_version}"
            ),
            "assets": [
                {
                    "name": f"StormFuse-Setup-{prerelease_version}.exe",
                    "browser_download_url": (
                        f"https://example.invalid/StormFuse-Setup-{prerelease_version}.exe"
                    ),
                    "size": update_checker._MIN_INSTALLER_BYTES,
                }
            ],
        }
    ]
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda request, timeout: _FakeResponse(json.dumps(payload).encode("utf-8")),
    )

    assert check_for_updates(include_prerelease=False) is None

    info = check_for_updates(include_prerelease=True)

    assert info is not None
    assert info.latest_version == prerelease_version
    assert info.is_prerelease


def test_check_for_updates_returns_none_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("offline")),
    )

    assert check_for_updates() is None


def test_validate_downloaded_installer_rejects_too_small_file(tmp_path) -> None:
    path = tmp_path / "StormFuse-Setup-1.0.6.exe"
    path.write_bytes(b"MZ" + b"\0" * 32)

    with pytest.raises(ValueError, match="too small"):
        validate_downloaded_installer(path)


def test_download_installer_rejects_size_mismatch(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"MZ" + (b"\0" * (update_checker._MIN_INSTALLER_BYTES - 2))
    headers = {"Content-Length": str(len(content))}
    monkeypatch.setattr(
        update_checker,
        "urlopen",
        lambda request, timeout: _FakeResponse(content, headers=headers),
    )
    update = UpdateInfo(
        current_version="1.0.5",
        latest_version="1.0.6",
        release_name="StormFuse v1.0.6",
        release_notes="Bug fixes",
        download_url="https://example.invalid/StormFuse-Setup-1.0.6.exe",
        download_size=len(content) + 1,
        browser_url="https://github.com/jasmeralia/StormFuse/releases/tag/v1.0.6",
        is_prerelease=False,
    )

    with pytest.raises(ValueError, match="size does not match"):
        download_installer(update, tmp_path)
