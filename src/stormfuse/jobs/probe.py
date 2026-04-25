# SPDX-License-Identifier: GPL-3.0-or-later
"""Background ffprobe jobs used by UI preflight flows (§5.1, §5.2, §8)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import pyqtSignal

from stormfuse.ffmpeg.probe import FileProbe, ProbeError
from stormfuse.jobs.base import Job

ProbeFile = Callable[[Path], FileProbe]


@dataclass(frozen=True)
class ProbeFilesResult:
    """Probe result payload with the original request context."""

    paths: list[Path]
    probes: list[FileProbe]
    request_id: int | None = None


class ProbeFilesJob(Job):
    """Probe one or more media files off the UI thread and return FileProbe objects."""

    probed = pyqtSignal(object)  # ProbeFilesResult

    def __init__(
        self,
        paths: list[Path],
        probe_file: ProbeFile,
        *,
        request_id: int | None = None,
    ) -> None:
        super().__init__()
        self._paths = list(paths)
        self._probe_file = probe_file
        self._request_id = request_id

    def _run_job(self) -> None:
        if not self._paths:
            self.probed.emit(ProbeFilesResult([], [], self._request_id))
            return

        probes: list[FileProbe] = []
        total = len(self._paths)
        for index, path in enumerate(self._paths):
            if self.is_cancelled:
                return

            self.progress.emit(index / total, f"Probing {path.name}…")
            try:
                probes.append(self._probe_file(path))
            except ProbeError as exc:
                self.fail(
                    event="probe.error",
                    message=f"Probe failed for {path.name}: {exc}",
                    stderr_tail=exc.stderr_tail,
                )
            except Exception as exc:
                self.fail(
                    event="probe.error",
                    message=f"Probe failed for {path.name}: {exc}",
                )

        if self.is_cancelled:
            return

        self.probed.emit(ProbeFilesResult(list(self._paths), probes, self._request_id))
