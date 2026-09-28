"""Player-tab library - Spec 18 Phase MP-2 amendment (MUSI-0356), TC-18-25..32.

The `main_window` fixture (ui/conftest.py) builds a real MainWindow over the
`tracks_dir` library. Activation is driven through `table.activated` directly
(Qt's own double-click / Enter -> activated mapping is measured in the spec).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter

from album_builder.domain.library import Library
from album_builder.services.player import PlayerState
from album_builder.ui.library_pane import COLUMNS, LibraryPane
from album_builder.ui.now_playing_card import NowPlayingCard
from album_builder.ui.theme import THEMES, palette_for


def _col(name: str) -> int:
    return next(i for i, c in enumerate(COLUMNS) if c[1] == name)


def _titles(pane: LibraryPane) -> list[str]:
    return [pane.title_at(r) for r in range(pane.row_count())]


def _activate(pane: LibraryPane, view_row: int, column: str) -> None:
    pane.table.activated.emit(pane._proxy.index(view_row, _col(column)))


# Spec: TC-18-25
def test_player_pane_hosts_its_own_library_first(main_window) -> None:
    main = main_window
    lib = main.player_library_pane
    assert isinstance(lib, LibraryPane)
    assert lib is not main.library_pane
    assert lib._player_mode is True
    splitter = next(
        s for s in main._player_pane.findChildren(QSplitter)
        if s.orientation() == Qt.Orientation.Horizontal
    )
    assert splitter.widget(0) is lib


# Spec: TC-18-26
def test_player_mode_hides_curation_columns(qtbot) -> None:
    player = LibraryPane(player_mode=True)
    curation = LibraryPane()
    qtbot.addWidget(player)
    qtbot.addWidget(curation)
    hidden = {c[1] for i, c in enumerate(COLUMNS) if player.table.isColumnHidden(i)}
    assert hidden == {"_toggle", "_used"}
    assert not any(curation.table.isColumnHidden(i) for i in range(len(COLUMNS)))


# Spec: TC-18-27
def test_both_library_panes_follow_the_one_watcher(main_window) -> None:
    main = main_window
    assert _titles(main.player_library_pane) == _titles(main.library_pane)
    assert main.player_library_pane.row_count() > 1
    old = main._library_watcher.library()
    smaller = Library(folder=old.folder, tracks=old.tracks[:1])
    main._library_watcher.tracks_changed.emit(smaller)
    assert main.player_library_pane.row_count() == 1
    assert _titles(main.player_library_pane) == _titles(main.library_pane)


# Spec: TC-18-28
def test_player_activation_plays_from_here(main_window, qtbot, monkeypatch) -> None:
    main = main_window
    lib = main.player_library_pane
    calls: list = []
    monkeypatch.setattr(
        main._controller, "play_tracks",
        lambda tracks, start_index=0: calls.append((list(tracks), start_index)),
    )
    for column in ("title", "_play"):
        with qtbot.waitSignal(lib.play_tracks_requested) as blocker:
            _activate(lib, 1, column)
        assert blocker.args == [lib.view_order_tracks(), 1]
    assert calls == [(lib.view_order_tracks(), 1)] * 2

    # A search filter narrows the payload to the filtered view.
    first_title = lib.title_at(0)
    lib.search_box.setText(first_title)
    with qtbot.waitSignal(lib.play_tracks_requested) as blocker:
        _activate(lib, 0, "title")
    assert blocker.args[0] == lib.view_order_tracks()
    assert len(blocker.args[0]) == lib.row_count()

    # The curation pane keeps its rule: title activation emits nothing.
    with qtbot.assertNotEmitted(main.library_pane.play_tracks_requested):
        _activate(main.library_pane, 0, "title")


# Spec: TC-18-29
def test_player_row_click_does_not_preview(main_window, qtbot) -> None:
    main = main_window
    lib = main.player_library_pane
    before = (
        main.now_playing_pane.card.title_label.text(),
        main._player_pane.card.title_label.text(),
    )
    with qtbot.assertNotEmitted(lib.row_body_clicked):
        lib.table.clicked.emit(lib._proxy.index(0, _col("title")))
    after = (
        main.now_playing_pane.card.title_label.text(),
        main._player_pane.card.title_label.text(),
    )
    assert after == before


# Spec: TC-18-30
def test_player_context_menu_reaches_controller(main_window, qtbot) -> None:
    main = main_window
    main._playlist_store.create("Road Trip")
    lib = main.player_library_pane
    menu = lib._build_context_menu(lib._proxy.index(0, _col("title")))
    actions = {a.text(): a for a in menu.actions()}
    with qtbot.waitSignal(main._controller.queue_changed):
        actions["Add to queue"].trigger()
    submenu = actions["Add to playlist"].menu()
    assert "Road Trip" in [a.text() for a in submenu.actions()]
    main._playlist_store.flush()


# Spec: TC-18-31
def test_play_state_and_theme_reach_both_panes(main_window, monkeypatch) -> None:
    main = main_window
    path = main.library_pane.view_order_tracks()[0].path
    monkeypatch.setattr(main._player, "source", lambda: path)
    main._on_player_state_changed_for_rows(PlayerState.PLAYING)
    assert main.library_pane._model._active_path == path
    assert main.player_library_pane._model._active_path == path

    other = next(t for t in THEMES if t != main._current_theme)
    main._apply_theme(other, persist=False)
    expected = palette_for(other)
    assert main.library_pane._usage_delegate._palette == expected
    assert main.player_library_pane._usage_delegate._palette == expected


# Spec: TC-18-32
def test_card_detail_order_title_artist_album(qtbot, tmp_path) -> None:
    card = NowPlayingCard()
    qtbot.addWidget(card)
    layout = card.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert order == [
        card.cover_label, card.title_label, card.artist_label, card.album_label,
        card.composer_label, card.comment_label, card.placeholder_label,
    ]


# Spec: TC-18-26
def test_player_mode_accessible_description(qtbot) -> None:
    pane = LibraryPane(player_mode=True)
    qtbot.addWidget(pane)
    desc = pane.table.accessibleDescription()
    assert "press Enter to play from it" in desc
    assert "toggles inclusion" not in desc

