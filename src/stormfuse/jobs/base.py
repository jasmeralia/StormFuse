# SPDX-License-Identifier: GPL-3.0-or-later
"""Base Job class using QObject signals over a QThread (§8)."""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import traceback
from dataclasses import dataclass
from typing import NoReturn

from PyQt6.QtCore import QObject, pyqtSignal

from stormfuse.logging_setup import bind_job_id, reset_job_id

log = logging.getLogger("jobs.base")
_JOB_ID_LOCK = threading.Lock()


@dataclass
class _JobIdState:
    last_ms: int = 0
    seq: int = 0


_JOB_ID_STATE = _JobIdState()


@dataclass
class JobResult:
    job_id: str
    duration_sec: float


@dataclass
class JobError:
    job_id: str
    event: str
    message: str
    stderr_tail: str = ""


class _HandledJobFailure(Exception):
    """Internal sentinel used when a job emits its own structured failure."""

    def __init__(self, error: JobError) -> None:
        self.error = error
        super().__init__(error.message)


class Job(QObject):
    """Abstract base for all StormFuse jobs.

    Subclasses implement _run_job(). The UI creates a QThread, moves this
    object to it, and calls run() via the thread's started signal.
    """

    progress = pyqtSignal(float, str)  # 0..1, phase label
    log = pyqtSignal(dict)  # structured log event dict
    done = pyqtSignal(object)  # JobResult
    failed = pyqtSignal(object)  # JobError
    finished = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.job_id = _generate_job_id(type(self).__name__)
        self._cancel_event: threading.Event = threading.Event()
        self._run_started_at: float | None = None

    def cancel(self) -> None:
        """Signal the job to cancel. Idempotent."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def fail(self, *, event: str, message: str, stderr_tail: str = "") -> NoReturn:
        """Emit a structured failure and stop the job without also emitting done()."""
        ctx: dict[str, object] = {"cause_event": event}
        if self._run_started_at is not None:
            ctx["duration_sec"] = round(time.monotonic() - self._run_started_at, 2)
        if stderr_tail:
            ctx["stderr_tail"] = stderr_tail.splitlines()[-20:]
        log.error(
            message,
            extra={"event": "job.fail", "job_id": self.job_id, "ctx": ctx},
        )
        error = JobError(
            job_id=self.job_id,
            event=event,
            message=message,
            stderr_tail=stderr_tail,
        )
        self.failed.emit(error)
        raise _HandledJobFailure(error)

    def run(self) -> None:
        """Called by QThread.started. Dispatches to _run_job()."""
        start = time.monotonic()
        self._run_started_at = start
        job_token = bind_job_id(self.job_id)
        log.info(
            "Job started",
            extra={
                "event": "job.start",
                "job_id": self.job_id,
                "ctx": {"type": type(self).__name__},
            },
        )
        try:
            self._run_job()
        except _HandledJobFailure:
            return
        except Exception as exc:
            err = JobError(
                job_id=self.job_id,
                event="job.fail",
                message=str(exc),
                stderr_tail=traceback.format_exc(),
            )
            log.error(
                "Job failed with unhandled exception",
                extra={"event": "job.fail", "job_id": self.job_id},
                exc_info=True,
            )
            self.failed.emit(err)
            return
        else:
            if self.is_cancelled:
                log.warning(
                    "Job cancelled",
                    extra={
                        "event": "job.cancel",
                        "job_id": self.job_id,
                        "ctx": {"duration_sec": round(time.monotonic() - start, 2)},
                    },
                )
            else:
                duration = time.monotonic() - start
                log.info(
                    "Job finished",
                    extra={
                        "event": "job.finish",
                        "job_id": self.job_id,
                        "ctx": {"duration_sec": round(duration, 2)},
                    },
                )
                self.done.emit(JobResult(job_id=self.job_id, duration_sec=duration))
        finally:
            self._run_started_at = None
            reset_job_id(job_token)
            self.finished.emit()

    def _run_job(self) -> None:
        raise NotImplementedError


def _generate_job_id(class_name: str) -> str:
    """Generate a time-sortable job identifier with a job-type prefix."""
    now_ms = time.time_ns() // 1_000_000
    with _JOB_ID_LOCK:
        if now_ms == _JOB_ID_STATE.last_ms:
            _JOB_ID_STATE.seq = (_JOB_ID_STATE.seq + 1) & 0xFFFF
        else:
            _JOB_ID_STATE.last_ms = now_ms
            _JOB_ID_STATE.seq = 0
        seq = _JOB_ID_STATE.seq

    job_kind = _job_kind(class_name)
    random_bits = secrets.randbits(48)
    return f"{job_kind}-{now_ms:012x}{seq:04x}{random_bits:012x}"


def _job_kind(class_name: str) -> str:
    stem = class_name.removesuffix("Job") or "Job"
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+", stem)
    if not parts:
        return "job"
    return "-".join(part.lower() for part in parts)
