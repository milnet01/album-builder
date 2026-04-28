"""Library pane -- search box + sortable table of tracks."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHeaderView, QLabel, QLineEdit, QTableView, QVBoxLayout

from album_builder.domain.album import Album, AlbumStatus
from album_builder.domain.library import Library
from album_builder.domain.track import Track
from album_builder.ui.theme import Glyphs

COLUMNS: list[tuple[str, str]] = [
    ("▶", "_play"),   # PLAY glyph - Spec 06 per-row preview-play
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Composer", "composer"),
    ("Duration", "duration_seconds"),
    ("✓", "_toggle"),
]

# Spec 01: search filters across title, artist, album_artist, composer, album.
# album_artist is not a displayed column, so the proxy must consult the
# underlying Track rather than the model's DisplayRole strings.
SEARCH_FIELDS: tuple[str, ...] = (
    "title", "artist", "album_artist", "composer", "album",
)


class TrackTableModel(QAbstractTableModel):
    def __init__(self, tracks: list[Track]):
        super().__init__()
        self._tracks: list[Track] = list(tracks)
        self._selected_paths: set[Path] = set()
        self._toggle_enabled: list[bool] = []
        self._album_status: AlbumStatus = AlbumStatus.DRAFT

    def set_tracks(self, tracks: list[Track]) -> None:
        # Contract: set_tracks() resets only the per-row enable cache,
        # NOT _selected_paths. Selection state belongs to the active album
        # and is owned by set_album_state(); a library-watcher refresh
        # (filesystem change) doesn't change the album's selection. Path
        # equality is value-based, so a Track that vanishes from disk and
        # reappears at the same path stays correctly selected. The
        # appropriate caller (MainWindow) reapplies album state after a
        # library refresh by calling set_current_album() if the active
        # album's view of the library needs to follow the watcher.
        self.beginResetModel()
        self._tracks = list(tracks)
        self._toggle_enabled = [True] * len(self._tracks)
        self.endResetModel()

    def set_album_state(
        self, *, selected_paths: set[Path], status: AlbumStatus, target: int,
    ) -> None:
        self.beginResetModel()
        self._selected_paths = selected_paths
        self._album_status = status
        at_target = len(selected_paths) >= target
        is_approved = status == AlbumStatus.APPROVED
        self._toggle_enabled = [
            (not is_approved) and (track.path in selected_paths or not at_target)
            for track in self._tracks
        ]
        self.endResetModel()

    def track_at(self, row: int) -> Track:
        return self._tracks[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        # A stale proxy index that survives a set_tracks() reset can point
        # past the end of the new list. Returning None lets Qt skip the cell
        # rather than letting a Python IndexError leak into C++ slot dispatch.
        if index.row() >= len(self._tracks):
            return None
        track = self._tracks[index.row()]
        attr = COLUMNS[index.column()][1]
        is_approved = self._album_status == AlbumStatus.APPROVED

        if attr == "_play":
            # Spec 06 per-row preview-play.
            if role == Qt.ItemDataRole.DisplayRole:
                return Glyphs.PLAY
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"Preview-play {track.title}"
            if role == Qt.ItemDataRole.ToolTipRole:
                return "Preview-play this track"
            if role == Qt.ItemDataRole.UserRole:
                # Sortable but uninformative; group by title casefold so a
                # header click on this column doesn't crash. Spec 06 doesn't
                # define a useful sort for this column.
                return track.title.casefold()
            return None

        if attr == "_toggle":
            selected = track.path in self._selected_paths
            if role == Qt.ItemDataRole.DisplayRole:
                return "●" if selected else "○"
            if role == Qt.ItemDataRole.AccessibleTextRole:
                # Spec 11 / WCAG 2.2 §4.1.2: screen readers should hear
                # "selected" / "not selected", not "black circle".
                return f"{'selected' if selected else 'not selected'}: {track.title}"
            if role == Qt.ItemDataRole.ToolTipRole and is_approved:
                # Spec 04 row state table: approved -> non-interactive tooltip.
                return "Album is approved; reopen for editing to change selection."
            if role == Qt.ItemDataRole.UserRole:
                # Sort key for the toggle column - keep selected rows together.
                return (selected, track.path.name.casefold())
            if role == Qt.ItemDataRole.UserRole + 2:
                if selected:
                    return "warning" if track.is_missing else "primary"
                return None
            return None

        # Non-toggle column UserRole+2 surfaces accent so the whole row
        # picks it up via the QSS attribute selector at paint time.
        if role == Qt.ItemDataRole.UserRole + 2:
            if track.path in self._selected_paths:
                return "warning" if track.is_missing else "primary"
            return None

        value = getattr(track, attr)
        if role == Qt.ItemDataRole.DisplayRole:
            if attr == "duration_seconds":
                return _format_duration(float(value))
            return str(value)
        if role == Qt.ItemDataRole.UserRole:
            # Sort key. Spec 00 §Sort order: case-insensitive locale-aware.
            # casefold() is the Unicode-aware lower (handles German ß, Turkish
            # I, etc.); raw codepoint sort would have Z < a and Polish ł > z.
            return value.casefold() if isinstance(value, str) else value
        return None


def _format_duration(seconds: float) -> str:
    # Classic half-up rounding (NOT round()'s banker's rounding) — users
    # expect 0.5s -> 1s, 1.5s -> 2s, etc., consistently. round() in Python
    # is half-to-even (1.5 -> 2 but 2.5 -> 2), which surfaces as a one-
    # second jitter in displayed durations of identically-encoded files.
    total = int(seconds + 0.5)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class TrackFilterProxy(QSortFilterProxyModel):
    """Proxy that filters by a substring against every Track field in
    SEARCH_FIELDS, including album_artist (which is not a displayed column)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle: str = ""

    def set_needle(self, text: str) -> None:
        self._needle = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._needle:
            return True
        model = self.sourceModel()
        if not isinstance(model, TrackTableModel):
            return True
        track = model.track_at(source_row)
        for field in SEARCH_FIELDS:
            if self._needle in str(getattr(track, field, "")).lower():
                return True
        return False


def _column_index(name: str) -> int:
    """Lookup column index by its `_attr` name. Lets call-sites avoid
    hard-coding integers that drift when the column list changes."""
    return next(i for i, c in enumerate(COLUMNS) if c[1] == name)


class LibraryPane(QFrame):
    selection_toggled = pyqtSignal(object, bool)        # Type: Path, new_state
    preview_play_requested = pyqtSignal(object)         # Type: Path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Library", objectName="PaneTitle")
        layout.addWidget(title)

        self.search_box = QLineEdit(
            placeholderText="\U0001f50d  search title, artist, album, composer…"
        )
        self.search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_box)

        self._model = TrackTableModel([])
        self._proxy = TrackFilterProxy()
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self._current_album: Album | None = None

        title_col = _column_index("title")
        play_col = _column_index("_play")
        toggle_col = _column_index("_toggle")

        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        # Title gets the leftover space; metadata columns size to content.
        header = self.table.horizontalHeader()
        for col in range(len(COLUMNS)):
            if col == title_col:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        # Default widths by name (resilient to column reorder).
        self.table.setColumnWidth(play_col, 30)
        self.table.setColumnWidth(_column_index("artist"), 140)
        self.table.setColumnWidth(_column_index("album"), 160)
        self.table.setColumnWidth(_column_index("composer"), 140)
        self.table.setColumnWidth(_column_index("duration_seconds"), 70)
        self.table.setColumnWidth(toggle_col, 30)
        self.table.setMinimumWidth(450)
        # Spec 01: default sort is Title ascending.
        self.table.sortByColumn(title_col, Qt.SortOrder.AscendingOrder)
        self.table.clicked.connect(self._on_table_clicked)
        # Keyboard parity with mouse: Enter / Return on a focused toggle cell
        # toggles the selection. Without this, a keyboard-only user (WCAG
        # 2.2 §2.1.1) cannot operate the column.
        self.table.activated.connect(self._on_table_clicked)
        self.table.setAccessibleName("Track library")
        self.table.setAccessibleDescription(
            "Searchable list of tracks. First column previews playback; "
            "last column toggles inclusion in the current album.",
        )
        layout.addWidget(self.table)

    def set_library(self, library: Library) -> None:
        self._model.set_tracks(library.tracks)

    def set_current_album(self, album: Album | None) -> None:
        self._current_album = album
        if album is None:
            self._model.set_album_state(
                selected_paths=set(), status=AlbumStatus.DRAFT, target=0,
            )
        else:
            self._model.set_album_state(
                selected_paths=set(album.track_paths),
                status=album.status,
                target=album.target_count,
            )

    def toggle_enabled_at(self, source_row: int) -> bool:
        # Operates on source-model rows (independent of the proxy's sort).
        # Real user clicks go through `_on_table_clicked`, which maps view->source.
        if source_row >= len(self._model._toggle_enabled):
            return False
        return self._model._toggle_enabled[source_row]

    def row_accent_at(self, source_row: int) -> str | None:
        # Operates on source-model rows (independent of the proxy's sort).
        # Use the title column for the lookup — the play column has its own
        # role table that doesn't include UserRole+2, so column 0 (play)
        # would always return None.
        src = self._model.index(source_row, _column_index("title"))
        if not src.isValid():
            return None
        return self._model.data(src, Qt.ItemDataRole.UserRole + 2)

    def _on_table_clicked(self, view_index: QModelIndex) -> None:
        if not view_index.isValid():
            return
        col_attr = COLUMNS[view_index.column()][1]
        src = self._proxy.mapToSource(view_index)
        row = src.row()
        if row >= len(self._model._tracks):
            return
        if col_attr == "_play":
            track = self._model.track_at(row)
            self.preview_play_requested.emit(track.path)
            return
        if col_attr != "_toggle":
            return
        if row >= len(self._model._toggle_enabled) or not self._model._toggle_enabled[row]:
            return
        track = self._model.track_at(row)
        was_selected = track.path in self._model._selected_paths
        self.selection_toggled.emit(track.path, not was_selected)

    def row_count(self) -> int:
        return self._proxy.rowCount()

    def title_at(self, view_row: int) -> str:
        idx = self._proxy.index(view_row, _column_index("title"))
        return self._proxy.data(idx, Qt.ItemDataRole.DisplayRole)

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_needle(text)
