# SPDX-License-Identifier: GPL-3.0-or-later
"""Global exception, Qt-message, signal, and fault handlers for StormFuse."""

from __future__ import annotations

import faulthandler
import logging
import signal
import sys
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType, TracebackType
from typing import TextIO

from PyQt6.QtCore import (
    QCoreApplication,
    QMessageLogContext,
    QTimer,
    QtMsgType,
    qInstallMessageHandler,
)

from stormfuse.config import LOG_DIR

log = logging.getLogger("stormfuse.error_handling")


@dataclass
class _HandlerState:
    fault_log_handle: TextIO | None = None
    previous_qt_message_handler: (
        Callable[[QtMsgType, QMessageLogContext, str | None], None] | None
    ) = None


_STATE = _HandlerState()


@dataclass(frozen=True)
class UnhandledError:
    """Structured payload describing an unexpected application failure."""

    title: str
    event: str
    summary: str
    why: str
    next_step: str
    stderr_tail: str


@dataclass(frozen=True)
class PreviousCrashReport:
    """Fatal crash artifact from the previous run."""

    path: Path
    content: str
    truncated: bool


def snapshot_previous_fatal_log(log_dir: Path = LOG_DIR) -> PreviousCrashReport | None:
    """Move a previous fatal crash log aside before this session starts."""
    fatal_log_path = log_dir / "fatal_errors.log"
    try:
        if not fatal_log_path.is_file() or fatal_log_path.stat().st_size == 0:
            return None
        content = fatal_log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if "Windows fatal exception" not in content and "Fatal Python error" not in content:
        return None

    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    snapshot_path = log_dir / f"fatal_errors-{stamp}.log"
    try:
        snapshot_path.write_text(content, encoding="utf-8")
        fatal_log_path.write_text("", encoding="utf-8")
    except OSError:
        return PreviousCrashReport(
            path=fatal_log_path,
            content=content,
            truncated=_fatal_log_looks_truncated(content),
        )

    return PreviousCrashReport(
        path=snapshot_path,
        content=content,
        truncated=_fatal_log_looks_truncated(content),
    )


def install_sys_hook(
    show_dialog: Callable[[UnhandledError], None] | None = None,
) -> Callable[[type[BaseException], BaseException, TracebackType | None], None]:
    """Install and return the top-level sys exception hook."""

    def handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        stderr_tail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log.error(
            "Unhandled exception: %s: %s",
            exc_type.__name__,
            exc_value,
            extra={
                "event": "app.unhandled",
                "ctx": {"stderr_tail": stderr_tail.splitlines()[-20:]},
            },
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        _flush_log_handlers()
        if show_dialog is not None:
            show_dialog(
                UnhandledError(
                    title="StormFuse — Unexpected Error",
                    event="app.unhandled",
                    summary="StormFuse hit an unexpected error on the UI thread.",
                    why=f"{exc_type.__name__}: {exc_value}",
                    next_step=(
                        "Copy the diagnostic bundle, then restart StormFuse and "
                        "retry the last action."
                    ),
                    stderr_tail=stderr_tail,
                )
            )

    sys.excepthook = handle_exception
    return handle_exception


def install_thread_hook(
    show_dialog: Callable[[UnhandledError], None] | None = None,
) -> Callable[[threading.ExceptHookArgs], None]:
    """Install and return the threading exception hook."""

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        exc_type = args.exc_type
        exc_value = args.exc_value or RuntimeError("Unknown thread exception")
        exc_traceback = args.exc_traceback
        stderr_tail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log.error(
            "Unhandled thread exception: %s: %s",
            exc_type.__name__,
            exc_value,
            extra={
                "event": "app.thread_unhandled",
                "ctx": {
                    "thread_name": args.thread.name if args.thread is not None else None,
                    "stderr_tail": stderr_tail.splitlines()[-20:],
                },
            },
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        _flush_log_handlers()
        if show_dialog is not None:
            QTimer.singleShot(
                0,
                lambda: show_dialog(
                    UnhandledError(
                        title="StormFuse — Background Thread Error",
                        event="app.thread_unhandled",
                        summary="StormFuse hit an unexpected background-thread error.",
                        why=f"{exc_type.__name__}: {exc_value}",
                        next_step=(
                            "Copy the diagnostic bundle, then restart StormFuse before retrying."
                        ),
                        stderr_tail=stderr_tail,
                    )
                ),
            )

    threading.excepthook = handle_thread_exception
    return handle_thread_exception


def install_qt_message_handler() -> Callable[[QtMsgType, QMessageLogContext, str | None], None]:
    """Install and return a Qt message handler that forwards into logging."""

    def handle_qt_message(
        msg_type: QtMsgType,
        context: QMessageLogContext,
        message: str | None,
    ) -> None:
        level_map = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }
        message_type = {
            QtMsgType.QtDebugMsg: "debug",
            QtMsgType.QtInfoMsg: "info",
            QtMsgType.QtWarningMsg: "warning",
            QtMsgType.QtCriticalMsg: "critical",
            QtMsgType.QtFatalMsg: "fatal",
        }.get(msg_type, "unknown")

        text = str(message).strip()
        if text:
            log.log(
                level_map.get(msg_type, logging.INFO),
                "Qt message",
                extra={
                    "event": "app.qt_message",
                    "ctx": {
                        "type": message_type,
                        "category": getattr(context, "category", ""),
                        "file": getattr(context, "file", ""),
                        "line": getattr(context, "line", 0),
                        "function": getattr(context, "function", ""),
                        "message": text,
                    },
                },
            )
            if msg_type == QtMsgType.QtFatalMsg:
                _flush_log_handlers()

        if _STATE.previous_qt_message_handler is not None:
            _STATE.previous_qt_message_handler(msg_type, context, message)

    _STATE.previous_qt_message_handler = qInstallMessageHandler(handle_qt_message)
    return handle_qt_message


def enable_fault_handler(log_dir: Path = LOG_DIR) -> None:
    """Enable faulthandler output to a dedicated crash log."""

    if _STATE.fault_log_handle is not None:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    fault_log_path = log_dir / "fatal_errors.log"
    fault_file = fault_log_path.open("a", encoding="utf-8")
    fault_file.write(
        "\n".join(
            [
                f"StormFuse fatal log session: {datetime.now(UTC).isoformat()}",
                f"Platform: {sys.platform}",
                f"Python: {sys.version}",
                "",
            ]
        )
    )
    fault_file.flush()
    faulthandler.enable(file=fault_file, all_threads=True)
    _STATE.fault_log_handle = fault_file
    log.info(
        "Fault handler enabled",
        extra={"event": "app.fault", "ctx": {"path": str(fault_log_path)}},
    )


def truncate_active_fault_log(path: Path = LOG_DIR / "fatal_errors.log") -> bool:
    """Truncate the active faulthandler file if it is open for this process."""
    handle = _STATE.fault_log_handle
    if handle is None:
        return False
    try:
        if getattr(handle, "name", None) != str(path):
            return False
        handle.seek(0)
        handle.truncate()
        handle.flush()
    except (AttributeError, OSError, ValueError):
        return False
    return True


def install_signal_hooks() -> None:
    """Install SIGINT/SIGTERM handlers that log and quit the Qt app cleanly."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            continue


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    signal_name = signal.Signals(signum).name
    log.info(
        "Application received a termination signal",
        extra={"event": "app.signal", "ctx": {"signal": signal_name, "signum": signum}},
    )
    _flush_log_handlers()
    app = QCoreApplication.instance()
    if app is not None:
        QTimer.singleShot(0, app.quit)


def _flush_log_handlers() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        try:
            handler.flush()
        except Exception:
            continue


def _fatal_log_looks_truncated(content: str) -> bool:
    if "File Windows fatal exception" in content:
        return True
    stripped = content.rstrip()
    if not stripped:
        return False
    return not (
        stripped.endswith("Extension modules:")
        or stripped.endswith("Current thread")
        or "most recent call first" in stripped
    )
