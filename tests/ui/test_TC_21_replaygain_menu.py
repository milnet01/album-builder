"""MainWindow Playback menu + restore-path re-level - Spec 21 (TC-21-08/09)."""

from __future__ import annotations

import pytest
from mutagen.id3 import ID3, TXXX

import album_builder.ui.main_window as mw
from album_builder.persistence import settings as st
from album_builder.persistence.settings import ReplayGainSettings
from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow


# Spec: TC-21-08
def test_playback_menu_structure_and_wiring(main_window, monkeypatch) -> None:
    win = main_window
    # A Playback menu exists, positioned after View and before Help.
    titles = [a.text() for a in win.menuBar().actions()]
    assert titles == ["File", "View", "Playback", "Help"]
    # Toggle reflects the persisted (default off) state at startup.
    assert win._rg_toggle_action.isChecked() is False

    persisted: list = []
    monkeypatch.setattr(mw, "write_replaygain", lambda s: persisted.append(s))
    enabled_calls: list = []
    monkeypatch.setattr(win._replaygain, "set_enabled", lambda on: enabled_calls.append(on))

    win._rg_toggle_action.trigger()  # checkable -> now checked, emits triggered(True)
    assert enabled_calls == [True]
    assert persisted[-1].enabled is True

    mode_calls: list = []
    monkeypatch.setattr(win._replaygain, "set_mode", lambda m: mode_calls.append(m))
    track_act = next(a for a in win._rg_mode_group.actions() if a.text() == "Track")
    track_act.trigger()
    assert mode_calls == ["track"]
    assert persisted[-1].mode == "track"


def test_toggle_persist_failure_is_caught(main_window, monkeypatch) -> None:
    win = main_window

    def boom(_s):
        raise OSError("disk full")

    monkeypatch.setattr(mw, "write_replaygain", boom)
    # Must NOT propagate out of the triggered slot (would qFatal the app).
    win._rg_toggle_action.trigger()
    assert win._rg_toggle_action.isChecked() is True  # runtime state still flipped


# Spec: TC-21-09
def test_restore_path_levels_the_restored_track(qtbot, tracks_dir, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    st.write_replaygain(ReplayGainSettings(enabled=True, mode="album"))
    track_path = (tracks_dir / "01-intro.mp3").resolve()
    id3 = ID3(track_path)
    id3.add(TXXX(encoding=3, desc="REPLAYGAIN_ALBUM_GAIN", text=["-6.0 dB"]))
    id3.save(track_path, v2_version=3)

    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState(last_played_track_path=track_path)
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)

    # The restore branch (which bypasses the controller) levelled the restored
    # track: the factor is the album gain, not 1.0.
    assert win._player._replaygain_factor == pytest.approx(10 ** (-6 / 20))
