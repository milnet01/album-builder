"""PlaylistsPane - saved-playlists surface (Spec 17, Phase D).
Test contracts TC-17-17, 18, 27, 28, 30."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.library import Library
from album_builder.domain.playlist import Playlist
from album_builder.domain.track import Track
from album_builder.ui.playlists_pane import PlaylistsPane


def _track(path: str, *, title: str) -> Track:
    return Track(
        path=Path(path),
        title=title,
        artist="A",
        album_artist="A",
        composer="",
        album="",
        comment="",
        lyrics_text=None,
        cover_data=None,
        cover_mime=None,
        duration_seconds=1.0,
        file_size_bytes=1,
        is_missing=False,
    )


def _lib(*tracks: Track) -> Library:
    return Library(folder=Path("/tracks"), tracks=tracks)


def _pl(name: str, *paths: str, pl_id: str | None = None) -> Playlist:
    p = Playlist(id=pl_id or name, name=name, track_paths=[Path(x) for x in paths])
    return p


@pytest.fixture
def pane(qtbot):
    p = PlaylistsPane()
    qtbot.addWidget(p)
    return p


# Spec: TC-17-17
def test_renders_playlists_and_resolves_tracks(pane) -> None:
    pane.set_playlists([_pl("Happy", "/tracks/a.mp3", "/tracks/c.mp3")])
    # A set_playlists before any set_library: every track renders "(missing)".
    assert pane.tracks_list.item(0).text() == "a.mp3 (missing)"
    assert pane.tracks_list.item(1).text() == "c.mp3 (missing)"

    # set_library resolves present tracks by title; absent stays "(missing)".
    pane.set_library(_lib(_track("/tracks/a.mp3", title="Song A")))
    assert pane.playlists_list.count() == 1
    assert pane.playlists_list.item(0).text() == "Happy"
    assert pane.tracks_list.item(0).text() == "Song A"
    assert pane.tracks_list.item(1).text() == "c.mp3 (missing)"

    # A later library that now contains c flips it back from "(missing)".
    pane.set_library(_lib(
        _track("/tracks/a.mp3", title="Song A"),
        _track("/tracks/c.mp3", title="Song C"),
    ))
    assert pane.tracks_list.item(1).text() == "Song C"


# Spec: TC-17-18
def test_action_buttons_emit_and_have_accessible_names(pane, qtbot) -> None:
    pane.set_playlists([_pl("Happy", "/tracks/a.mp3", "/tracks/b.mp3", "/tracks/c.mp3")])
    pane.set_library(_lib())  # tracks all "(missing)" but present as rows

    with qtbot.waitSignal(pane.create_requested, timeout=500):
        pane.btn_new.click()

    with qtbot.waitSignal(pane.play_requested, timeout=500) as sig:
        pane.btn_play.click()
    assert sig.args[0] == "Happy"

    with qtbot.waitSignal(pane.delete_requested, timeout=500) as sig:
        pane.btn_delete.click()
    assert sig.args[0] == "Happy"

    # Select the middle track: Up and Down both enabled.
    pane.tracks_list.setCurrentRow(1)
    assert pane.btn_track_up.isEnabled()
    assert pane.btn_track_down.isEnabled()
    with qtbot.waitSignal(pane.move_track_requested, timeout=500) as sig:
        pane.btn_track_up.click()
    assert sig.args == ["Happy", 1, 0]

    pane.tracks_list.setCurrentRow(1)
    with qtbot.waitSignal(pane.remove_track_requested, timeout=500) as sig:
        pane.btn_track_remove.click()
    assert sig.args == ["Happy", 1]

    # Disabled at the ends.
    pane.tracks_list.setCurrentRow(0)
    assert not pane.btn_track_up.isEnabled()
    pane.tracks_list.setCurrentRow(2)
    assert not pane.btn_track_down.isEnabled()

    # Inline rename commit emits (id, new name).
    with qtbot.waitSignal(pane.rename_committed, timeout=500) as sig:
        pane.playlists_list.item(0).setText("Renamed")
    assert sig.args == ["Happy", "Renamed"]

    for b in (pane.btn_new, pane.btn_delete, pane.btn_play,
              pane.btn_track_up, pane.btn_track_down, pane.btn_track_remove):
        assert b.accessibleName()


# Spec: TC-17-27
def test_selection_survives_re_render(pane) -> None:
    a, b, c = _pl("A", pl_id="A"), _pl("B", pl_id="B"), _pl("C", pl_id="C")
    pane.set_playlists([a, b, c])
    pane.playlists_list.setCurrentRow(1)  # select B
    assert pane.current_playlist_id() == "B"

    # Reordered list still containing B: selection stays on B.
    pane.set_playlists([c, b, a])
    assert pane.current_playlist_id() == "B"

    # B deleted: falls to the first remaining row.
    pane.set_playlists([c, a])
    assert pane.current_playlist_id() == "C"

    # Empty catalogue: selection clears to None.
    pane.set_playlists([])
    assert pane.current_playlist_id() is None


# Spec: TC-17-28
def test_button_disable_gating(pane) -> None:
    # No playlist selected (empty catalogue).
    pane.set_playlists([])
    assert not pane.btn_delete.isEnabled()
    assert not pane.btn_play.isEnabled()
    assert not pane.btn_track_up.isEnabled()
    assert not pane.btn_track_down.isEnabled()
    assert not pane.btn_track_remove.isEnabled()
    assert pane.btn_new.isEnabled()  # New always enabled

    # A selected-but-empty playlist keeps the three track buttons disabled.
    pane.set_playlists([_pl("Empty")])
    assert pane.btn_delete.isEnabled()
    assert pane.btn_play.isEnabled()
    assert not pane.btn_track_up.isEnabled()
    assert not pane.btn_track_down.isEnabled()
    assert not pane.btn_track_remove.isEnabled()

    # Playlist with tracks but no track row highlighted: still disabled.
    pane.set_playlists([_pl("Full", "/x/a.mp3")])
    pane.tracks_list.setCurrentRow(-1)
    assert not pane.btn_track_remove.isEnabled()


# Spec: TC-17-30
def test_keyboard_reorder_follows_track(pane, qtbot) -> None:
    # Simulate the store: apply each requested move/remove to a live playlist
    # and re-render, exactly as MainWindow -> store.changed -> set_playlists does.
    pl = _pl("P", "/x/a.mp3", "/x/b.mp3", "/x/c.mp3", pl_id="P")
    pane.set_library(_lib(
        _track("/x/a.mp3", title="A"),
        _track("/x/b.mp3", title="B"),
        _track("/x/c.mp3", title="C"),
    ))
    pane.set_playlists([pl])

    pane.move_track_requested.connect(
        lambda _id, f, t: (pl.move(f, t), pane.set_playlists([pl]))
    )
    pane.remove_track_requested.connect(
        lambda _id, i: (pl.remove(i), pane.set_playlists([pl]))
    )

    pane.tracks_list.setCurrentRow(0)  # select track A
    pane.btn_track_down.click()        # A -> slot 1, selection follows
    assert pane.tracks_list.currentRow() == 1
    pane.btn_track_down.click()        # A -> slot 2
    assert pane.tracks_list.currentRow() == 2
    assert [p.name for p in pl.track_paths] == ["b.mp3", "c.mp3", "a.mp3"]
    assert pane.tracks_list.item(2).text() == "A"  # selection is on A

    # Remove: selection lands on the entry now at the removed index.
    pane.tracks_list.setCurrentRow(0)  # b
    pane.btn_track_remove.click()
    assert [p.name for p in pl.track_paths] == ["c.mp3", "a.mp3"]
    assert pane.tracks_list.currentRow() == 0  # entry now at removed index (c)

    # Removing the last row lands selection on the new last row.
    pane.tracks_list.setCurrentRow(1)  # a (last)
    pane.btn_track_remove.click()
    assert [p.name for p in pl.track_paths] == ["c.mp3"]
    assert pane.tracks_list.currentRow() == 0
