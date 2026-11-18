"""Built-in lists in the Playlists tab - Spec 29 §4.5 (TC-29-12, TC-29-13)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.library import Library
from album_builder.domain.play_history import SongStats
from album_builder.domain.playlist import Playlist
from album_builder.domain.track import Track
from album_builder.persistence.play_history_io import save_history
from album_builder.services.play_history import PlayHistory
from album_builder.services.player import Player, PlayerState
from album_builder.ui.playlists_pane import PlaylistsPane
from album_builder.ui.theme import Glyphs
from tests.conftest import SILENT_MP3

T0 = datetime(2026, 11, 18, tzinfo=UTC)
ID_SIGNALS = (
    "play_requested",
    "rename_committed",
    "delete_requested",
    "move_track_requested",
    "remove_track_requested",
)


def _track(path: Path) -> Track:
    return Track(
        path=path, title=path.stem, artist="A", album_artist="A", composer="",
        album="", comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=100.0, file_size_bytes=1, is_missing=False,
    )


@pytest.fixture
def setup(qtbot, tmp_path: Path):
    music = tmp_path / "music"
    tracks = [_track(music / f"{n}.mp3") for n in ("alpha", "beta", "gamma")]
    lib = Library(folder=music, tracks=tracks)
    root = tmp_path / "root"
    save_history(root, {
        "alpha.mp3": SongStats(plays=1, last_played=T0),
        "beta.mp3": SongStats(plays=3, last_played=T0 + timedelta(minutes=1)),
        "gamma.mp3": SongStats(favourited=T0),
    })
    player = Player()
    history = PlayHistory(root, player, SimpleNamespace(library=lambda: lib))
    pane = PlaylistsPane()
    qtbot.addWidget(pane)
    pane.set_library(lib)
    pane.set_playlists([Playlist(id="p1", name="Mine", track_paths=[tracks[0].path])])
    pane.set_play_history(history)
    fired: list[str] = []
    for name in ID_SIGNALS:
        getattr(pane, name).connect(lambda *a, n=name: fired.append(n))
    return SimpleNamespace(pane=pane, history=history, tracks=tracks, fired=fired, player=player)


def _names(pane: PlaylistsPane) -> list[str]:
    return [pane.playlists_list.item(i).text() for i in range(pane.playlists_list.count())]


def _shown(pane: PlaylistsPane) -> list[str]:
    return [pane.tracks_list.item(i).text() for i in range(pane.tracks_list.count())]


# Spec: TC-29-12
def test_built_in_rows_first_and_locked(setup, qtbot) -> None:
    pane, fired = setup.pane, setup.fired
    icon = Glyphs.AUTO_LIST
    assert _names(pane) == [
        f"{icon} Favourites", f"{icon} Recently played", f"{icon} Most played", "Mine",
    ]
    for row, expected in ((0, ["gamma"]), (1, ["beta", "alpha"]), (2, ["beta", "alpha"])):
        pane.playlists_list.setCurrentRow(row)
        assert pane.current_playlist_id() is None
        item = pane.playlists_list.item(row)
        assert not item.flags() & Qt.ItemFlag.ItemIsEditable
        assert _shown(pane) == expected
        pane.tracks_list.setCurrentRow(len(expected) - 1)
        assert not pane.btn_delete.isEnabled()
        assert not pane.btn_track_up.isEnabled()
        assert not pane.btn_track_down.isEnabled()
        assert not pane.btn_track_remove.isEnabled()
        assert pane.btn_play.isEnabled()

        # Disabled actions do nothing, even when driven directly.
        pane._on_delete_clicked()
        pane._on_move_track(-1)
        pane._on_remove_track()
        item.setText("renamed")  # an inline edit, were one possible
        with qtbot.waitSignal(pane.smart_play_requested, timeout=500) as blocker:
            pane.btn_play.click()
        assert [t.title for t in blocker.args[0]] == expected
    assert fired == []

    # The user's playlist still works as before.
    pane.playlists_list.setCurrentRow(3)
    assert pane.current_playlist_id() == "p1"
    pane.btn_play.click()
    assert fired == ["play_requested"]


# Spec: TC-29-13
def test_live_refresh(setup) -> None:
    pane, history, tracks, player = setup.pane, setup.history, setup.tracks, setup.player
    pane.playlists_list.setCurrentRow(0)
    assert _shown(pane) == ["gamma"]
    history.set_favourite(tracks[0], True)
    assert _shown(pane) == ["alpha", "gamma"]

    # A counted play refreshes Recently played.
    pane.playlists_list.setCurrentRow(1)
    gamma = tracks[2].path
    gamma.parent.mkdir(parents=True)
    shutil.copy(SILENT_MP3, gamma)
    player._set_duration_for_test(100)
    player.set_source(gamma)
    player._set_state_for_test(PlayerState.PLAYING)
    for i in range(501):
        player.position_changed.emit(i / 10)
    assert _shown(pane) == ["gamma", "beta", "alpha"]
