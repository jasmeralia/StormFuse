# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for CI workflow contracts in DESIGN.md §16."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_ci_workflow_contract() -> None:
    assert not (REPO_ROOT / ".github" / "workflows" / "ci.yml").exists()

    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "name: CI / Build & Release" in workflow
    assert "branches:\n      - master" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    assert "run: make deps" in workflow
    assert "run: make lint" in workflow
    assert "run: make test" in workflow

    # New release-resolution contract: a single resolve job decides whether
    # to release and the dependent jobs gate on its `is_release` output.
    assert "Resolve Release Info" in workflow
    assert "scripts/release_info.py" in workflow
    assert "needs.resolve.outputs.is_release == 'true'" in workflow
    assert "needs: [resolve, lint-and-test]" in workflow

    # Dynamic-version contract: no APP_VERSION sync or bump PR machinery.
    assert "sync-version" not in workflow
    assert "sync_release_version" not in workflow
    assert "release/v" not in workflow
    assert "gh pr create" not in workflow
    assert "gh pr merge" not in workflow
    assert "scripts/write_version.py" in workflow

    # Action pins
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "codecov/codecov-action@v7" in workflow
    assert "softprops/action-gh-release@v3" in workflow
    assert "@v4" not in workflow
    assert "@v5" not in workflow

    # Linting / testing happens via Makefile, not raw tool invocations.
    assert "ruff check" not in workflow
    assert "mypy src/stormfuse/" not in workflow
    assert "pytest tests/unit/" not in workflow


def test_release_pipeline_contract_on_windows() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "TAG_NAME" in workflow
    assert "Create Release Tag" in workflow
    assert "refs/tags/${{ env.TAG_NAME }}" in workflow

    # Tag created via the GitHub API (not git push), to bypass the workflow-
    # scope restriction on GITHUB_TOKEN when the commit being tagged includes
    # workflow file changes.
    assert "gh api" in workflow
    assert '--field "ref=refs/tags/${TAG_NAME}"' in workflow

    # The build job writes the release _version.py from the tag.
    assert 'python scripts/write_version.py --tag "${TAG_NAME}"' in workflow

    # Installer build + release publish chain
    assert "run: make deps" in workflow
    assert "run: make fetch-ffmpeg" in workflow
    assert "run: make test" in workflow
    assert "run: make installer" in workflow
    assert workflow.count("run: make generate-third-party") == 2
    assert "Ensure NSIS" in workflow
    assert "GITHUB_PATH" in workflow
    assert "shell: bash" in workflow

    # Release publishing
    assert (
        "gh run download \"$GITHUB_RUN_ID\" --pattern 'StormFuse-*' --dir release-assets"
        in workflow
    )
    assert "softprops/action-gh-release@v3" in workflow

    # Things we deliberately don't do anymore.
    assert "actions/download-artifact" not in workflow
    assert "pip install -r requirements-dev.txt" not in workflow
    assert "pyinstaller build/stormfuse.spec" not in workflow
    assert "makensis build/installer/stormfuse.nsi" not in workflow
    assert "gh release create" not in workflow


def test_release_pipeline_builds_all_linux_packages_natively() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for job in (
        "build-linux-deb-rpm:",
        "build-appimage:",
        "build-flatpak:",
        "build-snap:",
    ):
        assert job in workflow

    assert workflow.count("ubuntu-24.04-arm") == 4
    assert "nfpm package --config build/linux/nfpm.yaml --packager deb" in workflow
    assert "nfpm package --config build/linux/nfpm.yaml --packager rpm" in workflow
    assert "make fetch-ffmpeg-linux-${ARCH}" in workflow
    assert "appimagetool-${APPIMAGE_ARCH}.AppImage" in workflow
    assert "flatpak/flatpak-github-actions/flatpak-builder@v6" in workflow
    assert "snapcore/action-build@v1" in workflow
    assert "build/linux/flatpak/net.windsofstorm.StormFuse.yaml" in workflow
    assert "build/linux/snap" in workflow

    for suffix in ("deb", "rpm", "AppImage", "flatpak", "snap"):
        assert f"release-assets/**/*.{suffix}" in workflow


def test_windows_release_is_not_blocked_by_linux_packaging_failures() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    # The release job must gate on build-installer succeeding, not on every
    # Linux packaging job succeeding — a broken/flaky Linux leg must not
    # withhold the Windows installer from being published.
    assert "needs.build-installer.result == 'success'" in workflow
    assert "fail_on_unmatched_files: false" in workflow

    # A separate, always-run job still fails the overall workflow loudly if
    # any packaging job didn't succeed, so a partial release gets noticed.
    assert "verify-release-complete:" in workflow
    assert "One or more packaging jobs did not succeed" in workflow


def test_makefile_supports_windows_virtualenv_paths() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "ifeq ($(OS),Windows_NT)" in makefile
    assert "VENV_BIN := $(VENV)/Scripts" in makefile
    assert "PY       := $(VENV_BIN)/python.exe" in makefile


def test_makefile_writes_version_file_for_dev_builds() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    # deps depends on version-file so editable installs see a real version.
    assert "deps: venv version-file" in makefile
    # installer also depends on it — CI overrides via --tag before invoking.
    assert "installer: version-file" in makefile
    assert "scripts/write_version.py --root ." in makefile
    assert "VERSION_FILE := src/stormfuse/_version.py" in makefile
