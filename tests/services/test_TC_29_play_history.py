"""PlayHistory service - Spec 29 (TC-29-03, 07, 08, 09, 10, 11).

The service tests emit `Player` signals directly, so none needs real audio
to play; `set_source` loads a real silent file so the backend stays quiet.
The library is a stub watcher: PlayHistory only calls `library()`.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from album_builder.domain.library import Library
from album_builder.domain.play_history import SongStats
from album_builder.domain.track import Track
from album_builder.persistence.play_history_io import (
    history_path,
    load_history,
    save_history,
)
from album_builder.services.play_history import PlayHistory, SmartList
from album_builder.services.player import Player, PlayerState
from tests.conftest import SILENT_MP3


def _track(path: Path) -> Track:
    return Track(
        path=path, title=path.stem, artist="A", album_artist="A", composer="",
        album="", comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=100.0, file_size_bytes=1, is_missing=False,
    )


def _watcher(folder: Path, *names: str) -> SimpleNamespace:
    lib = Library(folder=folder, tracks=[_track(folder / n) for n in names])
    return SimpleNamespace(library=lambda: lib)


def _song(folder: Path, name: str = "song.mp3") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy(SILENT_MP3, folder / name))


@pytest.fixture
def player(qapp):
    p = Player()
    yield p
    p.stop()


def _listen(player: Player, seconds: float, *, start: float = 0.0) -> None:
    """Emit 0.1 s position ticks while PLAYING from `start` for `seconds`."""
    player._set_state_for_test(PlayerState.PLAYING)
    for i in range(round(seconds * 10) + 1):
        player.position_changed.emit(start + i / 10)


# Spec: TC-29-03
def test_load_failures(player: Player, tmp_path: Path) -> None:
    root = tmp_path / "root"
    music = tmp_path / "music"
    watcher = _watcher(music, "song.mp3")
    track = watcher.library().tracks[0]
    path = history_path(root)
    path.parent.mkdir(parents=True)

    # Corrupt: starts empty, and the first save keeps the original bytes.
    path.write_bytes(b"{ not json")
    history = PlayHistory(root, player, watcher)
    assert history.load_failed is True
    assert history.read_only is False
    assert history.stats_for(track) == SongStats()
    history.set_favourite(track, True)
    history.flush()
    assert path.with_name("play_history.json.corrupt.bak").read_bytes() == b"{ not json"
    assert load_history(root)["song.mp3"].favourited is not None

    # Newer schema: starts empty, works in memory, never writes.
    newer = json.dumps({"schema_version": 2, "songs": {}}).encode()
    path.write_bytes(newer)
    history = PlayHistory(root, player, watcher)
    assert history.read_only is True
    assert history.load_failed is False
    history.set_favourite(track, True)
    assert history.stats_for(track).favourited is not None
    history.flush()
    assert path.read_bytes() == newer


# Spec: TC-29-07
def test_once_per_listen(player: Player, tmp_path: Path) -> None:
    music = tmp_path / "music"
    song = _song(music)
    history = PlayHistory(tmp_path / "root", player, _watcher(music, "song.mp3"))
    track = _track(song)
    player._set_duration_for_test(100)

    player.set_source(song)
    _listen(player, 60)
    _listen(player, 60, start=60)  # same listen, past the threshold again
    assert history.stats_for(track).plays == 1

    # Repeat-one replay: set_source of the same path, no current_changed.
    player.set_source(song)
    _listen(player, 60)
    assert history.stats_for(track).plays == 2

    # Play after Stop replays without set_source.
    player.state_changed.emit(PlayerState.STOPPED)
    _listen(player, 60)
    assert history.stats_for(track).plays == 3


# Spec: TC-29-08
def test_source_changed(player: Player, tmp_path: Path, qtbot) -> None:
    song = _song(tmp_path)
    seen: list[object] = []
    player.source_changed.connect(seen.append)
    player.set_source(song)
    player.set_source(song)
    player.set_source(None)
    assert seen == [song, song, None]


# Spec: TC-29-09
def test_keying(player: Player, tmp_path: Path) -> None:
    root = tmp_path / "root"
    first = tmp_path / "first"
    song = _song(first)
    history = PlayHistory(root, player, _watcher(first, "song.mp3"))
    player._set_duration_for_test(100)
    player.set_source(song)
    _listen(player, 60)
    history.flush()
    saved = load_history(root)
    assert list(saved) == ["song.mp3"]
    assert saved["song.mp3"].plays == 1
    assert saved["song.mp3"].last_played is not None

    # The same file name in another folder shows the data: relative keys.
    second = tmp_path / "second"
    moved = PlayHistory(root, player, _watcher(second, "song.mp3"))
    assert moved.stats_for(_track(second / "song.mp3")).plays == 1
    assert [t.path for t in moved.smart_list(SmartList.MOST_PLAYED)] == [second / "song.mp3"]

    # A source outside the music folder records nothing and does not raise.
    outside = _song(tmp_path / "elsewhere")
    player.set_source(outside)
    _listen(player, 60)
    moved.flush()
    assert list(load_history(root)) == ["song.mp3"]
    assert moved.has_key(_track(outside)) is False

    # Trust boundary: a key spelled another way shows nothing.
    when = datetime(2026, 11, 18, tzinfo=UTC)
    save_history(root, {
        str(second / "song.mp3"): SongStats(plays=5, last_played=when),
        f"../{second.name}/song.mp3": SongStats(plays=7, last_played=when),
        "bad\x00name.mp3": SongStats(plays=9, last_played=when),
    })
    spelled = PlayHistory(root, player, _watcher(second, "song.mp3"))
    assert spelled.stats_for(_track(second / "song.mp3")) == SongStats()
    assert spelled.smart_list(SmartList.MOST_PLAYED) == []


# Spec: TC-29-10
def test_favourite(player: Player, tmp_path: Path, qtbot) -> None:
    root = tmp_path / "root"
    music = tmp_path / "music"
    watcher = _watcher(music, "song.mp3")
    track = watcher.library().tracks[0]
    history = PlayHistory(root, player, watcher)

    before = datetime.now(UTC)
    with qtbot.waitSignal(history.changed, timeout=500):
        history.set_favourite(track, True)
    hearted = history.stats_for(track).favourited
    assert hearted is not None and before <= hearted <= datetime.now(UTC)
    history.flush()
    assert load_history(root)["song.mp3"].favourited == hearted.replace(
        microsecond=hearted.microsecond // 1000 * 1000,
    )

    with qtbot.waitSignal(history.changed, timeout=500):
        history.set_favourite(track, False)
    assert history.stats_for(track).favourited is None
    history.flush()
    songs = json.loads(history_path(root).read_text(encoding="utf-8"))["songs"]
    assert songs == {}

    # A song outside the music folder has no key: nothing changes.
    with qtbot.assertNotEmitted(history.changed):
        history.set_favourite(_track(tmp_path / "elsewhere" / "x.mp3"), True)


# Spec: TC-29-11
def test_smart_list_skips_missing(player: Player, tmp_path: Path) -> None:
    root = tmp_path / "root"
    music = tmp_path / "music"
    names = [f"s{i:02}.mp3" for i in range(51)]
    t0 = datetime(2026, 11, 18, tzinfo=UTC)
    # s50 is the most played and the newest; it is missing from the library.
    save_history(root, {
        n: SongStats(plays=i + 1, last_played=t0 + timedelta(minutes=i))
        for i, n in enumerate(names)
    })
    present = names[:-1]
    history = PlayHistory(root, player, _watcher(music, *present))
    for which in (SmartList.MOST_PLAYED, SmartList.RECENTLY_PLAYED):
        tracks = history.smart_list(which)
        assert len(tracks) == 50
        assert tracks[0].path == music / "s49.mp3"
    history.set_favourite(history.smart_list(SmartList.MOST_PLAYED)[0], True)
    history.flush()
    assert "s50.mp3" in load_history(root)  # the missing song stays in the file
    assert [t.path.name for t in history.smart_list(SmartList.FAVOURITES)] == ["s49.mp3"]
