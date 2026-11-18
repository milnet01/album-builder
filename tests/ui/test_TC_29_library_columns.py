"""Heart and play-count columns in the Player tab's song list - Spec 29 §4.5
(TC-29-14, TC-29-16)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle

from album_builder.domain.library import Library
from album_builder.domain.play_history import SongStats
from album_builder.domain.track import Track
from album_builder.persistence.play_history_io import save_history
from album_builder.services.play_history import PlayHistory
from album_builder.services.player import Player
from album_builder.ui.library_pane import COLUMNS, LibraryPane, _column_index
from album_builder.ui.theme import Glyphs

T0 = datetime(2026, 11, 18, tzinfo=UTC)


def _track(path: Path) -> Track:
    return Track(
        path=path, title=path.stem, artist="A", album_artist="A", composer="",
        album="", comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=100.0, file_size_bytes=1, is_missing=False,
    )


class _SingleClickActivates(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, return_data=None):
        if hint == QStyle.StyleHint.SH_ItemView_ActivateItemOnSingleClick:
            return 1
        return super().styleHint(hint, option, widget, return_data)


@pytest.fixture
def setup(qtbot, tmp_path: Path):
    music = tmp_path / "music"
    tracks = [_track(music / f"{n}.mp3") for n in ("alpha", "beta", "gamma")]
    outside = _track(tmp_path / "elsewhere" / "delta.mp3")
    lib = Library(folder=music, tracks=[*tracks, outside])
    root = tmp_path / "root"
    save_history(root, {
        "alpha.mp3": SongStats(plays=1, last_played=T0),
        "beta.mp3": SongStats(plays=7, last_played=T0),
        "gamma.mp3": SongStats(favourited=T0),
    })
    history = PlayHistory(root, Player(), SimpleNamespace(library=lambda: lib))
    pane = LibraryPane(player_mode=True)
    qtbot.addWidget(pane)
    pane.resize(1200, 400)
    pane.show()
    pane.set_library(lib)
    pane.set_play_history(history)
    pane.favourite_toggled.connect(history.set_favourite)
    pane.table.sortByColumn(_column_index("title"), Qt.SortOrder.AscendingOrder)
    plays: list[object] = []
    pane.play_tracks_requested.connect(lambda *a: plays.append(a))
    pane.preview_play_requested.connect(lambda *a: plays.append(a))
    return SimpleNamespace(pane=pane, history=history, tracks=tracks, outside=outside,
                           plays=plays)


def _view_index(pane: LibraryPane, title: str, column: str):
    for row in range(pane.row_count()):
        if pane.title_at(row) == title:
            return pane.table.model().index(row, _column_index(column))
    raise AssertionError(title)


def _cell(pane: LibraryPane, title: str, column: str):
    return pane.table.model().data(_view_index(pane, title, column))


def _titles(pane: LibraryPane) -> list[str]:
    return [pane.title_at(r) for r in range(pane.row_count())]


def _click(qtbot, pane: LibraryPane, title: str, column: str = "_fav") -> None:
    rect = pane.table.visualRect(_view_index(pane, title, column))
    qtbot.mouseClick(pane.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())


def _double_click(pane: LibraryPane, title: str, column: str = "_fav") -> None:
    """The events a real double-click delivers: press, release, double-click,
    release. QTest.mouseDClick sends the double-click alone, which skips the
    first click."""
    viewport = pane.table.viewport()
    pos = QPointF(pane.table.visualRect(_view_index(pane, title, column)).center())
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    for kind, held in (
        (QEvent.Type.MouseButtonPress, left),
        (QEvent.Type.MouseButtonRelease, none),
        (QEvent.Type.MouseButtonDblClick, left),
        (QEvent.Type.MouseButtonRelease, none),
    ):
        event = QMouseEvent(
            kind, pos, viewport.mapToGlobal(pos), left, held, Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(viewport, event)


# Spec: TC-29-14
def test_columns_order_and_visibility(qtbot) -> None:
    attrs = [c[1] for c in COLUMNS]
    assert attrs[1] == "_toggle"
    assert attrs[2] == "_fav"
    assert attrs[-1] == "_used"
    assert attrs.index("_plays") == attrs.index("duration_seconds") + 1
    player, curation = LibraryPane(player_mode=True), LibraryPane()
    qtbot.addWidget(player)
    qtbot.addWidget(curation)
    for name in ("_fav", "_plays"):
        assert not player.table.isColumnHidden(_column_index(name))
        assert curation.table.isColumnHidden(_column_index(name))


# Spec: TC-29-14
def test_cells_show_history(setup) -> None:
    pane = setup.pane
    assert _cell(pane, "gamma", "_fav") == Glyphs.HEART
    assert _cell(pane, "alpha", "_fav") == Glyphs.HEART_OUTLINE
    assert _cell(pane, "beta", "_plays") == "7"
    assert _cell(pane, "gamma", "_plays") == ""
    # A song outside the music folder has a disabled heart.
    assert not _view_index(pane, "delta", "_fav").flags() & Qt.ItemFlag.ItemIsEnabled
    assert _view_index(pane, "alpha", "_fav").flags() & Qt.ItemFlag.ItemIsEnabled


@pytest.mark.parametrize("single_click_activates", [False, True])
# Spec: TC-29-14
def test_heart_click_toggles_once_and_never_plays(
    setup, qtbot, single_click_activates: bool,
) -> None:
    pane, history = setup.pane, setup.history
    if single_click_activates:
        style = _SingleClickActivates()
        pane.table.setStyle(style)
        pane._test_style = style  # keep it alive for the view's lifetime
    alpha = setup.tracks[0]
    _click(qtbot, pane, "alpha")
    assert history.stats_for(alpha).favourited is not None
    assert _cell(pane, "alpha", "_fav") == Glyphs.HEART
    assert setup.plays == []

    # A double-click toggles once (its first click) and does not play.
    toggles: list[object] = []
    pane.favourite_toggled.connect(lambda *a: toggles.append(a))
    _double_click(pane, "alpha")
    assert len(toggles) == 1
    assert history.stats_for(alpha).favourited is None
    assert setup.plays == []


# Spec: TC-29-14
def test_enter_on_heart_toggles_and_never_plays(setup, qtbot) -> None:
    pane, history = setup.pane, setup.history
    pane.table.setCurrentIndex(_view_index(pane, "beta", "_fav"))
    pane.table.setFocus()
    qtbot.keyClick(pane.table, Qt.Key.Key_Return)
    assert history.stats_for(setup.tracks[1]).favourited is not None
    assert setup.plays == []
    # Enter on another column still plays from the row (Spec 18 MP-2).
    pane.table.setCurrentIndex(_view_index(pane, "beta", "title"))
    qtbot.keyClick(pane.table, Qt.Key.Key_Return)
    assert len(setup.plays) == 1


# Spec: TC-29-14
def test_outside_song_heart_does_nothing(setup, qtbot) -> None:
    _click(qtbot, setup.pane, "delta")
    assert setup.history.stats_for(setup.outside) == SongStats()
    assert setup.plays == []


# Spec: TC-29-14
def test_sorting_and_live_refresh(setup) -> None:
    pane, history = setup.pane, setup.history
    pane.table.sortByColumn(_column_index("_fav"), Qt.SortOrder.AscendingOrder)
    assert _titles(pane) == ["gamma", "alpha", "beta", "delta"]
    # The sort follows a change while it is the sort column.
    history.set_favourite(setup.tracks[1], True)
    assert _titles(pane) == ["beta", "gamma", "alpha", "delta"]

    pane.table.sortByColumn(_column_index("_plays"), Qt.SortOrder.DescendingOrder)
    assert _titles(pane)[:2] == ["beta", "alpha"]


# Spec: TC-29-16
def test_context_menu(setup) -> None:
    pane, history = setup.pane, setup.history

    def action(title: str):
        menu = pane._build_context_menu(_view_index(pane, title, "title"))
        return next(a for a in menu.actions() if "favourites" in a.text())

    add = action("alpha")
    assert add.text() == "Add to favourites"
    add.trigger()
    assert history.stats_for(setup.tracks[0]).favourited is not None
    remove = action("alpha")
    assert remove.text() == "Remove from favourites"
    remove.trigger()
    assert history.stats_for(setup.tracks[0]).favourited is None
    assert action("gamma").text() == "Remove from favourites"
    assert not action("delta").isEnabled()
    assert setup.plays == []


# Spec: TC-29-16
def test_curation_menu_has_no_heart(qtbot, setup) -> None:
    curation = LibraryPane()
    qtbot.addWidget(curation)
    curation.set_library(Library(folder=setup.tracks[0].path.parent, tracks=setup.tracks))
    menu = curation._build_context_menu(curation.table.model().index(0, 2))
    assert not [a for a in menu.actions() if "favourites" in a.text()]
