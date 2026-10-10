"""The duplicate checker's result window (MUSI-0386).

Two lists, shown separately: exact copies, then likely copies. Read-only:
the app never removes a song (discovery S7), so the window says where each
file is and leaves the tidying to the file manager.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from album_builder.domain.track import Track
from album_builder.i18n import tr
from album_builder.services.duplicates import DuplicateReport


class DuplicatesDialog(QDialog):
    def __init__(
        self, report: DuplicateReport, tracks: Mapping[Path, Track], folder: Path, parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Find Duplicates..."))
        self.resize(720, 480)
        layout = QVBoxLayout(self)

        note = QLabel(tr(
            "This list only shows duplicates. The app never deletes songs: "
            "remove the copies you don't want in your file manager."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(QLabel(tr("Music folder: {folder}", folder=str(folder))))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("File"), tr("Title"), tr("Artist")])
        self._add_section(
            tr("Exact copies (the same file more than once): {count}",
               count=len(report.exact)),
            report.exact, tracks,
        )
        self._add_section(
            tr("Likely copies (same title and artist): {count}", count=len(report.likely)),
            report.likely, tracks,
        )
        if report.unreadable:
            self._add_section(
                tr("Could not be read: {count}", count=len(report.unreadable)),
                tuple((p,) for p in report.unreadable), tracks,
            )
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        layout.addWidget(self.tree)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_section(
        self, heading: str, groups: tuple[tuple[Path, ...], ...], tracks: Mapping[Path, Track],
    ) -> None:
        section = QTreeWidgetItem(self.tree, [heading])
        section.setFirstColumnSpanned(True)
        for group in groups:
            parent = section
            if len(group) > 1:
                parent = QTreeWidgetItem(
                    section, [tr("{count} copies", count=len(group))],
                )
                parent.setFirstColumnSpanned(True)
            for path in group:
                track = tracks.get(path)
                QTreeWidgetItem(parent, [
                    path.name,
                    track.title if track else "",
                    track.artist if track else "",
                ])
