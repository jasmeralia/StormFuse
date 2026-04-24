# SPDX-License-Identifier: GPL-3.0-or-later
"""About dialog (§2.4)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stormfuse.config import APP_VERSION
from stormfuse.ffmpeg.locator import icons_dir
from stormfuse.ui.menu_actions import open_licenses_dir

_ABOUT_TEXT = f"""\
StormFuse v{APP_VERSION}
© 2026 Morgan Blackthorne, Winds of Storm
Licensed under GPL v3.

Built with:
  Python 3.12+ (PSF-2.0)
  PyQt6 (GPL v3) — Riverbank Computing
  FFmpeg (GPL v2) — ffmpeg.org, build by gyan.dev
  PyInstaller, NSIS
  pytest, ruff, mypy, pylint

Developed with assistance from Claude (Anthropic) and Codex (OpenAI).\
"""


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About StormFuse")
        self.setModal(True)
        self.setMinimumWidth(480)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        icon_label.setFixedSize(96, 96)
        icon_label.setScaledContents(True)
        pixmap = self._load_icon_pixmap()
        if pixmap is not None:
            icon_label.setPixmap(pixmap)

        label = QLabel(_ABOUT_TEXT)

        licenses_btn = QPushButton("View Licenses")
        licenses_btn.clicked.connect(open_licenses_dir)

        github_btn = QPushButton("GitHub")
        github_btn.clicked.connect(self._open_github)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(licenses_btn)
        btn_row.addWidget(github_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_box)

        layout = QVBoxLayout(self)
        if pixmap is not None:
            layout.addWidget(icon_label)
        layout.addWidget(label)
        layout.addLayout(btn_row)

    def _load_icon_pixmap(self) -> QPixmap | None:
        try:
            icons = icons_dir()
            for name in ("stormfuse.png", "stormfuse.ico"):
                path = icons / name
                if path.exists():
                    pixmap = QPixmap(str(path))
                    if not pixmap.isNull():
                        return pixmap
        except FileNotFoundError:
            pass
        qapp = QApplication.instance()
        if isinstance(qapp, QApplication):
            win_icon = qapp.windowIcon()
            if not win_icon.isNull():
                return win_icon.pixmap(96, 96)
        return None

    def _open_github(self) -> None:
        QDesktopServices.openUrl(QUrl("https://github.com/winds-of-storm/stormfuse"))
