"""MainWindow Player-tab wiring - Spec 15 (Phase B), TC-15-24 / 27 / 28 / 29 / 30.

These drive the real Player synchronously: `set_source` / `source` are
synchronous and `Player.ended` can be emitted directly (Spec 15 §Test contract),
so no audio backend / teardown hang is involved. State that needs a "playing"
assertion is not required here - the observable wiring is source / now-playing
title / Up Next highlight, all synchronous.
"""

from __future__ import annotations

from album_builder.ui.queue_pane import QueuePane


# Spec: TC-15-24
def test_two_tabs_album_builder_and_player(main_window) -> None:
    tabs = main_window.tabs
    assert tabs.count() == 2
    assert tabs.tabText(0) == "Album Builder"
    assert tabs.tabText(1) == "Player"
    assert tabs.currentIndex() == 0                       # default tab
    assert isinstance(tabs.widget(1), QueuePane)
    assert tabs.widget(1) is main_window.queue_pane
    # The curation splitter lives under the first tab.
    assert tabs.widget(0).isAncestorOf(main_window.splitter)


# Spec: TC-15-28
def test_play_all_drives_controller_end_to_end(main_window) -> None:
    view_tracks = main_window.library_pane.view_order_tracks()
    first = view_tracks[0]
    main_window.library_pane.play_tracks_requested.emit(view_tracks, 0)
    # Player loaded the first track (observable source).
    assert main_window._player.source() == first.path
    # now-playing pane title updated via current_changed.
    assert main_window.now_playing_pane.title_label.text() == first.title
    # Up Next list rebuilt and highlight pulled to slot 0.
    assert main_window.queue_pane.list.count() == len(view_tracks)
    assert main_window.queue_pane.list.currentRow() == 0


# Spec: TC-15-29
def test_auto_advance_updates_now_playing_and_highlight(main_window) -> None:
    view_tracks = main_window.library_pane.view_order_tracks()
    main_window.library_pane.play_tracks_requested.emit(view_tracks, 0)
    second = view_tracks[1]
    # The natural end-of-media pulse advances the queue.
    main_window._player.ended.emit()
    assert main_window._player.source() == second.path
    assert main_window.now_playing_pane.title_label.text() == second.title
    assert main_window.queue_pane.list.currentRow() == 1


# Spec: TC-15-27
def test_up_next_activation_jumps_and_out_of_range_is_noop(main_window) -> None:
    view_tracks = main_window.library_pane.view_order_tracks()
    main_window.library_pane.play_tracks_requested.emit(view_tracks, 0)
    main_window.queue_pane.row_activated.emit(1)
    assert main_window._player.source() == view_tracks[1].path
    # Out-of-range positions are swallowed (no IndexError to the UI).
    main_window.queue_pane.row_activated.emit(99)
    assert main_window._player.source() == view_tracks[1].path
    main_window.queue_pane.row_activated.emit(-1)
    assert main_window._player.source() == view_tracks[1].path


# Spec: TC-15-30
def test_tab_switch_is_non_destructive(main_window) -> None:
    store = main_window._store
    album = store.create(name="X", target_count=3)
    main_window.top_bar.switcher.set_current(album.id)
    first = main_window._library_watcher.library().tracks[0]
    main_window._on_selection_toggled(first.path, True)
    main_window.library_pane.play_tracks_requested.emit([first], 0)

    current_before = main_window.top_bar.switcher.current_id
    source_before = main_window._player.source()

    main_window.tabs.setCurrentIndex(1)         # to Player
    main_window.tabs.setCurrentIndex(0)         # back to Album Builder

    assert main_window.top_bar.switcher.current_id == current_before
    assert first.path in store.get(album.id).track_paths
    assert main_window._player.source() == source_before
