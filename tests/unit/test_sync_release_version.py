# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for release version synchronization."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from scripts.sync_release_version import (
    Version,
    choose_release_version,
    sync_release_version,
)


def _write_release_files(root: Path, version: str = "1.0.19") -> None:
    config = root / "src" / "stormfuse"
    config.mkdir(parents=True)
    (config / "config.py").write_text(
        f'APP_NAME = "StormFuse"\nAPP_VERSION = "{version}"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# StormFuse\n\n"
        "![Release Build](https://img.shields.io/github/actions/workflow/status/"
        f"jasmeralia/StormFuse/release.yml?event=push&branch=v{version}"
        "&label=Release%20Build)\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "All notable changes to this project will be documented in this file.\n\n"
        f"## [{version}] - 2026-04-29\n\n"
        "### Changed\n\n"
        "#### Existing section\n"
        "- Existing entry.\n",
        encoding="utf-8",
    )


def test_choose_release_version_keeps_new_untagged_app_version() -> None:
    version, bumped = choose_release_version(Version.parse("1.0.20"), ["v1.0.19"])

    assert version == Version.parse("1.0.20")
    assert bumped is False


def test_choose_release_version_bumps_when_app_version_is_already_tagged() -> None:
    version, bumped = choose_release_version(Version.parse("1.0.19"), ["v1.0.18", "v1.0.19"])

    assert version == Version.parse("1.0.20")
    assert bumped is True


def test_choose_release_version_bumps_stale_app_version_after_latest_tag() -> None:
    version, bumped = choose_release_version(Version.parse("1.0.17"), ["v1.0.18", "v1.0.19"])

    assert version == Version.parse("1.0.20")
    assert bumped is True


def test_sync_release_version_updates_files_when_bumped(tmp_path: Path) -> None:
    _write_release_files(tmp_path)

    result = sync_release_version(
        tmp_path,
        ["v1.0.18", "v1.0.19"],
        date(2026, 5, 7),
        write=True,
    )

    assert result == {
        "app_version": "1.0.19",
        "release_version": "1.0.20",
        "tag_name": "v1.0.20",
        "bumped": True,
    }
    assert 'APP_VERSION = "1.0.20"' in (tmp_path / "src" / "stormfuse" / "config.py").read_text(
        encoding="utf-8"
    )
    assert "branch=v1.0.20" in (tmp_path / "README.md").read_text(encoding="utf-8")
    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.index("## [1.0.20] - 2026-05-07") < changelog.index("## [1.0.19]")
    assert "- Automatic release for latest changes merged to master." in changelog


def test_sync_release_version_does_not_write_when_app_version_is_releasable(
    tmp_path: Path,
) -> None:
    _write_release_files(tmp_path, version="1.0.20")

    result = sync_release_version(tmp_path, ["v1.0.19"], date(2026, 5, 7), write=True)

    assert result["tag_name"] == "v1.0.20"
    assert result["bumped"] is False
    assert "## [1.0.20]" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")


def test_version_rejects_non_three_part_versions() -> None:
    with pytest.raises(ValueError, match=r"Expected X\.Y\.Z version"):
        Version.parse("1.0")
