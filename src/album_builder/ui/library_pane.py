"""Library pane — search box + sortable table of tracks."""

from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtWidgets import QFrame, QHeaderView, QLabel, QLineEdit, QTableView, QVBoxLayout

from album_builder.domain.library import Library
from album_builder.domain.track import Track

COLUMNS: list[tuple[str, str]] = [
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Composer", "composer"),
    ("Duration", "duration_seconds"),
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

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
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
        value = getattr(track, attr)
        if role == Qt.ItemDataRole.DisplayRole:
            if attr == "duration_seconds":
                return _format_duration(float(value))
            return str(value)
        if role == Qt.ItemDataRole.UserRole:
            return value  # raw value for sort comparison
        return None


def _format_duration(seconds: float) -> str:
    total = round(seconds)
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


class LibraryPane(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Library", objectName="PaneTitle")
        layout.addWidget(title)

        self.search_box = QLineEdit(placeholderText="🔍  search title, artist, album, composer…")
        self.search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_box)

        self._model = TrackTableModel([])
        self._proxy = TrackFilterProxy()
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Spec 01: default sort is Title ascending. Applied here so the user
        # sees a deterministic order on first launch — without this, rows
        # appear in filesystem-walk order.
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.table)

    def set_library(self, library: Library) -> None:
        self._model.set_tracks(library.tracks)

    def row_count(self) -> int:
        return self._proxy.rowCount()

    def title_at(self, view_row: int) -> str:
        idx = self._proxy.index(view_row, 0)
        return self._proxy.data(idx, Qt.ItemDataRole.DisplayRole)

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_needle(text)
