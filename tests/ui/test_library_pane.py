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
