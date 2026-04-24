# SPDX-License-Identifier: GPL-3.0-or-later
"""Collapsible log pane showing the human-readable log mirror (§6.1, §9.2)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDockWidget,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_MAX_LINES = 2000


class LogPane(QDockWidget):
    """Dockable, collapsible pane that tails the human-readable log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Log", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(_MAX_LINES)
        font = QFont("Consolas", 9) if QFont("Consolas").exactMatch() else QFont("Monospace", 9)
        self._text.setFont(font)

        clear_btn = QPushButton("Clear pane")
        clear_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        clear_btn.clicked.connect(self._text.clear)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._text)
        layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.setWidget(inner)

    @pyqtSlot(str)
    def append_line(self, line: str) -> None:
        """Append a human-readable log line. Safe to call from any thread via signal."""
        self._text.appendPlainText(line)
        sb = self._text.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())
