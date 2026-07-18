"""Spec 18 (Phase E) - player-mode surface: two-bar transport sync, the
NowPlayingCard extraction, the PlayerPane composition, and the MainWindow
fan-out to both now-playing surfaces.

Two-bar sync tests build two `TransportBar(player, controller)` on one real
`Player` + one real `PlaybackController` and assert bar B reflects an action on
bar A (Spec 18 §Test contract). `set_source` / signal emits are synchronous, so
no audio backend / teardown hang is involved.
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import QFrame, QTabWidget

from album_builder.domain.lyrics import LyricLine, Lyrics
from album_builder.domain.play_queue import RepeatMode
from album_builder.domain.track import Track
from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player
from album_builder.ui.main_window import MainWindow
from album_builder.ui.now_playing_card import NowPlayingCard
from album_builder.ui.now_playing_pane import NowPlayingPane
from album_builder.ui.player_pane import PlayerPane
from album_builder.ui.playlists_pane import PlaylistsPane
from album_builder.ui.queue_pane import QueuePane
from album_builder.ui.theme import Glyphs
from album_builder.ui.transport_bar import TransportBar


def _make_track(tmp: Path, **over) -> Track:
    base = dict(
        path=tmp / "song.mpeg",
        title="Walking The Line",
        artist="18 Down",
        album_artist="18 Down",
        album="Memoirs of a Sinner",
        composer="A. Smith",
        comment="rough mix",
        lyrics_text=None,
        cover_data=None,
        cover_mime=None,
        duration_seconds=240.0,
        is_missing=False,
        file_size_bytes=1234,
    )
    base.update(over)
    return Track(**base)


def _two_bars(qtbot):
    p = Player()
    c = PlaybackController(p)
    a = TransportBar(p, c)
    b = TransportBar(p, c)
    qtbot.addWidget(a)
    qtbot.addWidget(b)
    return p, c, a, b


# ---- Two-bar transport sync ----------------------------------------------


# Spec: TC-18-05
def test_volume_change_on_bar_a_moves_bar_b(qtbot) -> None:
    p, _c, a, b = _two_bars(qtbot)
    a.volume_slider.setValue(42)          # user gesture on bar A -> set_volume
    assert p.volume() == 42
    assert a.volume_slider.value() == 42
    assert b.volume_slider.value() == 42  # bar B followed via volume_changed; no loop


# Spec: TC-18-06
def test_mute_on_bar_a_flips_bar_b_glyph(qtbot) -> None:
    p, _c, a, b = _two_bars(qtbot)
    assert b.btn_mute.text() == Glyphs.UNMUTE
    a.btn_mute.click()
    assert p.muted() is True
    assert a.btn_mute.text() == Glyphs.MUTE
    assert b.btn_mute.text() == Glyphs.MUTE
    a.btn_mute.click()
    assert b.btn_mute.text() == Glyphs.UNMUTE


# Spec: TC-18-07
def test_shuffle_on_bar_a_checks_bar_b_without_recursion(qtbot) -> None:
    _p, c, a, b = _two_bars(qtbot)
    seen: list[bool] = []
    c.shuffle_changed.connect(seen.append)
    a.btn_shuffle.click()                 # native toggle -> set_shuffle(True)
    assert c.shuffle_enabled() is True
    assert b.btn_shuffle.isChecked() is True
    assert seen == [True]                 # setChecked echoes `toggled`, not `clicked`


# Spec: TC-18-08
def test_repeat_cycle_on_bar_a_updates_bar_b(qtbot) -> None:
    _p, c, a, b = _two_bars(qtbot)
    a.btn_repeat.click()                  # OFF -> ALL
    assert c.repeat_mode() == RepeatMode.ALL
    assert b.btn_repeat.text() == Glyphs.REPEAT_ALL
    assert b.btn_repeat.isChecked() is True
    assert b.btn_repeat.accessibleName() == "Repeat all"
    a.btn_repeat.click()                  # ALL -> ONE
    assert c.repeat_mode() == RepeatMode.ONE
    assert b.btn_repeat.text() == Glyphs.REPEAT_ONE
    assert b.btn_repeat.isChecked() is True
    assert b.btn_repeat.accessibleName() == "Repeat one"
    a.btn_repeat.click()                  # ONE -> OFF
    assert c.repeat_mode() == RepeatMode.OFF
    assert b.btn_repeat.isChecked() is False
    assert b.btn_repeat.accessibleName() == "Repeat off"


# Spec: TC-18-09
def test_single_bar_visuals_after_own_click(qtbot) -> None:
    p = Player()
    c = PlaybackController(p)
    bar = TransportBar(p, c)
    qtbot.addWidget(bar)
    # Mute + repeat glyphs move via the returning broadcast (imperative _sync
    # calls were removed); shuffle uses the native checkable auto-toggle.
    bar.btn_mute.click()
    assert p.muted() is True
    assert bar.btn_mute.text() == Glyphs.MUTE
    bar.btn_repeat.click()
    assert c.repeat_mode() == RepeatMode.ALL
    assert bar.btn_repeat.text() == Glyphs.REPEAT_ALL
    assert bar.btn_repeat.isChecked() is True
    bar.btn_shuffle.click()
    assert bar.btn_shuffle.isChecked() is True
    assert c.shuffle_enabled() is True


# Spec: TC-18-20
def test_volume_broadcast_skips_bar_mid_drag(qtbot) -> None:
    p, _c, a, b = _two_bars(qtbot)
    a.volume_slider.setValue(30)          # baseline both at 30
    assert b.volume_slider.value() == 30
    a.volume_slider.setSliderDown(True)   # bar A now "mid-drag"
    p.volume_changed.emit(80)
    assert a.volume_slider.value() == 30  # not fought mid-drag
    assert b.volume_slider.value() == 80  # bar B (not dragging) follows


# Spec: TC-18-21
def test_construction_seeds_from_current_state(qtbot) -> None:
    p = Player()
    c = PlaybackController(p)
    p.set_muted(True)
    p.set_volume(35)
    c.set_shuffle(True)
    c.set_repeat(RepeatMode.ALL)
    seen: list = []
    p.volume_changed.connect(lambda v: seen.append(("vol", v)))
    p.muted_changed.connect(lambda m: seen.append(("mute", m)))
    c.shuffle_changed.connect(lambda e: seen.append(("sh", e)))
    c.repeat_changed.connect(lambda m: seen.append(("rep", m)))
    bar = TransportBar(p, c)
    qtbot.addWidget(bar)
    assert bar.btn_shuffle.isChecked() is True
    assert bar.btn_repeat.text() == Glyphs.REPEAT_ALL
    assert bar.btn_repeat.isChecked() is True
    assert bar.btn_mute.text() == Glyphs.MUTE
    assert bar.volume_slider.value() == 35
    assert seen == []                     # construction fired no setter broadcast


# ---- NowPlayingCard ------------------------------------------------------


# Spec: TC-18-10
def test_now_playing_card_render_and_style(qtbot, tmp_path: Path) -> None:
    card = NowPlayingCard()
    qtbot.addWidget(card)
    card.show()
    assert card.objectName() == "NowPlayingCard"
    ss = card.styleSheet()
    assert "QFrame#NowPlayingCard" in ss and "transparent" in ss
    assert card.title_label.objectName() == "NowPlayingTitle"
    assert card.cover_label.objectName() == "NowPlayingCover"
    assert card.placeholder_label.isVisible()           # None at construction
    card.set_track(_make_track(tmp_path, cover_data=None))
    assert not card.placeholder_label.isVisible()
    assert card.title_label.text() == "Walking The Line"
    assert card.album_label.text() == "Memoirs of a Sinner"
    assert card.artist_label.text() == "18 Down"
    assert card.cover_label.text() == "(no cover)"
    card.set_track(_make_track(tmp_path, cover_data=b"\x00\x01nope"))
    assert card.cover_label.text() == "(cover unavailable)"
    card.set_track(None)
    assert card.title_label.text() == ""
    assert card.placeholder_label.isVisible()


# Spec: TC-18-11
def test_now_playing_pane_surface_via_card(qtbot, tmp_path: Path) -> None:
    p = Player()
    pane = NowPlayingPane(p, PlaybackController(p))
    qtbot.addWidget(pane)
    assert hasattr(pane, "lyrics_panel") and hasattr(pane, "transport")
    pane.set_track(_make_track(tmp_path))
    assert pane.card.title_label.text() == "Walking The Line"
    pane.lyrics_panel.set_lyrics(Lyrics(lines=(LyricLine(time_seconds=0.0, text="x"),)))
    assert pane.lyrics_panel.list.count() == 1
    pane.set_track(None)                  # L7-M5: clears card AND this pane's lyrics
    assert pane.card.title_label.text() == ""
    assert pane.lyrics_panel.list.count() == 0


# ---- PlayerPane ----------------------------------------------------------


# Spec: TC-18-12
def test_player_pane_construction_and_layout(qtbot) -> None:
    p = Player()
    c = PlaybackController(p)
    qp = QueuePane()
    pp = PlaylistsPane()
    pane = PlayerPane(p, c, qp, pp)
    qtbot.addWidget(pane)
    assert pane.card is not None
    assert pane.transport is not None
    assert pane.lyrics_panel is not None
    tabw = pane.findChild(QTabWidget)
    assert tabw is not None
    assert tabw.count() == 2
    assert tabw.tabText(0) == "Up Next"
    assert tabw.tabText(1) == "Playlists"
    assert pane.isAncestorOf(qp)
    assert pane.isAncestorOf(pp)
    left_panes = [w for w in pane.findChildren(QFrame) if w.objectName() == "Pane"]
    assert left_panes, "left column is a QFrame#Pane (guards bg_base regression)"


# Spec: TC-18-13
def test_player_pane_set_track(qtbot, tmp_path: Path) -> None:
    p = Player()
    pane = PlayerPane(p, PlaybackController(p), QueuePane(), PlaylistsPane())
    qtbot.addWidget(pane)
    pane.set_track(_make_track(tmp_path))
    assert pane.card.title_label.text() == "Walking The Line"
    pane.lyrics_panel.set_lyrics(Lyrics(lines=(LyricLine(time_seconds=0.0, text="x"),)))
    pane.set_track(None)                  # symmetric: blanks card AND own lyrics
    assert pane.card.title_label.text() == ""
    assert pane.lyrics_panel.list.count() == 0


# Spec: TC-18-14
def test_player_pane_transport_drives_shared_controller(qtbot, monkeypatch) -> None:
    p = Player()
    c = PlaybackController(p)
    pane = PlayerPane(p, c, QueuePane(), PlaylistsPane())
    qtbot.addWidget(pane)
    assert pane.transport._controller is c
    calls: list = []
    monkeypatch.setattr(c, "next", lambda: calls.append(True))
    pane.transport.btn_next.click()
    assert calls == [True]


# ---- MainWindow fan-out --------------------------------------------------


# Spec: TC-18-15
def test_current_changed_fans_to_both_surfaces(main_window) -> None:
    main = main_window
    tracks = main.library_pane.view_order_tracks()
    main.library_pane.play_tracks_requested.emit(tracks, 0)
    first = tracks[0]
    assert main.now_playing_pane.card.title_label.text() == first.title
    assert main._player_pane.card.title_label.text() == first.title
    # Seed lyrics on both panels, then clear the queue -> current_changed(None).
    ly = Lyrics(lines=(LyricLine(time_seconds=0.0, text="hi"),))
    for panel in main._lyrics_panels:
        panel.set_lyrics(ly)
    main._controller.play_tracks([])
    assert main.now_playing_pane.card.title_label.text() == ""
    assert main._player_pane.card.title_label.text() == ""
    for panel in main._lyrics_panels:
        assert panel.list.count() == 0   # both cleared (None self-clears each panel)


# Spec: TC-18-16
def test_lyrics_fan_out_to_both_panels(
    qtbot, tmp_path: Path, tracks_dir: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    track = next(iter(watcher.library().tracks))
    lrc = track.path.with_suffix(".lrc")
    lrc.write_text("[00:00.00]hi\n[00:01.50]there\n", encoding="utf-8")
    os.utime(track.path, (track.path.stat().st_atime, lrc.stat().st_mtime - 10))
    win = MainWindow(store, watcher, AppState(), tmp_path)
    qtbot.addWidget(win)
    win._sync_lyrics_for_track(track)
    for panel in win._lyrics_panels:
        assert panel.list.count() == 2
    win._tracker.current_line_changed.emit(1)
    for panel in win._lyrics_panels:
        assert panel.current_line() == 1


# Spec: TC-18-17
def test_align_now_from_either_panel_starts_a_job(main_window, monkeypatch) -> None:
    import album_builder.ui.main_window as mw
    main = main_window
    monkeypatch.setattr(mw, "whisperx_models_cached", lambda *_: True)
    track = next(iter(main._library_watcher.library().tracks))
    main._state.last_played_track_path = track.path
    calls: list = []
    monkeypatch.setattr(main._alignment, "start_alignment", lambda t: calls.append(t))
    for panel in main._lyrics_panels:
        panel.align_now_requested.emit()
    # Either panel's button starts a job on the loaded track (not the sender).
    assert calls == [track, track]


# Spec: TC-18-18
def test_alignment_updates_fan_to_both_panels(main_window) -> None:
    main = main_window
    track = next(iter(main._library_watcher.library().tracks))
    main._state.last_played_track_path = track.path
    main._alignment.progress.emit(track.path, 33)
    for panel in main._lyrics_panels:
        assert "33%" in panel.status_label.text()
    main._alignment.lyrics_ready.emit(track.path, Lyrics(
        lines=(LyricLine(time_seconds=0.0, text="hi"),)))
    for panel in main._lyrics_panels:
        assert panel.list.count() == 1
    # Stale-track emit updates neither panel (active-track guard unchanged).
    main._alignment.progress.emit(Path("/nope/other.mp3"), 99)
    for panel in main._lyrics_panels:
        assert "99%" not in panel.status_label.text()


# Spec: TC-18-19
def test_main_window_tabs_and_player_pane(main_window) -> None:
    main = main_window
    assert main.tabs.count() == 2
    assert main.tabs.tabText(0) == "Album Builder"
    assert main.tabs.tabText(1) == "Player"
    assert main.tabs.widget(1) is main._player_pane
    assert main.splitter.isAncestorOf(main.now_playing_pane)


# Spec: TC-18-22
def test_row_body_preview_fans_to_both(main_window) -> None:
    main = main_window
    track = main.library_pane.view_order_tracks()[0]
    main._on_row_body_clicked(track.path)  # player STOPPED at construction
    assert main.now_playing_pane.card.title_label.text() == track.title
    assert main._player_pane.card.title_label.text() == track.title


# Spec: TC-18-23
def test_current_changed_preserves_non_surface_side_effects(main_window) -> None:
    main = main_window
    tracks = main.library_pane.view_order_tracks()
    main.library_pane.play_tracks_requested.emit(tracks, 0)
    first = tracks[0]
    assert main._state.last_played_track_path == first.path
    assert main.queue_pane.list.currentRow() == main._controller.current_position()
    assert main.queue_pane.list.currentRow() == 0


# Spec: TC-18-24
def test_startup_restore_fans_to_both(
    qtbot, tmp_path: Path, tracks_dir: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    track = next(iter(watcher.library().tracks))
    state = AppState()
    state.last_played_track_path = track.path
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    assert win.now_playing_pane.card.title_label.text() == track.title
    assert win._player_pane.card.title_label.text() == track.title
