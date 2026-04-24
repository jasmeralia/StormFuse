# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-size slider widget for the Compress tab (§6.3)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget


class SizeSlider(QWidget):
    """Slider from 1.0 GB to 10.0 GB in 0.1 GB steps.

    Emits value_changed(gb: float) whenever the value changes.
    """

    value_changed = pyqtSignal(float)

    _MIN_GB = 10  # 1.0 GB in tenths
    _MAX_GB = 100  # 10.0 GB in tenths
    _DEFAULT_GB = 95  # 9.5 GB

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(self._MIN_GB, self._MAX_GB)
        self._slider.setValue(self._DEFAULT_GB)
        self._slider.setTickInterval(10)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        self._gb_label = QLabel(self._format_gb(self._DEFAULT_GB))
        self._gb_label.setMinimumWidth(50)

        row = QHBoxLayout()
        row.addWidget(QLabel("1.0 GB"))
        row.addWidget(self._slider, stretch=1)
        row.addWidget(QLabel("10.0 GB"))
        row.addWidget(self._gb_label)

        self._bitrate_label = QLabel("")
        self._bitrate_label.setObjectName("bitratePreview")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self._bitrate_label)

        self._slider.valueChanged.connect(self._on_value_changed)

    def _format_gb(self, tenths: int) -> str:
        return f"{tenths / 10:.1f} GB"

    def _on_value_changed(self, tenths: int) -> None:
        self._gb_label.setText(self._format_gb(tenths))
        self.value_changed.emit(tenths / 10.0)

    def gb_value(self) -> float:
        return self._slider.value() / 10.0

    def set_bitrate_preview(self, bitrate_k: int) -> None:
        if bitrate_k > 0:
            self._bitrate_label.setText(f"≈ {bitrate_k:,} kbps video")
        else:
            self._bitrate_label.setText("Target too small for this duration")

    def setToolTip(self, tooltip: str) -> None:  # type: ignore[override]
        self._slider.setToolTip(tooltip)
        super().setToolTip(tooltip)
