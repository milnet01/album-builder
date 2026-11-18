"""The Player tab's now-playing card heart - Spec 29 §4.5 (TC-29-15)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from album_builder.domain.library import Library
from album_builder.domain.track import Track
from album_builder.services.play_history import PlayHistory
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player
from album_builder.ui.library_pane import LibraryPane
from album_builder.ui.now_playing_pane import NowPlayingPane
from album_builder.ui.player_pane import PlayerPane
from album_builder.ui.playlists_pane import PlaylistsPane
from album_builder.ui.queue_pane import QueuePane
from album_builder.ui.theme import Glyphs


def _track(path: Path) -> Track:
    return Track(
        path=path, title=path.stem, artist="A", album_artist="A", composer="",
        album="", comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=100.0, file_size_bytes=1, is_missing=False,
    )


# Spec: TC-29-15
def test_card_heart_follows_and_toggles(qtbot, tmp_path: Path) -> None:
    music = tmp_path / "music"
    one, two = _track(music / "one.mp3"), _track(music / "two.mp3")
    lib = Library(folder=music, tracks=[one, two])
    player = Player()
    controller = PlaybackController(player)
    history = PlayHistory(tmp_path / "root", player, SimpleNamespace(library=lambda: lib))
    pane = PlayerPane(
        player, controller, QueuePane(), PlaylistsPane(), LibraryPane(player_mode=True),
    )
    qtbot.addWidget(pane)
    pane.set_play_history(history)
    pane.favourite_toggled.connect(history.set_favourite)
    heart = pane.card.heart_button
    assert heart is not None
    assert heart.accessibleName() == "Favourite"

    # No track: disabled.
    assert not heart.isEnabled()

    pane.set_track(one)
    assert heart.isEnabled() and not heart.isChecked()
    assert heart.text() == Glyphs.HEART_OUTLINE
    assert heart.toolTip() == "Add to favourites"

    heart.click()
    assert history.stats_for(one).favourited is not None
    assert heart.isChecked() and heart.text() == Glyphs.HEART
    assert heart.toolTip() == "Remove from favourites"

    # A track change shows the new track's state, not the previous one's.
    pane.set_track(two)
    assert not heart.isChecked()

    # A change made elsewhere (the song list) shows here too.
    history.set_favourite(two, True)
    assert heart.isChecked()

    heart.click()
    assert history.stats_for(two).favourited is None
    assert history.stats_for(one).favourited is not None

    # A song outside the music folder has no key: disabled.
    pane.set_track(_track(tmp_path / "elsewhere" / "x.mp3"))
    assert not heart.isEnabled()
    pane.set_track(None)
    assert not heart.isEnabled()


# Spec: TC-29-15
def test_album_builder_card_has_no_heart(qtbot) -> None:
    player = Player()
    pane = NowPlayingPane(player, PlaybackController(player))
    qtbot.addWidget(pane)
    assert pane.card.heart_button is None
