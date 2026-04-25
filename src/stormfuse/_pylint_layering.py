# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom pylint checks for StormFuse import-layering rules (§4, §13)."""

from __future__ import annotations

from typing import Final

from astroid import nodes  # type: ignore[import-untyped]
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

_STORMFUSE_ROOT: Final[str] = "stormfuse"
_UI_ROOT: Final[str] = "stormfuse.ui"
_CORE_ROOT: Final[str] = "stormfuse.core"
_FFMPEG_ROOT: Final[str] = "stormfuse.ffmpeg"
_JOBS_ROOT: Final[str] = "stormfuse.jobs"
_MENU_ACTIONS_MODULE: Final[str] = "stormfuse.ui.menu_actions"
_SUBPROCESS_MODULE: Final[str] = "subprocess"


class StormFuseLayeringChecker(BaseChecker):
    """Enforce package boundaries that ruff and vanilla pylint cannot express."""

    name = "stormfuse-layering"

    msgs = {  # noqa: RUF012
        "E9501": (
            "stormfuse.jobs and stormfuse.ffmpeg may not import stormfuse.ui (%s)",
            "stormfuse-forbidden-ui-import",
            "Used when lower layers import UI code.",
        ),
        "E9502": (
            "Only stormfuse.ffmpeg and stormfuse.ui.menu_actions may import subprocess (%s)",
            "stormfuse-forbidden-subprocess-import",
            "Used when modules outside the ffmpeg boundary import subprocess.",
        ),
        "E9503": (
            "stormfuse.core may not import stormfuse.ui or stormfuse.jobs (%s)",
            "stormfuse-forbidden-core-upward-import",
            "Used when core imports UI or job-layer code.",
        ),
        "E9504": (
            "stormfuse.ffmpeg and stormfuse.jobs may not import stormfuse.core (%s)",
            "stormfuse-forbidden-core-import",
            "Used when ffmpeg or jobs import core code.",
        ),
    }

    def visit_import(self, node: nodes.Import) -> None:
        module_name = node.root().name
        if not _is_stormfuse_module(module_name):
            return

        for imported_name, _alias in node.names:
            if _is_jobs_or_ffmpeg_module(module_name) and _targets_ui(imported_name):
                self.add_message(
                    "stormfuse-forbidden-ui-import",
                    node=node,
                    args=(node.as_string(),),
                )
            if _is_core_module(module_name) and _targets_ui_or_jobs(imported_name):
                self.add_message(
                    "stormfuse-forbidden-core-upward-import",
                    node=node,
                    args=(node.as_string(),),
                )
            if _is_jobs_or_ffmpeg_module(module_name) and _targets_core(imported_name):
                self.add_message(
                    "stormfuse-forbidden-core-import",
                    node=node,
                    args=(node.as_string(),),
                )
            if not _subprocess_import_allowed(module_name) and _targets_subprocess(imported_name):
                self.add_message(
                    "stormfuse-forbidden-subprocess-import",
                    node=node,
                    args=(node.as_string(),),
                )

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        module_name = node.root().name
        if not _is_stormfuse_module(module_name):
            return

        imported_module = _resolve_import_from(module_name, node.modname, node.level or 0)
        if _is_jobs_or_ffmpeg_module(module_name) and (
            _targets_ui(imported_module)
            or (imported_module == _STORMFUSE_ROOT and _imports_name(node, "ui"))
        ):
            self.add_message(
                "stormfuse-forbidden-ui-import",
                node=node,
                args=(node.as_string(),),
            )

        if _is_core_module(module_name) and (
            _targets_ui_or_jobs(imported_module)
            or (
                imported_module == _STORMFUSE_ROOT
                and (_imports_name(node, "ui") or _imports_name(node, "jobs"))
            )
        ):
            self.add_message(
                "stormfuse-forbidden-core-upward-import",
                node=node,
                args=(node.as_string(),),
            )

        if _is_jobs_or_ffmpeg_module(module_name) and (
            _targets_core(imported_module)
            or (imported_module == _STORMFUSE_ROOT and _imports_name(node, "core"))
        ):
            self.add_message(
                "stormfuse-forbidden-core-import",
                node=node,
                args=(node.as_string(),),
            )

        if not _subprocess_import_allowed(module_name) and _targets_subprocess(imported_module):
            self.add_message(
                "stormfuse-forbidden-subprocess-import",
                node=node,
                args=(node.as_string(),),
            )


def register(linter: PyLinter) -> None:
    """Register the checker with pylint."""

    linter.register_checker(StormFuseLayeringChecker(linter))


def _imports_name(node: nodes.ImportFrom, target_name: str) -> bool:
    return any(imported_name == target_name for imported_name, _alias in node.names)


def _resolve_import_from(current_module: str, imported_module: str, level: int) -> str:
    if level == 0:
        return imported_module

    package_name = current_module.rpartition(".")[0]
    package_parts = package_name.split(".") if package_name else []
    up_levels = max(level - 1, 0)
    if up_levels >= len(package_parts):
        resolved_base = ""
    else:
        resolved_base = ".".join(package_parts[: len(package_parts) - up_levels])

    if resolved_base and imported_module:
        return f"{resolved_base}.{imported_module}"
    return resolved_base or imported_module


def _is_stormfuse_module(module_name: str) -> bool:
    return module_name == _STORMFUSE_ROOT or module_name.startswith(f"{_STORMFUSE_ROOT}.")


def _is_jobs_or_ffmpeg_module(module_name: str) -> bool:
    return _is_package_or_submodule(module_name, _FFMPEG_ROOT) or _is_package_or_submodule(
        module_name, _JOBS_ROOT
    )


def _is_core_module(module_name: str) -> bool:
    return _is_package_or_submodule(module_name, _CORE_ROOT)


def _subprocess_import_allowed(module_name: str) -> bool:
    return (
        _is_package_or_submodule(module_name, _FFMPEG_ROOT) or module_name == _MENU_ACTIONS_MODULE
    )


def _targets_ui(imported_name: str) -> bool:
    return _is_package_or_submodule(imported_name, _UI_ROOT)


def _targets_ui_or_jobs(imported_name: str) -> bool:
    return _targets_ui(imported_name) or _is_package_or_submodule(imported_name, _JOBS_ROOT)


def _targets_core(imported_name: str) -> bool:
    return _is_package_or_submodule(imported_name, _CORE_ROOT)


def _targets_subprocess(imported_name: str) -> bool:
    return _is_package_or_submodule(imported_name, _SUBPROCESS_MODULE)


def _is_package_or_submodule(module_name: str, package_root: str) -> bool:
    return module_name == package_root or module_name.startswith(f"{package_root}.")
