# SPDX-License-Identifier: GPL-3.0-or-later
"""Application startup: logging, NVENC probe, main window (§5.3, §9)."""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from stormfuse import __version__
from stormfuse.config import APP_NAME, APP_VERSION
from stormfuse.ffmpeg.encoders import detect_encoder
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


def run_app() -> int:
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Winds of Storm")

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
    window: MainWindow | None = None

    # Install top-level exception handler
    def _excepthook(
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        stderr_tail = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        log.error(
            "Unhandled exception",
            extra={
                "event": "app.unhandled",
                "error": {
                    "type": exc_type.__name__,
                    "message": str(exc_val),
                    "traceback": stderr_tail,
                },
            },
        )
        show_diagnostic_dialog(
            None,
            title="StormFuse — Unexpected Error",
            message=f"An unexpected error occurred: {exc_type.__name__}: {exc_val}",
            event="app.unhandled",
            stderr_tail=stderr_tail,
            encoder=window.current_encoder() if window is not None else encoder,
            guidance=DiagnosticGuidance(
                summary="StormFuse hit an unexpected error on the UI thread.",
                why=f"{exc_type.__name__}: {exc_val}",
                next_step=(
                    "Copy the diagnostic bundle, then restart StormFuse and retry the last action."
                ),
            ),
        )

    sys.excepthook = _excepthook

    window = MainWindow(ffmpeg_exe, ffprobe_exe, encoder)
    window.show()

    exit_code = app.exec()

    log.info("Application exiting", extra={"event": "app.exit", "ctx": {"exit_code": exit_code}})
    return exit_code
