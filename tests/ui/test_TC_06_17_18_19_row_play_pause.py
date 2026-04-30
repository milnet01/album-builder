"""Spec 06 TC-06-17/18/19 - per-row preview-play button is a load-or-toggle.

The v0.4.0 implementation always reloaded the source on row-button click
- including when the row's track was already the active source - which
ignored the user's expectation that a click on the playing row should
pause it (the same way the transport bar's main play/pause button does).
v0.5.2 turns the row button into a load-or-toggle control with a
state-mirrored glyph.

Tests live in one file because the contract (TC-06-17/18/19) crosses
three units: MainWindow's _on_preview_play dispatch, LibraryPane's
DisplayRole + AccessibleTextRole on the play column, and AlbumOrderPane's
QPushButton text + accessibleName.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.album import Album
from album_builder.domain.track import Track
from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.player import PlayerState
from album_builder.ui.album_order_pane import AlbumOrderPane
from album_builder.ui.library_pane import COLUMNS, LibraryPane
from album_builder.ui.main_window import MainWindow
from album_builder.ui.theme import Glyphs


def _play_col() -> int:
    for i, (_, attr) in enumerate(COLUMNS):
        if attr == "_play":
            return i
    raise AssertionError("library_pane.COLUMNS has no _play column")


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
    return win


# ---------- TC-06-17 -----------------------------------------------------

# Spec: TC-06-17 — same-row click on the active+playing source pauses without
# reloading. set_source is called once (the initial load); a second click does
# not call set_source again, and the player state transitions PLAYING -> PAUSED.
def test_active_playing_row_click_pauses_without_reload(main_window, qtbot, monkeypatch) -> None:
    track_paths = [t.path for t in main_window._library_watcher.library().tracks]
    assert track_paths

    set_source_calls: list[Path | None] = []
    real_set_source = main_window._player.set_source

    def spy(path):
        set_source_calls.append(path)
        real_set_source(path)
    monkeypatch.setattr(main_window._player, "set_source", spy)

    # First click loads + plays.
    main_window._on_preview_play(track_paths[0])
    qtbot.wait(50)
    assert set_source_calls == [track_paths[0]], "first click loads the track"

    # Force the state to PLAYING for the test (real QMediaPlayer may take
    # longer than the test window to actually start; the dispatch logic
    # only cares about the reported state).
    main_window._player._state = PlayerState.PLAYING

    # Second click on the same row — must NOT call set_source again.
    main_window._on_preview_play(track_paths[0])
    qtbot.wait(50)
    assert set_source_calls == [track_paths[0]], (
        "TC-06-17: same-row click on active+playing source must not reload "
        f"(set_source called {len(set_source_calls)} times: {set_source_calls})"
    )
    # State must have transitioned to PAUSED via the toggle path.
    assert main_window._player.state() == PlayerState.PAUSED, (
        "TC-06-17: same-row click on active+playing source pauses; "
        f"state is {main_window._player.state()}"
    )
    # Source unchanged.
    assert main_window._player.source() == track_paths[0]


# ---------- TC-06-18 -----------------------------------------------------

# Spec: TC-06-18 — same-row click on the active+paused source resumes.
def test_active_paused_row_click_resumes_without_reload(main_window, qtbot, monkeypatch) -> None:
    track_paths = [t.path for t in main_window._library_watcher.library().tracks]

    set_source_calls: list[Path | None] = []
    real_set_source = main_window._player.set_source

    def spy(path):
        set_source_calls.append(path)
        real_set_source(path)
    monkeypatch.setattr(main_window._player, "set_source", spy)

    # Load + play, then pause via the real Player.pause() path so Qt's
    # underlying QMediaPlayer state matches the python-side state. (Hand-
    # setting _state = PAUSED while QMediaPlayer is still PlayingState
    # would make the next play() a Qt-level no-op, blocking the resume.)
    main_window._on_preview_play(track_paths[0])
    qtbot.wait(50)
    assert set_source_calls == [track_paths[0]]
    main_window._player.pause()
    qtbot.wait(50)
    assert main_window._player.state() == PlayerState.PAUSED, (
        f"setup: expected PAUSED after pause(); got {main_window._player.state()}"
    )

    # Click same row again: resume without reload.
    main_window._on_preview_play(track_paths[0])
    qtbot.wait(50)
    assert set_source_calls == [track_paths[0]], (
        "TC-06-18: same-row click on active+paused source must not reload"
    )
    assert main_window._player.state() == PlayerState.PLAYING, (
        f"TC-06-18: same-row click on active+paused source resumes; "
        f"state is {main_window._player.state()}"
    )


# ---------- TC-06-15 (amended) -------------------------------------------

# Spec: TC-06-15 (amended) — cross-row click loads + plays the new track and
# stops the prior one (player observably does the swap, not just emits the
# preview signal).
def test_cross_row_click_swaps_source(main_window, qtbot) -> None:
    track_paths = [t.path for t in main_window._library_watcher.library().tracks]
    assert len(track_paths) >= 2

    main_window._on_preview_play(track_paths[0])
    qtbot.wait(50)
    main_window._player._state = PlayerState.PLAYING
    assert main_window._player.source() == track_paths[0]

    # Cross-row click: different path than the active source.
    main_window._on_preview_play(track_paths[1])
    qtbot.wait(50)
    assert main_window._player.source() == track_paths[1], (
        "TC-06-15: cross-row click must swap the source"
    )


# ---------- TC-06-19 (library pane) --------------------------------------

# Spec: TC-06-19 — library-pane play column DisplayRole returns Glyphs.PAUSE
# for the row whose track is the active source AND state is PLAYING; PLAY
# otherwise. AccessibleTextRole mirrors the action.
def test_library_pane_active_playing_row_shows_pause_glyph(qtbot, tracks_dir: Path) -> None:
    from album_builder.domain.library import Library
    lib = Library.scan(tracks_dir)
    pane = LibraryPane()
    pane.set_library(lib)
    qtbot.addWidget(pane)

    play_col = _play_col()
    target = lib.tracks[0]

    # Drive the pane via its public API, not via the model directly.
    pane.set_active_play_state(target.path, playing=True)

    model = pane._model
    src = model.index(0, play_col)
    assert model.data(src, Qt.ItemDataRole.DisplayRole) == Glyphs.PAUSE
    accessible = model.data(src, Qt.ItemDataRole.AccessibleTextRole)
    assert accessible == f"Pause {target.title}", (
        f"TC-06-19: library-pane row 0 accessible text is {accessible!r}"
    )

    # Other rows still show PLAY.
    other = model.index(1, play_col)
    assert model.data(other, Qt.ItemDataRole.DisplayRole) == Glyphs.PLAY
    other_accessible = model.data(other, Qt.ItemDataRole.AccessibleTextRole)
    assert other_accessible.startswith("Preview-play")


# Spec: TC-06-19 — when the player is not PLAYING (PAUSED / STOPPED / ERROR),
# every row shows PLAY, even the active-source row.
def test_library_pane_active_paused_row_shows_play_glyph(qtbot, tracks_dir: Path) -> None:
    from album_builder.domain.library import Library
    lib = Library.scan(tracks_dir)
    pane = LibraryPane()
    pane.set_library(lib)
    qtbot.addWidget(pane)

    play_col = _play_col()
    target = lib.tracks[0]
    pane.set_active_play_state(target.path, playing=False)

    src = pane._model.index(0, play_col)
    assert pane._model.data(src, Qt.ItemDataRole.DisplayRole) == Glyphs.PLAY


# ---------- TC-06-19 (album-order pane) ----------------------------------

# Spec: TC-06-19 — album-order pane row's QPushButton.text() and
# accessibleName() flip on set_active_play_state(path, playing=True).
def test_album_order_pane_active_playing_row_shows_pause_glyph(qtbot) -> None:
    pane = AlbumOrderPane()
    qtbot.addWidget(pane)
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3"), Path("/abs/b.mp3")]
    pane.set_album(a, [_ord_track("a"), _ord_track("b")])

    pane.set_active_play_state(Path("/abs/a.mp3"), playing=True)
    btn = pane.play_button_at(0)
    assert btn is not None
    assert btn.text() == Glyphs.PAUSE, (
        f"TC-06-19: album-order row 0 button glyph is {btn.text()!r}"
    )
    assert btn.accessibleName() == "Pause a"

    other = pane.play_button_at(1)
    assert other is not None
    assert other.text() == Glyphs.PLAY


# Spec: TC-06-19 — set_album re-render preserves the PAUSE glyph if the
# active source is in the new track list (the album_order_pane re-apply
# branch). Without this, every album-switch would briefly show PLAY for
# the active track until the next state_changed tick.
def test_album_order_pane_set_album_preserves_active_glyph(qtbot) -> None:
    pane = AlbumOrderPane()
    qtbot.addWidget(pane)
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3"), Path("/abs/b.mp3")]
    pane.set_album(a, [_ord_track("a"), _ord_track("b")])
    pane.set_active_play_state(Path("/abs/a.mp3"), playing=True)

    # Re-render with the same album/tracks — the active row's glyph
    # must survive (set_album reads _active_path/_active_playing on
    # row construction).
    pane.set_album(a, [_ord_track("a"), _ord_track("b")])
    btn0 = pane.play_button_at(0)
    assert btn0 is not None
    assert btn0.text() == Glyphs.PAUSE, (
        "TC-06-19: set_album re-render must preserve the active row's PAUSE glyph"
    )


# Spec: TC-06-19 — on a swap, only the previously-active and newly-active
# rows have set_active called; the other rows are untouched.
def test_album_order_pane_swap_calls_set_active_only_on_affected_rows(
    qtbot, monkeypatch,
) -> None:
    pane = AlbumOrderPane()
    qtbot.addWidget(pane)
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3"), Path("/abs/b.mp3"), Path("/abs/c.mp3")]
    pane.set_album(a, [_ord_track("a"), _ord_track("b"), _ord_track("c")])

    from album_builder.ui import album_order_pane as aop
    calls: list[tuple[int, bool]] = []
    real = aop._OrderRowWidget.set_active

    def spy(self_widget, *, playing):
        # Identify the row by matching against the path stash.
        for i in range(pane.list.count()):
            if pane.list.itemWidget(pane.list.item(i)) is self_widget:
                calls.append((i, playing))
                break
        real(self_widget, playing=playing)
    monkeypatch.setattr(aop._OrderRowWidget, "set_active", spy)

    # Initial set: one row affected.
    pane.set_active_play_state(Path("/abs/a.mp3"), playing=True)
    assert calls == [(0, True)], (
        f"TC-06-19: initial active set calls set_active for row 0 only; got {calls}"
    )
    calls.clear()

    # Swap: previously-active (row 0) reverts + newly-active (row 1) flips.
    pane.set_active_play_state(Path("/abs/b.mp3"), playing=True)
    affected_rows = sorted({i for i, _ in calls})
    assert affected_rows == [0, 1], (
        f"TC-06-19: swap calls set_active for rows 0+1 only; got {affected_rows}"
    )
    # Row 0 reverts to playing=False; row 1 goes to playing=True.
    assert (0, False) in calls
    assert (1, True) in calls


# Spec: TC-06-19 — clearing the active track flips both rows' glyphs back.
def test_album_order_pane_clear_active_resets_all_rows_to_play(qtbot) -> None:
    pane = AlbumOrderPane()
    qtbot.addWidget(pane)
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3"), Path("/abs/b.mp3")]
    pane.set_album(a, [_ord_track("a"), _ord_track("b")])

    pane.set_active_play_state(Path("/abs/a.mp3"), playing=True)
    pane.set_active_play_state(None, playing=False)
    btn0 = pane.play_button_at(0)
    btn1 = pane.play_button_at(1)
    assert btn0 is not None and btn1 is not None
    assert btn0.text() == Glyphs.PLAY
    assert btn1.text() == Glyphs.PLAY


# ---------- TC-06-19 (perf observable) -----------------------------------

# Spec: TC-06-19 — on a source-swap, only the previously-active and newly-
# active rows emit dataChanged for the play column. Verified by collecting
# dataChanged hits and asserting the row range covers exactly those two
# (or one, if no row was previously active).
def test_library_pane_swap_emits_data_changed_only_for_affected_rows(
    qtbot, tracks_dir: Path,
) -> None:
    from album_builder.domain.library import Library
    lib = Library.scan(tracks_dir)
    pane = LibraryPane()
    pane.set_library(lib)
    qtbot.addWidget(pane)

    play_col = _play_col()
    hits: list[tuple[int, int, int]] = []

    def on_data_changed(top_left, bottom_right, _roles):
        if top_left.column() <= play_col <= bottom_right.column():
            for r in range(top_left.row(), bottom_right.row() + 1):
                hits.append((r, top_left.column(), bottom_right.column()))
    pane._model.dataChanged.connect(on_data_changed)

    # Initial set: one row affected (no prior active).
    pane.set_active_play_state(lib.tracks[0].path, playing=True)
    affected_rows = sorted({r for r, _, _ in hits})
    assert affected_rows == [0], (
        f"TC-06-19: initial active set emits dataChanged for row 0 only; "
        f"got rows {affected_rows}"
    )
    hits.clear()

    # Swap: previously active (row 0) + newly active (row 1) — exactly two rows.
    pane.set_active_play_state(lib.tracks[1].path, playing=True)
    affected_rows = sorted({r for r, _, _ in hits})
    assert affected_rows == [0, 1], (
        f"TC-06-19: swap emits dataChanged for rows 0+1 only; got {affected_rows}"
    )
