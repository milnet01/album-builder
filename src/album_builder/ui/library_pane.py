"""Library pane -- search box + sortable table of tracks."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
)

from album_builder.domain.album import Album, AlbumStatus
from album_builder.domain.library import Library
from album_builder.domain.track import Track
from album_builder.ui.theme import Glyphs, Palette

if TYPE_CHECKING:
    from album_builder.services.usage_index import UsageIndex

# Mirror of `MISSING_ROLE` / `TITLE_ROLE` in album_order_pane.py: per-pane
# user-role offsets above Qt.ItemDataRole.UserRole, named so callers don't
# need to know the offset arithmetic. ACCENT_ROLE returns "primary" /
# "warning" / None for the QSS attribute selector at paint time.
ACCENT_ROLE = Qt.ItemDataRole.UserRole + 2


def _plain_text_safe(name: str) -> str:
    """Return `name` HTML-escaped for safe QToolTip embedding.

    Qt's QToolTip auto-detects rich text via `Qt.mightBeRichText` (a
    fast heuristic that flags strings containing tag-like patterns).
    Escaping unconditionally means an album named `<b>Loud</b>` shows
    up as literal `&lt;b&gt;Loud&lt;/b&gt;` rather than rendered HTML;
    plain ASCII names pass through unchanged. Spec 13 §Tooltip + TC-13-30.

    `Qt.convertFromPlainText` is NOT used here - it wraps in `<p>` tags
    and substitutes non-breaking spaces, which is right for full-body
    conversion but wrong for per-line list items embedded in a parent
    multi-line string.
    """
    import html
    return html.escape(name, quote=False)


def _build_usage_tooltip(album_ids, store) -> str | None:
    """Build the Used-column tooltip body for a track on N approved albums.

    Looks up each album's name from the store at call time (lazy - so a
    rename between rebuild and tooltip-show reflects on next hover). If
    `store.get(album_id)` returns None (album removed in a race), the
    id is silently skipped. If the resulting list is empty, returns
    None (Qt suppresses the tooltip).

    Names are sorted case-insensitively. Each line is indented with two
    spaces and prefixed by `Glyphs.MIDDOT`. HTML-like names are made
    plain-text-safe via `_plain_text_safe`.

    Spec 13 §Tooltip + TC-13-12, 20, 29, 30.
    """
    names: list[str] = []
    for aid in album_ids:
        album = store.get(aid)
        if album is None:
            continue  # race tolerance: album removed mid-cascade
        names.append(album.name)
    if not names:
        return None
    names.sort(key=str.casefold)
    safe_names = [_plain_text_safe(n) for n in names]
    body = "\n".join(f"  {Glyphs.MIDDOT} {n}" for n in safe_names)
    return f"Used in approved albums:\n{body}"


COLUMNS: list[tuple[str, str]] = [
    ("▶", "_play"),   # PLAY glyph - Spec 06 per-row preview-play
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Composer", "composer"),
    ("Duration", "duration_seconds"),
    ("✓", "_toggle"),
    ("Used", "_used"),   # Spec 13 - cross-album popularity badge
]

# Spec 01: search filters across title, artist, album_artist, composer, album.
# album_artist is not a displayed column, so the proxy must consult the
# underlying Track rather than the model's DisplayRole strings.
SEARCH_FIELDS: tuple[str, ...] = (
    "title", "artist", "album_artist", "composer", "album",
)


class TrackTableModel(QAbstractTableModel):
    def __init__(self, tracks: Sequence[Track]):
        super().__init__()
        self._tracks: list[Track] = list(tracks)
        self._selected_paths: set[Path] = set()
        self._toggle_enabled: list[bool] = []
        self._album_status: AlbumStatus = AlbumStatus.DRAFT
        # Spec 06 TC-06-17/18/19: per-row preview-play button is a
        # load-or-toggle. The play column's glyph + a11y text reflect
        # whether *this* track is the active+playing source.
        self._active_path: Path | None = None
        self._active_playing: bool = False
        # Spec 13 §Self-exclusion: when the current album is itself
        # approved, exclude its id from cross-album counts. None when
        # current is a draft (no exclusion) or no album is selected.
        self._current_album_id: UUID | None = None
        # Spec 13 §Layer placement: live reference to the UsageIndex.
        # None until LibraryPane.__init__ wires it via set_usage_index.
        self._usage_index: UsageIndex | None = None

    def set_tracks(self, tracks: Sequence[Track]) -> None:
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
        self, *,
        selected_paths: set[Path],
        status: AlbumStatus,
        target: int,
        current_album_id: UUID | None = None,
    ) -> None:
        self.beginResetModel()
        self._selected_paths = selected_paths
        self._album_status = status
        # Spec 13 §Self-exclusion: stored on every set_album_state so the
        # existing reset envelope carries the new exclusion target for
        # the Used column without a separate dataChanged emit.
        self._current_album_id = current_album_id
        at_target = len(selected_paths) >= target
        is_approved = status == AlbumStatus.APPROVED
        self._toggle_enabled = [
            (not is_approved) and (track.path in selected_paths or not at_target)
            for track in self._tracks
        ]
        self.endResetModel()

    def set_usage_index(self, usage_index: UsageIndex) -> None:
        """Inject the UsageIndex reference. Called once from LibraryPane.__init__.

        Live reference, not snapshot - subsequent data() calls read live
        counts via usage_index.count_for(...). Spec 13 §Behavior rules.
        """
        self._usage_index = usage_index

    def track_at(self, row: int) -> Track:
        return self._tracks[row]

    # Public read accessors so external code (LibraryPane, tests) does not
    # have to reach into `_tracks` / `_toggle_enabled` (L6-M2 closure).

    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def is_toggle_enabled(self, row: int) -> bool:
        if row < 0 or row >= len(self._toggle_enabled):
            return False
        return self._toggle_enabled[row]

    def selected_paths(self) -> set[Path]:
        return set(self._selected_paths)

    def set_active_play_state(self, path: Path | None, playing: bool) -> None:
        """Mark `path` as the active source and whether it is currently
        playing. Emits dataChanged for the play column on the previously-
        active and newly-active rows only — Spec 06 TC-06-19's
        "rest of the list re-renders nothing" observable.
        """
        prev_path = self._active_path
        prev_playing = self._active_playing
        if prev_path == path and prev_playing == playing:
            return
        self._active_path = path
        self._active_playing = playing
        play_col = next(
            i for i, c in enumerate(COLUMNS) if c[1] == "_play"
        )
        rows: set[int] = set()
        for i, t in enumerate(self._tracks):
            if t.path == prev_path or t.path == path:
                rows.add(i)
        for r in rows:
            idx = self.index(r, play_col)
            self.dataChanged.emit(idx, idx)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            # Spec 13 §Accessibility: descriptive accessible name for the
            # new Used column; other columns return the visible header
            # string so this role extension does not silently regress
            # screen-reader behaviour on the rest of the header.
            attr = COLUMNS[section][1]
            if attr == "_used":
                return "Cross-album reuse count"
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
            # Spec 06 per-row preview-play. TC-06-19: the row whose track
            # is the active source AND state == PLAYING shows the PAUSE
            # glyph + "Pause <title>" a11y text — a click pauses the
            # source. Every other row shows PLAY + "Preview-play <title>".
            is_active_playing = (
                self._active_playing and track.path == self._active_path
            )
            if role == Qt.ItemDataRole.DisplayRole:
                return Glyphs.PAUSE if is_active_playing else Glyphs.PLAY
            if role == Qt.ItemDataRole.AccessibleTextRole:
                if is_active_playing:
                    return f"Pause {track.title}"
                return f"Preview-play {track.title}"
            if role == Qt.ItemDataRole.ToolTipRole:
                if is_active_playing:
                    return "Pause this track"
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
                return Glyphs.TOGGLE_ON if selected else Glyphs.TOGGLE_OFF
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
            if role == ACCENT_ROLE:
                if selected:
                    return "warning" if track.is_missing else "primary"
                return None
            return None

        # Spec 13 §Behavior rules: explicit early-return discipline for
        # the _used column. Every role must be handled here (or return
        # None); the post-branch getattr(track, "_used") fallthrough
        # below would raise AttributeError because Track has no _used
        # attribute. (TC-13-28.)
        if attr == "_used":
            usage = self._usage_index
            if usage is None:
                # Defensive: model queried before the index was injected
                # (shouldn't happen in normal flow). Behave as count == 0.
                count = 0
            else:
                count = usage.count_for(
                    track.path, exclude=self._current_album_id,
                )
            if role == Qt.ItemDataRole.DisplayRole:
                return "" if count == 0 else str(count)
            if role == Qt.ItemDataRole.UserRole:        # sort role
                return count
            if role == Qt.ItemDataRole.AccessibleTextRole:
                if count == 0:
                    return ""
                if count == 1:
                    return "Used in 1 other approved album"
                return f"Used in {count} other approved albums"
            if role == Qt.ItemDataRole.ToolTipRole:
                if count == 0 or usage is None:
                    return None
                ids = usage.album_ids_for(
                    track.path, exclude=self._current_album_id,
                )
                return _build_usage_tooltip(ids, usage.store)
            if role == ACCENT_ROLE:
                return None  # Used column doesn't participate in accent strip
            return None  # any other role: explicit None, never fall through

        # Non-toggle column ACCENT_ROLE surfaces accent so the whole row
        # picks it up via the QSS attribute selector at paint time.
        if role == ACCENT_ROLE:
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
        # L6-M5 (Theme G closure): casefold instead of lower so search
        # matches the same Unicode-aware comparison the rest of the app
        # uses (AlbumStore.list, Library.sorted, model sort role).
        # casefold('ß') == 'ss', lower('ß') == 'ß' — affects German users.
        self._needle = text.strip().casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._needle:
            return True
        model = self.sourceModel()
        if not isinstance(model, TrackTableModel):
            return True
        track = model.track_at(source_row)
        for field in SEARCH_FIELDS:
            if self._needle in str(getattr(track, field, "")).casefold():
                return True
        return False


def _column_index(name: str) -> int:
    """Lookup column index by its `_attr` name. Lets call-sites avoid
    hard-coding integers that drift when the column list changes."""
    return next(i for i, c in enumerate(COLUMNS) if c[1] == name)


class UsageBadgeDelegate(QStyledItemDelegate):
    """Paints the cross-album popularity badge for the Used column.

    Spec 13 §The badge: filled rounded-rectangle pill with the integer
    count when DisplayRole is non-empty; no-op (delegates to super)
    when DisplayRole is empty (count == 0).

    sizeHint() returns super().sizeHint(...) so row height is governed
    by the existing row-height heuristic, not the badge.

    Constructor accepts an optional `palette` mirroring the LyricsPanel
    construct-with-optional-palette idiom (ui/lyrics_panel.py:49-52);
    defaults to `Palette.dark_colourful()` for back-compat with
    construction-without-palette tests.
    """

    _PILL_RADIUS = 10
    _PILL_FONT_SIZE_PX = 11
    _PILL_FONT_WEIGHT = 600

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        palette: Palette | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette or Palette.dark_colourful()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            super().paint(painter, option, index)
            return

        fill_colour = QColor(self._palette.accent_primary_1)
        text_colour = QColor("#ffffff")

        cell = option.rect
        pill_w = min(22, cell.width() - 4)
        pill_h = min(16, cell.height() - 2)
        pill_x = cell.x() + (cell.width() - pill_w) // 2
        pill_y = cell.y() + (cell.height() - pill_h) // 2
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(fill_colour))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pill_rect, self._PILL_RADIUS, self._PILL_RADIUS)

        font = QFont(painter.font())
        font.setPixelSize(self._PILL_FONT_SIZE_PX)
        font.setWeight(QFont.Weight(self._PILL_FONT_WEIGHT))
        painter.setFont(font)
        painter.setPen(text_colour)
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, str(text))
        painter.restore()

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex,
    ) -> QSize:
        return super().sizeHint(option, index)


class LibraryPane(QFrame):
    selection_toggled = pyqtSignal(object, bool)        # Type: Path, new_state
    preview_play_requested = pyqtSignal(object)         # Type: Path
    # Spec 06 TC-06-20/21: row-body click (anywhere in the row outside the
    # play column or the toggle column) emits this signal so MainWindow can
    # decide whether to populate the now-playing pane (only when the player
    # is STOPPED). Layered on top of the existing preview_play / toggle
    # signals — those still fire from their own columns independently.
    row_body_clicked = pyqtSignal(object)               # Type: Path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Library", objectName="PaneTitle")
        layout.addWidget(title)

        self.search_box = QLineEdit(
            placeholderText=f"{Glyphs.SEARCH}  search title, artist, album, composer…",
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
        # Spec 13 §The badge: column-scoped delegate attachment.
        # Never setItemDelegate (which would repaint other cells).
        used_col = _column_index("_used")
        self.table.setItemDelegateForColumn(
            used_col, UsageBadgeDelegate(self.table),
        )
        self.table.setColumnWidth(used_col, 40)
        self.table.setMinimumWidth(450)
        # Spec 01: default sort is Title ascending.
        self.table.sortByColumn(title_col, Qt.SortOrder.AscendingOrder)
        self.table.clicked.connect(self._on_table_clicked)
        # Keyboard parity with mouse: Enter / Return on a focused toggle cell
        # toggles the selection. Without this, a keyboard-only user (WCAG
        # 2.2 §2.1.1) cannot operate the column. Spec 06 TC-06-25 says the
        # row-body preview path is **click-only** (Enter does NOT preview),
        # so Enter routes through `_on_table_activated` which only handles
        # the _play and _toggle columns.
        self.table.activated.connect(self._on_table_activated)
        self.table.setAccessibleName("Track library")
        self.table.setAccessibleDescription(
            "Searchable list of tracks. First column previews playback; "
            "last column toggles inclusion in the current album.",
        )
        layout.addWidget(self.table)

    def set_library(self, library: Library) -> None:
        self._model.set_tracks(library.tracks)

    def set_usage_index(self, usage_index: UsageIndex) -> None:
        """Inject the UsageIndex reference and connect the changed signal.

        Called once from MainWindow.__init__ after the index has been
        constructed and seeded. Spec 13 §Behavior rules.
        """
        self._model.set_usage_index(usage_index)
        usage_index.changed.connect(self._on_usage_changed)

    def _on_usage_changed(self) -> None:
        """Repaint the Used column on UsageIndex.changed.

        Empty-table guard: skip the emit when rowCount == 0 (the bottom-
        right index would be invalid, undefined behaviour under PyQt6
        debug builds). If the proxy's active sort column is Used,
        invalidate the proxy so the rebuilt counts re-sort.

        Spec 13 §Outputs (column-scoped path).
        """
        n = self._model.rowCount()
        if n == 0:
            return
        used_col = _column_index("_used")
        top_left = self._model.index(0, used_col)
        bottom_right = self._model.index(n - 1, used_col)
        self._model.dataChanged.emit(top_left, bottom_right, [])
        if self._proxy.sortColumn() == used_col:
            self._proxy.invalidate()

    def set_active_play_state(self, path: Path | None, playing: bool) -> None:
        """Spec 06 TC-06-17/18/19 — surface the player's active+playing state
        so the play-column glyph mirrors it. Pure pass-through; the model
        owns the diff + dataChanged emit."""
        self._model.set_active_play_state(path, playing)

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
        return self._model.is_toggle_enabled(source_row)

    def row_accent_at(self, source_row: int) -> str | None:
        # Operates on source-model rows (independent of the proxy's sort).
        # Use the title column for the lookup — the play column has its own
        # role table that doesn't include ACCENT_ROLE, so column 0 (play)
        # would always return None. The model's `data()` returns
        # `tuple[bool, str]` for the toggle column's sort role (Tier 2 fix
        # L5-H2); narrowing here protects this method's contract — title
        # column never returns the toggle-sort tuple, so `isinstance(value,
        # str)` is the right guard.
        src = self._model.index(source_row, _column_index("title"))
        if not src.isValid():
            return None
        value = self._model.data(src, ACCENT_ROLE)
        return value if isinstance(value, str) else None

    def _on_table_clicked(self, view_index: QModelIndex) -> None:
        if not view_index.isValid():
            return
        col_attr = COLUMNS[view_index.column()][1]
        src = self._proxy.mapToSource(view_index)
        row = src.row()
        if row >= self._model.rowCount():
            return
        if col_attr == "_play":
            track = self._model.track_at(row)
            self.preview_play_requested.emit(track.path)
            return
        if col_attr == "_toggle":
            if not self._model.is_toggle_enabled(row):
                return
            track = self._model.track_at(row)
            was_selected = track.path in self._model.selected_paths()
            self.selection_toggled.emit(track.path, not was_selected)
            return
        # Spec 06 TC-06-20/21: row-body click on any other column emits
        # row_body_clicked. MainWindow gates the preview behaviour on
        # Player.state() == STOPPED.
        track = self._model.track_at(row)
        self.row_body_clicked.emit(track.path)

    def _on_table_activated(self, view_index: QModelIndex) -> None:
        """Keyboard activation (Enter / Return). Routes only to the _play
        and _toggle columns; row-body activation is suppressed (Spec 06
        TC-06-25 — preview-without-play is mouse-click-only)."""
        if not view_index.isValid():
            return
        col_attr = COLUMNS[view_index.column()][1]
        if col_attr in ("_play", "_toggle"):
            self._on_table_clicked(view_index)

    def set_row_body_cursor_for_state(self, *, stopped: bool) -> None:
        """Spec 06 TC-06-26: PointingHandCursor when the player is STOPPED
        (preview-without-play is enabled), default cursor otherwise."""
        viewport = self.table.viewport()
        if viewport is None:
            return
        viewport.setCursor(
            Qt.CursorShape.PointingHandCursor if stopped else Qt.CursorShape.ArrowCursor
        )

    def row_count(self) -> int:
        return self._proxy.rowCount()

    def title_at(self, view_row: int) -> str:
        idx = self._proxy.index(view_row, _column_index("title"))
        return self._proxy.data(idx, Qt.ItemDataRole.DisplayRole)

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_needle(text)
