# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for scripts/release_info.py release-decision logic."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "release_info.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_info_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


release_info = _load_module()


def test_next_patch_from_no_tags() -> None:
    assert release_info.next_patch(None) == "v1.0.0"


def test_next_patch_increments_patch_component() -> None:
    assert release_info.next_patch("v1.2.3") == "v1.2.4"
    assert release_info.next_patch("v0.0.9") == "v0.0.10"


def _run(env: dict[str, str], cwd: Path) -> tuple[int, str, str]:
    full_env = {**os.environ}
    # Drop any GITHUB_OUTPUT inherited from the parent test runner so the
    # script only writes to stdout, which is what these tests read.
    full_env.pop("GITHUB_OUTPUT", None)
    full_env.update(env)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        env=full_env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _outputs(stdout: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in stdout.strip().splitlines() if "=" in line)


def _init_repo_with_tags(tmp_path: Path, tags: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "a").write_text("initial\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    for tag in tags:
        subprocess.run(["git", "tag", tag], cwd=repo, check=True)
    return repo


def test_pull_request_event_skips_release(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    code, stdout, _ = _run({"EVENT_NAME": "pull_request", "REF": "refs/pull/1/merge"}, repo)
    assert code == 0
    out = _outputs(stdout)
    assert out["is_release"] == "false"


def test_push_master_with_existing_tag_yields_next_patch(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    # Move HEAD forward so it's not pointing at the existing tag.
    (repo / "a").write_text("next\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "next"], cwd=repo, check=True)

    code, stdout, _ = _run({"EVENT_NAME": "push", "REF": "refs/heads/master"}, repo)
    assert code == 0
    out = _outputs(stdout)
    assert out == {"is_release": "true", "create_tag": "true", "tag_name": "v1.0.6"}


def test_push_master_head_already_tagged_skips_release(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    # HEAD is the same commit as v1.0.5; we should NOT issue v1.0.6.
    code, stdout, _ = _run({"EVENT_NAME": "push", "REF": "refs/heads/master"}, repo)
    assert code == 0
    out = _outputs(stdout)
    assert out["is_release"] == "false"
    assert out["tag_name"] == "v1.0.5"


def test_push_tag_event_resolves_to_that_tag(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    code, stdout, _ = _run({"EVENT_NAME": "push", "REF": "refs/tags/v1.0.5"}, repo)
    assert code == 0
    out = _outputs(stdout)
    assert out == {"is_release": "true", "create_tag": "false", "tag_name": "v1.0.5"}


def test_workflow_dispatch_without_release_only_lints(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    code, stdout, _ = _run(
        {
            "EVENT_NAME": "workflow_dispatch",
            "REF": "refs/heads/feature/foo",
            "DISPATCH_RELEASE": "false",
        },
        repo,
    )
    assert code == 0
    assert _outputs(stdout)["is_release"] == "false"


def test_workflow_dispatch_release_from_feature_branch_errors(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    code, _, stderr = _run(
        {
            "EVENT_NAME": "workflow_dispatch",
            "REF": "refs/heads/feature/foo",
            "DISPATCH_RELEASE": "true",
        },
        repo,
    )
    assert code == 1
    assert "refs/heads/master" in stderr


def test_workflow_dispatch_release_on_tag_rebuilds_tag(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    code, stdout, _ = _run(
        {
            "EVENT_NAME": "workflow_dispatch",
            "REF": "refs/tags/v1.0.5",
            "DISPATCH_RELEASE": "true",
        },
        repo,
    )
    assert code == 0
    out = _outputs(stdout)
    assert out == {"is_release": "true", "create_tag": "false", "tag_name": "v1.0.5"}


def test_invalid_tag_format_rejected(tmp_path: Path) -> None:
    repo = _init_repo_with_tags(tmp_path, ["v1.0.5"])
    code, _, stderr = _run({"EVENT_NAME": "push", "REF": "refs/tags/release-1.2"}, repo)
    assert code == 1
    assert "v-prefixed semver" in stderr
