# SPDX-License-Identifier: GPL-3.0-or-later
"""Application startup: logging, NVENC probe, main window (§5.3, §9)."""

from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from stormfuse import __version__
from stormfuse.config import APP_NAME, APP_VERSION, ORG_NAME
from stormfuse.error_handling import (
    UnhandledError,
    enable_fault_handler,
    install_qt_message_handler,
    install_signal_hooks,
    install_sys_hook,
    install_thread_hook,
)
from stormfuse.ffmpeg.encoders import EncoderChoice, detect_encoder
from stormfuse.ffmpeg.locator import FfmpegNotFoundError, ffmpeg_path, ffprobe_path, icons_dir
from stormfuse.logging_setup import setup_logging
from stormfuse.ui.error_dialogs import (
    TROUBLESHOOTING_URL,
    DiagnosticAction,
    DiagnosticGuidance,
    show_diagnostic_dialog,
)
from stormfuse.ui.main_window import MainWindow

log = logging.getLogger("stormfuse.app")


class ExceptionHookingApplication(QApplication):
    """QApplication variant that forwards swallowed Qt exceptions to sys.excepthook."""

    def notify(self, receiver: QObject | None, event: QEvent | None) -> bool:
        try:
            return super().notify(receiver, event)
        except Exception as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
            return False


def run_app() -> int:
    setup_logging()
    window: MainWindow | None = None
    encoder: EncoderChoice | None = None

    def _show_unhandled_error(error: UnhandledError) -> None:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        show_diagnostic_dialog(
            window,
            title=error.title,
            message=error.why,
            event=error.event,
            stderr_tail=error.stderr_tail,
            encoder=window.current_encoder() if window is not None else encoder,
            guidance=DiagnosticGuidance(
                summary=error.summary,
                why=error.why,
                next_step=error.next_step,
            ),
        )

    install_sys_hook(_show_unhandled_error)
    install_thread_hook()
    enable_fault_handler()

    app = ExceptionHookingApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)
    install_qt_message_handler()
    install_signal_hooks()

    try:
        icons = icons_dir()
        icon_path = icons / "stormfuse.png"
        if not icon_path.exists():
            icon_path = icons / "stormfuse.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
    except FileNotFoundError:
        pass

    log.info(
        "Application starting",
        extra={
            "event": "app.start",
            "ctx": {
                "version": __version__,
                "platform": sys.platform,
                "python": sys.version,
            },
        },
    )

    # Locate bundled ffmpeg
    try:
        ffmpeg_exe = ffmpeg_path()
        ffprobe_exe = ffprobe_path()
    except FfmpegNotFoundError as exc:
        log.error(
            "Bundled ffmpeg could not be located",
            extra={"event": "app.ffmpeg_missing", "ctx": {"error": str(exc)}},
        )
        show_diagnostic_dialog(
            None,
            title="StormFuse — Missing ffmpeg",
            message=str(exc),
            event="app.ffmpeg_missing",
            guidance=DiagnosticGuidance(
                summary="StormFuse could not start because the bundled ffmpeg files are missing.",
                why=str(exc),
                next_step=(
                    "If you are running from source, run 'make fetch-ffmpeg'. "
                    "If this is an installed copy, reinstall StormFuse or open Troubleshooting."
                ),
            ),
            action=DiagnosticAction(
                label="Open Troubleshooting",
                url=TROUBLESHOOTING_URL,
            ),
        )
        return 1

    # NVENC probe
    encoder = detect_encoder(ffmpeg_exe)
    window = MainWindow(ffmpeg_exe, ffprobe_exe, encoder)
    window.show()

    exit_code = app.exec()

    log.info("Application exiting", extra={"event": "app.exit", "ctx": {"exit_code": exit_code}})
    return exit_code
