# SPDX-License-Identifier: GPL-3.0-or-later
"""Drag-reorderable file list widget for the Combine tab (§6.2)."""

from __future__ import annotations

import locale
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QWidget,
)

from stormfuse.ffmpeg.probe import FileProbe
from stormfuse.timestamp_parser import parse_filename_timestamp


class FileListWidget(QListWidget):
    """QListWidget with drag-reorder and drop-from-Explorer support."""

    files_changed = pyqtSignal()

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._probes_by_path: dict[Path, FileProbe] = {}
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def add_paths(self, paths: list[Path]) -> None:
        """Add *paths* to the list, avoiding duplicates."""
        existing = self.all_paths()
        seen = set(existing)
        for p in paths:
            if p not in seen:
                existing.append(p)
                seen.add(p)
        self._set_paths(self._sorted_by_name(existing))

    def remove_selected(self) -> None:
        for item in self.selectedItems():
            self.takeItem(self.row(item))
        self.files_changed.emit()

    def move_up(self) -> None:
        rows = sorted({self.row(i) for i in self.selectedItems()})
        if not rows or rows[0] == 0:
            return
        for row in rows:
            item = self.takeItem(row)
            self.insertItem(row - 1, item)
            self.setCurrentItem(item)
        self.files_changed.emit()

    def move_down(self) -> None:
        rows = sorted({self.row(i) for i in self.selectedItems()}, reverse=True)
        if not rows or rows[0] == self.count() - 1:
            return
        for row in rows:
            item = self.takeItem(row)
            self.insertItem(row + 1, item)
            self.setCurrentItem(item)
        self.files_changed.emit()

    def clear_all(self) -> None:
        self.clear()
        self._probes_by_path.clear()
        self.files_changed.emit()

    def all_paths(self) -> list[Path]:
        return [self._path_for(i) for i in range(self.count())]

    def set_probe_results(self, probes_by_path: dict[Path, FileProbe]) -> None:
        self._probes_by_path = {
            path: probes_by_path[path] for path in self.all_paths() if path in probes_by_path
        }
        self._refresh_labels()

    def sort_by_name(self) -> None:
        self._set_paths(self._sorted_by_name(self.all_paths()))

    def sort_by_timestamp(self) -> None:
        paths = self.all_paths()
        timestamped = [
            (index, path, timestamp)
            for index, path in enumerate(paths)
            if (timestamp := parse_filename_timestamp(path.name)) is not None
        ]
        sorted_timestamped = iter(sorted(timestamped, key=lambda item: item[2]))
        reordered_paths = list(paths)
        for index, _, _ in timestamped:
            reordered_paths[index] = next(sorted_timestamped)[1]
        self._set_paths(reordered_paths)

    # ------------------------------------------------------------------ #
    # Drop from Explorer
    # ------------------------------------------------------------------ #

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            paths = [
                Path(url.toLocalFile())
                for url in mime.urls()
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in {".mkv", ".mp4"}
            ]
            self.add_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            self.files_changed.emit()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _append_path(self, path: Path) -> QListWidgetItem:
        item = QListWidgetItem(path.name)
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setToolTip(str(path))
        self.addItem(item)
        return item

    def _path_for(self, row: int) -> Path:
        item = self.item(row)
        assert item is not None
        return Path(item.data(Qt.ItemDataRole.UserRole))

    def _sorted_by_name(self, paths: list[Path]) -> list[Path]:
        return sorted(paths, key=lambda path: locale.strxfrm(path.name.casefold()))

    def _set_paths(self, paths: list[Path]) -> None:
        self.clear()
        for p in paths:
            self._append_path(p)
        self._probes_by_path = {
            path: self._probes_by_path[path] for path in paths if path in self._probes_by_path
        }
        self._refresh_labels()
        self.files_changed.emit()

    def _make_badge(
        self,
        text: str,
        *,
        object_name: str,
        background: str,
        foreground: str = "#f8fafc",
    ) -> QLabel:
        badge = QLabel(text)
        badge.setObjectName(object_name)
        badge.setStyleSheet(
            "QLabel {"
            f"background-color: {background};"
            f"color: {foreground};"
            "border-radius: 9px;"
            "padding: 2px 8px;"
            "font-size: 11px;"
            "font-weight: 600;"
            "}"
        )
        return badge

    def _media_badge_text(self, probe: FileProbe) -> str | None:
        if probe.video is None or probe.audio is None:
            return None
        return (
            f"{probe.video.width}x{probe.video.height}"
            f"@{probe.video.fps:.2f} {probe.video.codec}/{probe.audio.codec}"
        )

    def _build_row_widget(self, path: Path) -> QWidget:
        row_widget = QWidget(self)
        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(8)

        name_label = QLabel(path.name)
        name_label.setObjectName("basenameLabel")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name_label, stretch=1)

        timestamp = parse_filename_timestamp(path.name)
        if timestamp is None:
            warning_badge = self._make_badge(
                "⚠",
                object_name="timestampWarning",
                background="#92400e",
            )
            warning_badge.setToolTip(
                f"{path}\nNo recognizable timestamp in filename; "
                "sort-by-timestamp keeps this row anchored."
            )
            layout.addWidget(warning_badge)
        else:
            timestamp_badge = self._make_badge(
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                object_name="timestampBadge",
                background="#1d4ed8",
            )
            timestamp_badge.setToolTip(
                f"Parsed timestamp from filename: {timestamp.isoformat(sep=' ')}"
            )
            layout.addWidget(timestamp_badge)

        probe = self._probes_by_path.get(path)
        media_text = None if probe is None else self._media_badge_text(probe)
        if media_text is not None:
            media_badge = self._make_badge(
                media_text,
                object_name="probeBadge",
                background="#334155",
            )
            media_badge.setToolTip(f"Probed stream signature for {path.name}")
            layout.addWidget(media_badge)

        return row_widget

    def _refresh_labels(self) -> None:
        for row in range(self.count()):
            item = self.item(row)
            assert item is not None
            p = self._path_for(row)
            if parse_filename_timestamp(p.name) is None:
                item.setText(f"⚠ {p.name}")
                item.setToolTip(
                    f"{p}\n(No recognizable timestamp — sort-by-timestamp keeps this row anchored)"
                )
            else:
                item.setText(p.name)
                item.setToolTip(str(p))
            row_widget = self._build_row_widget(p)
            item.setSizeHint(row_widget.sizeHint())
            self.setItemWidget(item, row_widget)
