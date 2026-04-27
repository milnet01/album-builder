"""Main window — top bar + three-pane horizontal splitter."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from album_builder.domain.library import Library
from album_builder.ui.library_pane import LibraryPane
from album_builder.ui.theme import Palette, qt_stylesheet
from album_builder.version import __version__


class MainWindow(QMainWindow):
    def __init__(self, library: Library):
        super().__init__()
        self.setWindowTitle(f"Album Builder {__version__}")
        self.resize(1400, 900)
        self.setStyleSheet(qt_stylesheet(Palette.dark_colourful()))

        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.top_bar = self._build_top_bar()
        outer.addWidget(self.top_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.library_pane = LibraryPane()
        self.library_pane.set_library(library)
        self.splitter.addWidget(self.library_pane)

        # Phase 1 stubs — Phase 2 fills these in
        self.album_order_pane = self._build_placeholder_pane("Album order")
        self.now_playing_pane = self._build_placeholder_pane("Now playing")
        self.splitter.addWidget(self.album_order_pane)
        self.splitter.addWidget(self.now_playing_pane)

        self.splitter.setSizes([500, 350, 550])
        outer.addWidget(self.splitter, stretch=1)

    def _build_top_bar(self) -> QFrame:
        bar = QFrame(objectName="TopBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Phase 1: placeholder dropdown stub. Phase 2 wires the real switcher.
        album_btn = QPushButton("▾ No albums (Phase 2)")
        album_btn.setEnabled(False)
        layout.addWidget(album_btn)

        layout.addStretch(1)

        approve_btn = QPushButton("✓ Approve…")
        approve_btn.setEnabled(False)
        layout.addWidget(approve_btn)

        return bar

    def _build_placeholder_pane(self, title: str) -> QFrame:
        pane = QFrame(objectName="Pane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(10, 10, 10, 10)
        title_label = QLabel(title, objectName="PaneTitle")
        layout.addWidget(title_label)
        layout.addStretch(1)
        empty = QLabel("(coming in Phase 2)")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("color: #6e717c;")
        layout.addWidget(empty)
        layout.addStretch(2)
        return pane
