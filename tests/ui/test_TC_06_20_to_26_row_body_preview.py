"""Spec 06 TC-06-20..26 - row-body click previews-without-playing when idle.

Click on a library/order row outside the play button + selection toggle
populates the now-playing pane (cover, metadata, lyrics if a fresh LRC)
WITHOUT calling Player.set_source / play, but only when Player.state()
is STOPPED. PLAYING / PAUSED / ERROR clicks are no-ops at the playback
layer (selection-toggle clicks still operate independently).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.track import Track
from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.player import PlayerState
from album_builder.ui.library_pane import COLUMNS
from album_builder.ui.main_window import MainWindow


def _col(name: str) -> int:
    for i, (_, attr) in enumerate(COLUMNS):
        if attr == name:
            return i
    raise AssertionError(f"library_pane.COLUMNS has no {name} column")


def _ord_track(stem: str) -> Track:
    return Track(
        path=Path(f"/abs/{stem}.mp3"),
        title=stem,
        artist="x",
        album_artist="x",
        album="",
        composer="",
        comment="",
        lyrics_text=None,
        cover_data=None,
        cover_mime=None,
        duration_seconds=10.0,
        file_size_bytes=0,
        is_missing=False,
    )


@pytest.fixture
def main_window(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    # Default: no track was ever played, so player is STOPPED with no source.
    return win


# ---------- TC-06-20 -----------------------------------------------------

# Spec: TC-06-20 — row-body click on a library row, with player STOPPED,
# populates the now-playing pane and does not call set_source / play.
def test_row_body_click_when_stopped_populates_now_playing(main_window, qtbot, monkeypatch) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)
    assert tracks, "fixture must have at least one track"

    # Force player to STOPPED. (Construction may have left it STOPPED
    # already; this is defensive — production code path also calls
    # _on_player_state_changed_for_rows once at end of __init__.)
    assert win._player.state() == PlayerState.STOPPED

    set_source_calls: list[Path | None] = []
    monkeypatch.setattr(
        win._player, "set_source",
        lambda p: set_source_calls.append(p),
    )
    play_calls: list[None] = []
    monkeypatch.setattr(win._player, "play", lambda: play_calls.append(None))

    # Drive a row-body click via the library pane's internal handler.
    title_col = _col("title")
    proxy = win.library_pane._proxy
    view_idx = proxy.index(0, title_col)
    win.library_pane._on_table_clicked(view_idx)

    # Now-playing pane shows the row's metadata.
    src_row = proxy.mapToSource(view_idx).row()
    expected = win.library_pane._model.track_at(src_row)
    assert win.now_playing_pane.title_label.text() == expected.title, (
        f"TC-06-20: now-playing title is {win.now_playing_pane.title_label.text()!r}; "
        f"expected {expected.title!r}"
    )

    # No set_source / play call.
    assert set_source_calls == [], (
        f"TC-06-20: row-body click must not call set_source; got {set_source_calls}"
    )
    assert play_calls == [], "TC-06-20: row-body click must not call play"


# Spec: TC-06-20 — with a fresh .lrc on disk the lyrics panel populates
# statically (lines render, current-line highlight stays at -1 because no
# play() was issued, so position_changed never fires).
def test_row_body_click_when_stopped_loads_fresh_lrc(
    qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)

    # Seed a fresh LRC for the first track.
    target = next(iter(watcher.library().tracks))
    lrc = target.path.with_suffix(".lrc")
    lrc.write_text("[00:00.00]first line\n[00:01.00]second line\n", encoding="utf-8")
    import os as _os
    _os.utime(target.path, (target.path.stat().st_atime, lrc.stat().st_mtime - 10))

    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    assert win._player.state() == PlayerState.STOPPED

    title_col = _col("title")
    proxy = win.library_pane._proxy
    target_row = next(
        i for i in range(proxy.rowCount())
        if win.library_pane._model.track_at(proxy.mapToSource(proxy.index(i, 0)).row()).path
            == target.path
    )
    win.library_pane._on_table_clicked(proxy.index(target_row, title_col))

    # Lyrics list populated; the tracker's set_lyrics() initial pass
    # lands the now-line on line 0 because the LRC's first line is at
    # time_seconds=0 and the player position is 0. No further ticks
    # because play() was not issued — highlight is "stuck" on line 0
    # per spec TC-06-20.
    assert win.now_playing_pane.lyrics_panel.list.count() == 2
    assert win.now_playing_pane.lyrics_panel.current_line() == 0


# ---------- TC-06-21 -----------------------------------------------------

# Spec: TC-06-21 — row-body click is a no-op when player is PLAYING.
def test_row_body_click_when_playing_is_noop(main_window, qtbot, monkeypatch) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)

    # Load + force PLAYING via _on_preview_play (the play-button path).
    win._on_preview_play(tracks[0].path)
    qtbot.wait(50)
    win._player._state = PlayerState.PLAYING
    assert win.now_playing_pane.title_label.text() == tracks[0].title

    # Click row-body of a DIFFERENT row.
    title_col = _col("title")
    proxy = win.library_pane._proxy
    # Find the proxy index of tracks[1] in the current sort order.
    other = next(
        i for i in range(proxy.rowCount())
        if win.library_pane._model.track_at(proxy.mapToSource(proxy.index(i, 0)).row()).path
            == tracks[1].path
    )
    view_idx = proxy.index(other, title_col)
    win.library_pane._on_table_clicked(view_idx)

    # Now-playing still shows tracks[0]; player still on tracks[0].
    assert win.now_playing_pane.title_label.text() == tracks[0].title, (
        "TC-06-21: row-body click while PLAYING must not change now-playing"
    )
    assert win._player.source() == tracks[0].path


# Spec: TC-06-21 — same rule for PAUSED.
def test_row_body_click_when_paused_is_noop(main_window, qtbot, monkeypatch) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)
    win._on_preview_play(tracks[0].path)
    qtbot.wait(50)
    win._player.pause()
    qtbot.wait(50)
    assert win._player.state() == PlayerState.PAUSED

    title_col = _col("title")
    proxy = win.library_pane._proxy
    other = next(
        i for i in range(proxy.rowCount())
        if win.library_pane._model.track_at(proxy.mapToSource(proxy.index(i, 0)).row()).path
            == tracks[1].path
    )
    win.library_pane._on_table_clicked(proxy.index(other, title_col))

    assert win.now_playing_pane.title_label.text() == tracks[0].title


# ---------- TC-06-22 (album-order pane) ----------------------------------

# Spec: TC-06-22 — real mousePress on a middle-pane row widget (label
# area) emits row_body_clicked through the full plumbing.
def test_album_order_row_widget_real_press_emits_row_body_clicked(
    qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)

    tracks = list(watcher.library().tracks)
    a = store.create(name="Test", target_count=3)
    a.track_paths = [tracks[0].path, tracks[1].path]
    win.top_bar.switcher.set_current(a.id)

    # Locate the row widget for tracks[0].
    item = win.album_order_pane.list.item(0)
    row_widget = win.album_order_pane.list.itemWidget(item)
    assert row_widget is not None

    captured: list[Path] = []
    win.album_order_pane.row_body_clicked.connect(captured.append)

    # Simulate a real mousePress + Release on the row widget. Pos is
    # well within the widget so no drag-distance threshold is exceeded.
    from PyQt6.QtCore import QPoint
    qtbot.mousePress(row_widget, Qt.MouseButton.LeftButton, pos=QPoint(40, 10))
    qtbot.mouseRelease(row_widget, Qt.MouseButton.LeftButton, pos=QPoint(40, 10))

    assert captured == [tracks[0].path], (
        f"TC-06-22: real mousePress on row widget must emit row_body_clicked "
        f"with the row's path; got {captured}"
    )


# Spec: TC-06-22 — clicks on the row's play button do NOT emit
# row_body_clicked (the QPushButton absorbs the click before the row's
# mouseReleaseEvent fires).
def test_album_order_play_button_click_does_not_emit_row_body_clicked(
    qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)

    tracks = list(watcher.library().tracks)
    a = store.create(name="Test", target_count=3)
    a.track_paths = [tracks[0].path, tracks[1].path]
    win.top_bar.switcher.set_current(a.id)

    body_clicks: list[Path] = []
    win.album_order_pane.row_body_clicked.connect(body_clicks.append)

    # Click the row's play button — should fire preview_play_requested,
    # NOT row_body_clicked.
    btn = win.album_order_pane.play_button_at(0)
    assert btn is not None
    btn.click()

    assert body_clicks == [], (
        f"TC-06-22: play-button click must not bubble to row_body_clicked; "
        f"got {body_clicks}"
    )


# Spec: TC-06-22 — middle-pane row-body click obeys the same idle/non-idle
# rule. The hit-zone is the title-label area only (not the play button or
# drag handle).
def test_album_order_row_body_click_when_stopped_previews(
    qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)

    tracks = list(watcher.library().tracks)
    a = store.create(name="Test", target_count=3)
    a.track_paths = [tracks[0].path, tracks[1].path]
    win.top_bar.switcher.set_current(a.id)

    assert win._player.state() == PlayerState.STOPPED

    # Drive a row-body click via the album-order pane's signal.
    win.album_order_pane.row_body_clicked.emit(tracks[1].path)

    assert win.now_playing_pane.title_label.text() == tracks[1].title


# ---------- TC-06-23 -----------------------------------------------------

# Spec: TC-06-23 — preview-without-play does not update last_played_track_path.
def test_preview_without_play_does_not_update_last_played(main_window, qtbot) -> None:
    win = main_window
    assert win._state.last_played_track_path is None

    title_col = _col("title")
    proxy = win.library_pane._proxy
    win.library_pane._on_table_clicked(proxy.index(0, title_col))

    assert win._state.last_played_track_path is None, (
        "TC-06-23: row-body click must not set last_played_track_path"
    )


# ---------- TC-06-24 -----------------------------------------------------

# Spec: TC-06-24 — a late state_changed(STOPPED) does not repaint the
# now-playing pane after a preview has populated it.
def test_late_stopped_state_change_does_not_clobber_preview(main_window, qtbot) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)

    # Preview track 1 (player is STOPPED).
    title_col = _col("title")
    proxy = win.library_pane._proxy
    target_row = next(
        i for i in range(proxy.rowCount())
        if win.library_pane._model.track_at(proxy.mapToSource(proxy.index(i, 0)).row()).path
            == tracks[1].path
    )
    win.library_pane._on_table_clicked(proxy.index(target_row, title_col))
    assert win.now_playing_pane.title_label.text() == tracks[1].title

    # Synthetically re-emit state_changed(STOPPED).
    win._player.state_changed.emit(PlayerState.STOPPED)
    qtbot.wait(20)

    assert win.now_playing_pane.title_label.text() == tracks[1].title, (
        "TC-06-24: late state_changed(STOPPED) must not clobber the preview"
    )


# ---------- TC-06-25 -----------------------------------------------------

# Spec: TC-06-25 — keyboard arrow navigation does NOT trigger preview.
def test_keyboard_arrow_navigation_does_not_preview(main_window, qtbot) -> None:
    win = main_window
    initial_title = win.now_playing_pane.title_label.text()
    initial_source = win._player.source()

    # Focus the table; QTableView selection-change via keyboard is the path
    # that would risk hijacking the now-playing pane if we hooked it up.
    table = win.library_pane.table
    table.setFocus()
    # Move focus down a few rows.
    for _ in range(3):
        qtbot.keyClick(table, Qt.Key.Key_Down)
    qtbot.wait(20)

    assert win.now_playing_pane.title_label.text() == initial_title, (
        "TC-06-25: arrow-key row navigation must not change now-playing"
    )
    assert win._player.source() == initial_source


# ---------- TC-06-26 -----------------------------------------------------

# Spec: TC-06-26 — row-body cursor is PointingHandCursor when STOPPED,
# default otherwise.
def test_row_body_cursor_reflects_player_state(main_window, qtbot) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)

    # STOPPED: cursor on the table viewport is PointingHand.
    win._player.state_changed.emit(PlayerState.STOPPED)
    qtbot.wait(10)
    assert win.library_pane.table.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor

    # Force PLAYING via the public play path.
    win._on_preview_play(tracks[0].path)
    qtbot.wait(50)
    win._player._state = PlayerState.PLAYING
    win._player.state_changed.emit(PlayerState.PLAYING)
    qtbot.wait(10)
    assert win.library_pane.table.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor


# Spec: TC-06-21 — row-body click is also a no-op when the player is in ERROR.
def test_row_body_click_when_error_is_noop(main_window, qtbot) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)

    win._on_preview_play(tracks[0].path)
    qtbot.wait(50)
    win._player._state = PlayerState.ERROR
    initial_title = win.now_playing_pane.title_label.text()

    title_col = _col("title")
    proxy = win.library_pane._proxy
    other = next(
        i for i in range(proxy.rowCount())
        if win.library_pane._model.track_at(proxy.mapToSource(proxy.index(i, 0)).row()).path
            == tracks[1].path
    )
    win.library_pane._on_table_clicked(proxy.index(other, title_col))

    assert win.now_playing_pane.title_label.text() == initial_title, (
        "TC-06-21: row-body click while ERROR must not change now-playing"
    )


# Spec: TC-06-26 — cursor flips for PAUSED + ERROR transitions too.
def test_row_body_cursor_arrow_for_paused_and_error(main_window, qtbot) -> None:
    win = main_window

    win._player.state_changed.emit(PlayerState.PAUSED)
    qtbot.wait(10)
    assert win.library_pane.table.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor
    assert win.album_order_pane.list.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor

    win._player.state_changed.emit(PlayerState.ERROR)
    qtbot.wait(10)
    assert win.library_pane.table.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor
    assert win.album_order_pane.list.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor


# Spec: TC-06-25 — Enter/Return on a focused row body does NOT preview
# (the row-body preview path is mouse-click only; the activated signal
# is wired to a separate slot that only handles _play / _toggle).
def test_enter_on_row_body_does_not_preview(main_window, qtbot) -> None:
    win = main_window
    initial_title = win.now_playing_pane.title_label.text()

    title_col = _col("title")
    proxy = win.library_pane._proxy
    # Synthesise activated on a title cell.
    win.library_pane._on_table_activated(proxy.index(0, title_col))
    qtbot.wait(20)

    assert win.now_playing_pane.title_label.text() == initial_title, (
        "TC-06-25: Enter on a row-body cell must not trigger preview"
    )


# Spec: TC-06-26 — the construction-time cursor reflects current player state.
def test_initial_cursor_is_pointing_hand_when_stopped_at_launch(
    qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()  # no last_played → fresh launch
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    # No state_changed has fired yet — only the construction-time push.
    pointing = Qt.CursorShape.PointingHandCursor
    assert win.library_pane.table.viewport().cursor().shape() == pointing
    assert win.album_order_pane.list.viewport().cursor().shape() == pointing


# Spec: TC-06-21 — Spec 04 selection-toggle column click still operates
# independently (the row-body suppression is play-layer only).
def test_toggle_column_click_still_works_when_playing(main_window, qtbot) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)
    a = win._store.create(name="Test", target_count=3)
    win.top_bar.switcher.set_current(a.id)

    # Force PLAYING.
    win._on_preview_play(tracks[0].path)
    qtbot.wait(50)
    win._player._state = PlayerState.PLAYING

    # Click the toggle column on tracks[1] — this should still toggle selection.
    toggle_col = _col("_toggle")
    proxy = win.library_pane._proxy
    other = next(
        i for i in range(proxy.rowCount())
        if win.library_pane._model.track_at(proxy.mapToSource(proxy.index(i, 0)).row()).path
            == tracks[1].path
    )
    win.library_pane._on_table_clicked(proxy.index(other, toggle_col))

    assert tracks[1].path in a.track_paths, (
        "TC-06-21: toggle column click is independent of the row-body rule"
    )
