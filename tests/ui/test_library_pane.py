from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.library import Library
from album_builder.ui.library_pane import LibraryPane


@pytest.fixture
def populated_pane(qtbot, tracks_dir: Path):
    lib = Library.scan(tracks_dir)
    pane = LibraryPane()
    pane.set_library(lib)
    qtbot.addWidget(pane)
    return pane, lib


def test_library_pane_shows_all_tracks(populated_pane) -> None:
    pane, lib = populated_pane
    assert pane.row_count() == len(lib.tracks)


def test_library_pane_search_filters(populated_pane, qtbot) -> None:
    pane, _lib = populated_pane
    pane.search_box.setText("intro")
    qtbot.wait(50)
    assert pane.row_count() == 1


def test_library_pane_search_clear_restores_all(populated_pane, qtbot) -> None:
    pane, lib = populated_pane
    pane.search_box.setText("nope-nothing-matches")
    qtbot.wait(50)
    assert pane.row_count() == 0
    pane.search_box.setText("")
    qtbot.wait(50)
    assert pane.row_count() == len(lib.tracks)


def test_library_pane_sort_by_title(populated_pane) -> None:
    pane, _lib = populated_pane
    pane.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    titles = [pane.title_at(i) for i in range(pane.row_count())]
    assert titles == sorted(titles, key=str.lower)


def test_track_table_model_data_handles_out_of_range_row() -> None:
    """A stale proxy index after set_tracks() reset can ask the model for a
    row that no longer exists. Bare IndexError bubbles into Qt's C++ slot
    dispatch with no useful traceback. The model must return None instead."""
    from PyQt6.QtCore import Qt

    from album_builder.ui.library_pane import TrackTableModel

    model = TrackTableModel([])
    # Hand-craft an index pointing at row 5 of an empty model — this is
    # what happens when the proxy hasn't seen the model reset yet.
    bogus = model.createIndex(5, 0)
    assert model.data(bogus, Qt.ItemDataRole.DisplayRole) is None


# Spec: TC-01-09
def test_library_pane_default_sort_is_title_ascending(populated_pane) -> None:
    """Spec 01: 'Default sort: Title ascending'. The pane must apply this at
    construction time so the user sees a deterministic order on first launch."""
    pane, _lib = populated_pane
    titles = [pane.title_at(i) for i in range(pane.row_count())]
    assert titles == sorted(titles, key=str.lower)


# Spec: TC-01-15
def test_library_pane_search_matches_album_artist(populated_pane, qtbot) -> None:
    """Per Spec 01: search covers title, artist, album_artist, composer, album.

    All 3 fixture tracks share album_artist='18 Down'; track 03 (drift) has
    artist='Other Artist' so its album_artist is the only field that hits.
    The search must surface all 3, not just the 2 whose displayed artist
    column also says '18 Down'."""
    pane, _lib = populated_pane
    pane.search_box.setText("18 down")
    qtbot.wait(50)
    assert pane.row_count() == 3


# Spec: TC-04-14
def test_at_target_disables_off_toggles(populated_pane, qtbot) -> None:
    from album_builder.domain.album import Album
    pane, lib = populated_pane
    a = Album.create(name="x", target_count=2)
    a.select(lib.tracks[0].path)
    a.select(lib.tracks[1].path)  # now at target
    pane.set_current_album(a)
    assert pane.toggle_enabled_at(0) is True   # ON: still enabled (deselect path)
    assert pane.toggle_enabled_at(1) is True
    assert pane.toggle_enabled_at(2) is False  # OFF + at target: disabled


# Spec: TC-04-15
def test_below_target_re_enables_off_toggles(populated_pane) -> None:
    from album_builder.domain.album import Album
    pane, lib = populated_pane
    a = Album.create(name="x", target_count=2)
    a.select(lib.tracks[0].path)
    a.select(lib.tracks[1].path)
    pane.set_current_album(a)
    assert pane.toggle_enabled_at(2) is False
    a.deselect(lib.tracks[1].path)
    pane.set_current_album(a)  # re-render
    assert pane.toggle_enabled_at(2) is True


# Spec: TC-04-16
def test_approved_album_disables_all_toggles(populated_pane) -> None:
    from album_builder.domain.album import Album, AlbumStatus
    pane, lib = populated_pane
    a = Album.create(name="x", target_count=3)
    a.select(lib.tracks[0].path)
    a.status = AlbumStatus.APPROVED
    pane.set_current_album(a)
    assert pane.toggle_enabled_at(0) is False  # even ON ones lock when approved


# Spec: TC-04-18
def test_selected_row_has_accent_strip(populated_pane) -> None:
    from album_builder.domain.album import Album
    pane, lib = populated_pane
    a = Album.create(name="x", target_count=3)
    a.select(lib.tracks[0].path)
    pane.set_current_album(a)
    assert pane.row_accent_at(0) == "primary"
    assert pane.row_accent_at(1) is None


# Spec: TC-04-19
def test_missing_selected_row_has_warning_accent(populated_pane, tracks_dir: Path) -> None:
    """Spec 04 visual rules row 5: a selected row whose track is missing
    on disk renders the accent strip in `warning` (amber), not `primary`."""
    from album_builder.domain.album import Album
    from album_builder.domain.track import Track

    pane, lib = populated_pane
    real = lib.tracks[0]
    missing = Track(
        path=real.path, title=real.title, artist=real.artist,
        album_artist=real.album_artist, album=real.album, composer=real.composer,
        comment=real.comment, lyrics_text=real.lyrics_text,
        cover_data=real.cover_data, cover_mime=real.cover_mime,
        duration_seconds=real.duration_seconds, is_missing=True,
        file_size_bytes=getattr(real, "file_size_bytes", 0),
    )
    pane._model.set_tracks([missing, *lib.tracks[1:]])
    a = Album.create(name="x", target_count=3)
    a.select(missing.path)
    pane.set_current_album(a)
    assert pane.row_accent_at(0) == "warning"
    a.select(lib.tracks[1].path)
    pane.set_current_album(a)
    assert pane.row_accent_at(1) == "primary"


# Indie-review L5-H1: Spec 00 §Sort order requires case-insensitive locale-aware
# comparison, not raw codepoint. casefold() handles German ß, Turkish I, etc.
def test_sort_role_returns_casefolded_strings(populated_pane) -> None:
    from PyQt6.QtCore import Qt

    from album_builder.ui.library_pane import COLUMNS, TrackTableModel

    pane, lib = populated_pane
    model: TrackTableModel = pane._model
    # Find the first non-toggle column (Title at index 0).
    idx = model.index(0, 0)
    title_sort_key = model.data(idx, Qt.ItemDataRole.UserRole)
    track = lib.tracks[0]
    assert title_sort_key == track.title.casefold()
    # Toggle column gets a tuple sort key (selected, casefolded-name).
    toggle_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_toggle")
    toggle_sort_key = model.data(model.index(0, toggle_col), Qt.ItemDataRole.UserRole)
    assert isinstance(toggle_sort_key, tuple)
    assert isinstance(toggle_sort_key[0], bool)


# Indie-review L5-H4: AccessibleTextRole must say "selected" / "not selected",
# not the raw glyph (Spec 11 / WCAG 2.2 §4.1.2).
def test_toggle_column_accessible_text_describes_state(populated_pane) -> None:
    from PyQt6.QtCore import Qt

    from album_builder.domain.album import Album
    from album_builder.ui.library_pane import COLUMNS

    pane, lib = populated_pane
    a = Album.create(name="x", target_count=3)
    a.select(lib.tracks[0].path)
    pane.set_current_album(a)
    toggle_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_toggle")
    selected_idx = pane._model.index(0, toggle_col)
    text = pane._model.data(selected_idx, Qt.ItemDataRole.AccessibleTextRole)
    assert text.startswith("selected: ")
    unselected_idx = pane._model.index(1, toggle_col)
    text = pane._model.data(unselected_idx, Qt.ItemDataRole.AccessibleTextRole)
    assert text.startswith("not selected: ")


# Indie-review L5-M7: approved-album tooltip on the toggle cell.
def test_approved_album_toggle_has_tooltip(populated_pane) -> None:
    from PyQt6.QtCore import Qt

    from album_builder.domain.album import Album, AlbumStatus
    from album_builder.ui.library_pane import COLUMNS

    pane, lib = populated_pane
    a = Album.create(name="x", target_count=3)
    a.select(lib.tracks[0].path)
    a.status = AlbumStatus.APPROVED
    pane.set_current_album(a)
    toggle_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_toggle")
    tip = pane._model.data(pane._model.index(0, toggle_col), Qt.ItemDataRole.ToolTipRole)
    assert tip is not None
    assert "approved" in tip.lower()


# Spec: TC-06-15 — preview-play column emits Path on click.
def test_library_pane_emits_preview_play_request(populated_pane) -> None:
    pane, lib = populated_pane
    captured = []
    pane.preview_play_requested.connect(captured.append)
    from album_builder.ui.library_pane import COLUMNS
    play_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_play")
    # Map source-row 0 to a proxy index (the proxy is sorted by title).
    src = pane._model.index(0, play_col)
    proxy_idx = pane._proxy.mapFromSource(src)
    pane._on_table_clicked(proxy_idx)
    track_at_row_0 = lib.tracks[0]
    assert captured == [track_at_row_0.path]


# Spec 06: preview-play does NOT toggle selection.
def test_library_pane_preview_play_does_not_toggle_selection(populated_pane) -> None:
    pane, _lib = populated_pane
    selections = []
    pane.selection_toggled.connect(lambda *a: selections.append(a))
    from album_builder.ui.library_pane import COLUMNS
    play_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_play")
    src = pane._model.index(0, play_col)
    proxy_idx = pane._proxy.mapFromSource(src)
    pane._on_table_clicked(proxy_idx)
    assert selections == []


# Tier 3: classic half-up rounding, NOT Python's banker's. A 1.5s file and a
# 2.5s file should both round AWAY from the same midpoint, not collapse onto
# the same even integer.
def test_format_duration_uses_classic_half_up_rounding() -> None:
    from album_builder.ui.library_pane import _format_duration

    # 0.5 -> 1, 1.5 -> 2, 2.5 -> 3 (classic). round() would give 0/2/2 (banker's).
    assert _format_duration(0.5) == "0:01"
    assert _format_duration(1.5) == "0:02"
    assert _format_duration(2.5) == "0:03"
    # Sanity: integer seconds unchanged, hour boundary intact.
    assert _format_duration(0) == "0:00"
    assert _format_duration(3600) == "1:00:00"


# Indie-review L6-M5 (Theme G partial closure): TrackFilterProxy used
# .lower() while AlbumStore + Library.sorted use .casefold(). The
# inconsistency surfaces as "search for 'ß' fails to match a track named
# 'Süß' on a German user's system" — the casefolded form of ß is "ss".
def test_search_uses_casefold_not_lower(qtbot, tmp_path: Path) -> None:
    from album_builder.domain.library import Library
    from album_builder.domain.track import Track
    from album_builder.ui.library_pane import LibraryPane

    track = Track(
        path=tmp_path / "song.mp3",
        title="Süß",  # German sharp-S; casefold('ß') == 'ss', lower('ß') == 'ß'
        artist="x", album_artist="x", album="", composer="", comment="",
        lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=0.0, file_size_bytes=0, is_missing=False,
    )
    pane = LibraryPane()
    pane.set_library(Library(folder=tmp_path, tracks=(track,)))
    qtbot.addWidget(pane)

    # Searching for 'ss' must match the casefolded form of 'ß' (= 'ss').
    # With .lower() both sides, "ss" is not a substring of "süß"; only
    # casefold('ß') -> 'ss' surfaces the match.
    pane.search_box.setText("ss")
    qtbot.wait(50)
    assert pane.row_count() == 1, (
        "search must use casefold() so ß is matchable by 'ss' (Theme G)"
    )


# Indie-review L6-M2: LibraryPane reaches into _model._toggle_enabled
# and ._tracks from outside the class. Underscore-private leak. Add
# public accessors that lock the contract.
def test_track_table_model_exposes_public_accessors() -> None:
    from album_builder.ui.library_pane import TrackTableModel

    model = TrackTableModel([])
    # is_toggle_enabled(row) for out-of-range -> False (or returns a bool).
    assert model.is_toggle_enabled(0) is False
    # tracks() is the public read accessor.
    assert model.tracks() == []
