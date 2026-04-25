# SPDX-License-Identifier: GPL-3.0-or-later
"""JSON Lines + human-mirror logging for StormFuse (§9).

Two handlers are attached to the root logger:
  - JsonLinesHandler  → session log file (JSON Lines, one object per line)
  - HumanMirrorHandler → in-memory queue consumed by the UI log pane

Neither handler imports PyQt6; the UI reads from the queue.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import queue
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from stormfuse.config import LOG_DIR, MAX_LOG_FILES
from stormfuse.error_handling import truncate_active_fault_log


class JsonLinesFormatter(logging.Formatter):
    """Format a LogRecord as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        ts = (
            datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z"
        )

        obj: dict[str, object] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.name),
            "msg": record.getMessage(),
        }

        for extra in ("job_id", "ctx", "error", "phase", "pct"):
            val = getattr(record, extra, None)
            if val is not None:
                obj[extra] = val

        if record.exc_info:
            obj["error"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(obj, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Format a LogRecord as a compact human-readable line."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S.%f")[:-3]
        event = getattr(record, "event", record.name)
        job_id = getattr(record, "job_id", None)
        ctx = getattr(record, "ctx", None)

        job_part = f" [{job_id[:8]}]" if job_id else ""
        msg = record.getMessage()

        ctx_parts = ""
        if isinstance(ctx, dict):
            ctx_parts = "  " + "  ".join(f"{k}={v}" for k, v in ctx.items() if k != "argv")

        level = record.levelname[:5].ljust(5)
        logger = record.name[:20].ljust(20)
        return f"{ts} {level} {logger}{job_part} {event}  {msg}{ctx_parts}"


class JsonLinesHandler(logging.FileHandler):
    """Writes JSON Lines to the session log file."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(str(path), encoding="utf-8")
        self.setFormatter(JsonLinesFormatter())


class HumanMirrorHandler(logging.Handler):
    """Puts human-readable log lines into a queue for UI consumption."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(HumanReadableFormatter())
        self.queue: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._callbacks: list[Callable[[str], None]] = []

    def subscribe(self, callback: Callable[[str], None]) -> None:
        self._callbacks.append(callback)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            self.queue.put(line)
            for cb in self._callbacks:
                with contextlib.suppress(Exception):
                    cb(line)
        except Exception:
            self.handleError(record)


class _LoggingState:
    """Module-level singleton holding live handler references."""

    human: HumanMirrorHandler | None = None
    json_: JsonLinesHandler | None = None


_state = _LoggingState()
_active_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "stormfuse_active_job_id",
    default=None,
)


def bind_job_id(job_id: str) -> contextvars.Token[str | None]:
    """Bind *job_id* to the current execution context."""
    return _active_job_id.set(job_id)


def reset_job_id(token: contextvars.Token[str | None]) -> None:
    """Restore the previous bound job ID for the current context."""
    _active_job_id.reset(token)


def current_job_id() -> str | None:
    """Return the job ID bound to the current execution context, if any."""
    return _active_job_id.get()


def setup_logging() -> tuple[JsonLinesHandler, HumanMirrorHandler]:
    """Initialize logging for the current session. Call once at app start."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    _prune_old_logs()

    now = datetime.now()
    pid = os.getpid()
    session_name = f"stormfuse-{now.strftime('%Y%m%d-%H%M%S')}-{pid}.log"
    session_path = LOG_DIR / session_name
    latest_path = LOG_DIR / "latest.log"

    json_handler = JsonLinesHandler(session_path)
    json_handler.setLevel(logging.DEBUG)

    human_handler = HumanMirrorHandler()
    human_handler.setLevel(logging.DEBUG)

    _state.json_ = json_handler
    _state.human = human_handler

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(json_handler)
    root.addHandler(human_handler)

    latest_path.write_text("", encoding="utf-8")
    latest_handler = JsonLinesHandler(latest_path)
    latest_handler.setLevel(logging.DEBUG)
    root.addHandler(latest_handler)

    log = logging.getLogger("stormfuse.logging_setup")
    log.info(
        "Logging initialized",
        extra={
            "event": "app.logging.init",
            "ctx": {"session_log": str(session_path), "pid": pid, "python": sys.version},
        },
    )

    return json_handler, human_handler


def get_human_handler() -> HumanMirrorHandler | None:
    return _state.human


def _prune_old_logs() -> None:
    """Keep only the MAX_LOG_FILES most recent session logs."""
    try:
        logs = sorted(
            LOG_DIR.glob("stormfuse-*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in logs[MAX_LOG_FILES:]:
            with contextlib.suppress(OSError):
                old.unlink()
    except OSError:
        pass


def clear_log_files() -> dict[str, int]:
    """Clear all log files (§9.4). Returns counts of deleted/truncated/failed."""
    log = logging.getLogger("stormfuse.logging_setup")
    deleted = truncated = failed = 0

    open_paths: set[str] = set()
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and h.stream is not None:
            open_paths.add(h.baseFilename)

    try:
        all_files = list(LOG_DIR.glob("*"))
    except OSError:
        return {"deleted": 0, "truncated": 0, "failed": 1}

    for p in all_files:
        if str(p) in open_paths:
            try:
                for h in root.handlers:
                    if (
                        isinstance(h, logging.FileHandler)
                        and h.baseFilename == str(p)
                        and h.stream is not None
                    ):
                        h.stream.seek(0)
                        h.stream.truncate()
                        h.stream.flush()
                truncated += 1
            except OSError:
                failed += 1
        elif p.name == "fatal_errors.log" and _truncate_active_fault_log(p):
            truncated += 1
        else:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                failed += 1
                log.warning(
                    "Failed to delete log file",
                    extra={"event": "logs.clear.partial", "ctx": {"path": str(p)}},
                )

    log.info(
        "Log files cleared",
        extra={
            "event": "logs.clear",
            "ctx": {"deleted": deleted, "truncated": truncated, "failed": failed},
        },
    )
    return {"deleted": deleted, "truncated": truncated, "failed": failed}


def _truncate_active_fault_log(path: Path) -> bool:
    return truncate_active_fault_log(path)
