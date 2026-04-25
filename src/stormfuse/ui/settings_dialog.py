# SPDX-License-Identifier: GPL-3.0-or-later
"""Application settings dialog."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)

from stormfuse.ui import settings as ui_settings
from stormfuse.ui.theme import apply_widget_theme


@dataclass(frozen=True)
class SettingsValues:
    """User-editable application settings."""

    debug_ffmpeg_logging: bool
    auto_check_updates: bool
    allow_prerelease_updates: bool


class SettingsDialog(QDialog):
    """Modal settings dialog for diagnostics and update preferences."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(420, 260)

        self._debug_ffmpeg = QCheckBox("Enable debug ffmpeg logs", self)
        self._debug_ffmpeg.setObjectName("settingsDebugFfmpegLogs")
        self._debug_ffmpeg.setChecked(ui_settings.debug_ffmpeg_logging_enabled())

        self._auto_updates = QCheckBox("Check for updates at startup", self)
        self._auto_updates.setObjectName("settingsAutoCheckUpdates")
        self._auto_updates.setChecked(ui_settings.auto_check_updates_enabled())

        self._beta_updates = QCheckBox("Include beta updates", self)
        self._beta_updates.setObjectName("settingsAllowPrereleaseUpdates")
        self._beta_updates.setChecked(ui_settings.allow_prerelease_updates_enabled())

        diagnostics = QGroupBox("Diagnostics", self)
        diagnostics_layout = QVBoxLayout(diagnostics)
        diagnostics_layout.addWidget(self._debug_ffmpeg)

        updates = QGroupBox("Updates", self)
        updates_layout = QVBoxLayout(updates)
        updates_layout.addWidget(self._auto_updates)
        updates_layout.addWidget(self._beta_updates)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(diagnostics)
        layout.addWidget(updates)
        layout.addStretch(1)
        layout.addWidget(buttons)
        apply_widget_theme(self)

    def values(self) -> SettingsValues:
        """Return the currently selected settings."""
        return SettingsValues(
            debug_ffmpeg_logging=self._debug_ffmpeg.isChecked(),
            auto_check_updates=self._auto_updates.isChecked(),
            allow_prerelease_updates=self._beta_updates.isChecked(),
        )
