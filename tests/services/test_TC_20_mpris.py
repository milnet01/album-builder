"""Tests for album_builder.services.mpris - Spec 20 (Phase G).

Two tiers, mirroring test_player.py:

- **Unit tier (always runs)** - pure mapping helpers, adaptor getters/setters
  against fake Player/PlaybackController doubles, the service's chokepoint
  wiring + guard tested at the interceptable seam, and cover-art lifecycle.
  None require a live D-Bus session.
- **Integration tier (opt-in, AB_INTEGRATION_DBUS=1)** - registers against the
  real session bus and reads the Metadata property back over the wire to assert
  the load-bearing `x` / `o` / `as` signatures (opaque in-process). Skipped by
  default (headless/CI has no bus).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QObject
from PyQt6.QtDBus import QDBusArgument, QDBusConnection, QDBusObjectPath
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QWidget

from album_builder.domain.play_queue import RepeatMode
from album_builder.domain.track import Track
from album_builder.services.mpris import (
    _TRACKID_PREFIX,
    BUS_NAME,
    OBJECT_PATH,
    MediaPlayer2Adaptor,
    MediaPlayer2PlayerAdaptor,
    MprisService,
    _metadata_variant_map,
    loop_status,
    playback_status,
    repeat_mode,
    track_metadata,
)
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player, PlayerState

INTEGRATION = pytest.mark.skipif(
    os.environ.get("AB_INTEGRATION_DBUS") != "1",
    reason="Set AB_INTEGRATION_DBUS=1 to run the live-session-bus wire-signature test",
)


@pytest.fixture(autouse=True)
def _drop_mpris_bus_name():
    """Force-drop the well-known bus name after every test so a service that
    registered (and a test that flipped `available=False`, bypassing its own
    unregister) doesn't leak the name into the next test's registration."""
    yield
    bus = QDBusConnection.sessionBus()
    bus.unregisterObject(OBJECT_PATH)
    bus.unregisterService(BUS_NAME)


def _track(**overrides) -> Track:
    base = dict(
        path=Path("/x/a.mp3"), title="Song", artist="Artist", album_artist="Artist",
        composer="", album="Alb", comment="", lyrics_text=None, cover_data=None,
        cover_mime=None, duration_seconds=200.0, file_size_bytes=1, is_missing=False,
    )
    base.update(overrides)
    return Track(**base)


def _player_adaptor(host, player, controller, art_url="file:///art.jpg", track_no=7):
    return MediaPlayer2PlayerAdaptor(
        host, player, controller, lambda: art_url, lambda: track_no
    )


# ---- TC-20-01/02: enum <-> MPRIS string mapping -----------------------------


# Spec: TC-20-01
def test_playback_status_maps_all_states() -> None:
    assert playback_status(PlayerState.PLAYING) == "Playing"
    assert playback_status(PlayerState.PAUSED) == "Paused"
    assert playback_status(PlayerState.STOPPED) == "Stopped"
    assert playback_status(PlayerState.ERROR) == "Stopped"


# Spec: TC-20-02
def test_loop_status_maps_and_inverts() -> None:
    assert loop_status(RepeatMode.OFF) == "None"
    assert loop_status(RepeatMode.ONE) == "Track"
    assert loop_status(RepeatMode.ALL) == "Playlist"
    assert repeat_mode("None") == RepeatMode.OFF
    assert repeat_mode("Track") == RepeatMode.ONE
    assert repeat_mode("Playlist") == RepeatMode.ALL
    assert repeat_mode("something-invalid") == RepeatMode.OFF


# ---- TC-20-03: track_metadata pure dict -------------------------------------


# Spec: TC-20-03
def test_track_metadata_shape_and_types() -> None:
    t = _track(duration_seconds=200.0)
    m = track_metadata(t, "file:///art.jpg", 7)
    assert isinstance(m["mpris:trackid"], QDBusObjectPath)
    assert m["mpris:trackid"].path() == _TRACKID_PREFIX + "7"
    assert m["mpris:length"] == round(200.0 * 1_000_000)
    assert m["xesam:title"] == "Song"
    assert m["xesam:artist"] == ["Artist"]
    assert m["xesam:album"] == "Alb"
    assert m["mpris:artUrl"] == "file:///art.jpg"


def test_track_metadata_omits_art_when_none() -> None:
    m = track_metadata(_track(), None, 1)
    assert "mpris:artUrl" not in m


def test_track_metadata_none_track_is_empty_map() -> None:
    assert track_metadata(None, None, 3) == {}


def test_metadata_variant_map_wraps_carriers() -> None:
    # The direct regression guard for the SIGABRT crash: the getter value must be
    # a plain dict (never a whole-map QDBusArgument), with per-value carriers.
    vm = _metadata_variant_map(track_metadata(_track(), "file:///a.png", 2))
    assert isinstance(vm, dict)
    assert not isinstance(vm, QDBusArgument)
    assert isinstance(vm["mpris:trackid"], QDBusObjectPath)
    assert isinstance(vm["mpris:length"], QDBusArgument)
    assert isinstance(vm["xesam:artist"], QDBusArgument)
    assert vm["xesam:title"] == "Song"


# ---- TC-20-04: Player.seeked pulse ------------------------------------------


# Spec: TC-20-04
def test_seek_emits_seeked_with_clamped_lower_bound() -> None:
    p = Player()
    spy = QSignalSpy(p.seeked)
    p.seek(-5.0)  # clamps up to 0.0
    assert len(spy) == 1
    assert spy[0][0] == pytest.approx(0.0)


def test_seek_emits_seeked_with_clamped_upper_bound() -> None:
    p = Player()
    p._set_duration_for_test(100.0)  # so the dur-1.0 upper clamp is live
    spy = QSignalSpy(p.seeked)
    p.seek(500.0)  # clamps down to dur - 1.0 = 99.0
    assert len(spy) == 1
    assert spy[0][0] == pytest.approx(99.0)


def test_seek_pulses_even_on_repeat_seek() -> None:
    p = Player()
    p._set_duration_for_test(100.0)
    spy = QSignalSpy(p.seeked)
    p.seek(10.0)
    p.seek(10.0)  # no-op re-seek still pulses (harmless over-emit)
    assert len(spy) == 2


# ---- TC-20-05/06/07/08: player adaptor getters/setters/methods --------------


# Spec: TC-20-05
def test_player_adaptor_scalar_getters() -> None:
    host = QObject()
    player = MagicMock()
    player.state.return_value = PlayerState.PLAYING
    player.volume.return_value = 40
    player.position.return_value = 12.0
    controller = MagicMock()
    controller.repeat_mode.return_value = RepeatMode.ALL
    controller.shuffle_enabled.return_value = True
    controller.current_track.return_value = _track()
    a = _player_adaptor(host, player, controller)
    assert a.PlaybackStatus == "Playing"
    assert a.LoopStatus == "Playlist"
    assert a.Shuffle is True
    assert a.Volume == pytest.approx(0.4)
    assert a.Position == 12_000_000
    assert a.Rate == 1.0
    assert a.MinimumRate == 1.0
    assert a.MaximumRate == 1.0
    md = a.Metadata
    assert isinstance(md, dict)
    assert not isinstance(md, QDBusArgument)
    assert isinstance(md["mpris:trackid"], QDBusObjectPath)
    assert isinstance(md["mpris:length"], QDBusArgument)
    assert isinstance(md["xesam:artist"], QDBusArgument)


# Spec: TC-20-06
def test_player_adaptor_setters() -> None:
    host = QObject()
    player = MagicMock()
    player.volume.return_value = 50
    controller = MagicMock()
    a = _player_adaptor(host, player, controller)

    a.LoopStatus = "Track"
    controller.set_repeat.assert_called_once_with(RepeatMode.ONE)
    a.Shuffle = True
    controller.set_shuffle.assert_called_once_with(True)
    a.Volume = 0.4
    player.set_volume.assert_called_once_with(40)

    # Rate write is accepted and inert.
    a.Rate = 2.0
    assert a.Rate == 1.0

    # Out-of-range volume forwards the raw scaled int (Player clamps); the guard
    # for mute independence is that Volume reflects the underlying level.
    player.set_volume.reset_mock()
    a.Volume = 1.5
    player.set_volume.assert_called_once_with(150)
    player.set_volume.reset_mock()
    a.Volume = -0.2
    player.set_volume.assert_called_once_with(-20)


# Spec: TC-20-07
def test_player_adaptor_methods_and_setposition_guard() -> None:
    host = QObject()
    player = MagicMock()
    player.position.return_value = 5.0
    player.duration.return_value = 200.0
    controller = MagicMock()
    a = _player_adaptor(host, player, controller, track_no=3)

    a.Next()
    controller.next.assert_called_once()
    a.Previous()
    controller.previous.assert_called_once()
    a.Play()
    player.play.assert_called_once()
    a.Pause()
    player.pause.assert_called_once()
    a.PlayPause()
    player.toggle.assert_called_once()
    a.Stop()
    player.stop.assert_called_once()

    a.Seek(2_000_000)
    player.seek.assert_called_once_with(pytest.approx(7.0))

    player.seek.reset_mock()
    current_id = QDBusObjectPath(_TRACKID_PREFIX + "3")
    a.SetPosition(current_id, 3_000_000)
    player.seek.assert_called_once_with(pytest.approx(3.0))

    # Stale trackid -> ignored.
    player.seek.reset_mock()
    a.SetPosition(QDBusObjectPath(_TRACKID_PREFIX + "999"), 3_000_000)
    player.seek.assert_not_called()

    # Out-of-range position -> no-op (range-checked here, not delegated).
    a.SetPosition(current_id, -1)
    a.SetPosition(current_id, 200 * 1_000_000 + 1)
    player.seek.assert_not_called()


# Spec: TC-20-08
def test_player_adaptor_can_flags() -> None:
    host = QObject()
    player = MagicMock()
    controller = MagicMock()
    a = _player_adaptor(host, player, controller)

    controller.play_order.return_value = (_track(),)
    controller.current_track.return_value = _track()
    player.duration.return_value = 200.0
    assert a.CanGoNext is True
    assert a.CanGoPrevious is True
    assert a.CanPlay is True
    assert a.CanPause is True
    assert a.CanSeek is True
    assert a.CanControl is True

    controller.play_order.return_value = ()
    controller.current_track.return_value = None
    player.duration.return_value = 0.0
    assert a.CanGoNext is False
    assert a.CanGoPrevious is False
    assert a.CanPlay is False
    assert a.CanPause is False
    assert a.CanSeek is False


# ---- TC-20-09/10: service guard + chokepoint wiring -------------------------


def _service() -> MprisService:
    player = Player()
    controller = PlaybackController(player)
    return MprisService(player, controller, QWidget())


# Spec: TC-20-09
def test_unavailable_service_sends_nothing() -> None:
    svc = _service()
    svc.available = False
    sent: list = []
    svc._send = lambda msg: sent.append(msg)
    svc._player.state_changed.emit(PlayerState.PLAYING)
    assert sent == []
    seeked_spy = QSignalSpy(svc._player_adaptor.Seeked)
    svc._player.seeked.emit(1.0)
    assert len(seeked_spy) == 0
    # No raise on the unavailable path.


def test_forced_available_service_sends_once() -> None:
    svc = _service()
    svc.available = True
    sent: list = []
    svc._send = lambda msg: sent.append(msg)
    svc._player.state_changed.emit(PlayerState.PLAYING)
    assert len(sent) == 1
    seeked_spy = QSignalSpy(svc._player_adaptor.Seeked)
    svc._player.seeked.emit(1.0)
    assert len(seeked_spy) == 1
    svc.unregister()


# Spec: TC-20-10
def test_chokepoint_wiring_maps_signals_to_properties() -> None:
    svc = _service()
    calls: list = []
    svc._emit_properties_changed = lambda iface, changed, inval: calls.append(
        (iface, set(changed.keys()))
    )
    seeked: list = []
    svc._emit_seeked = lambda us: seeked.append(us)

    iface = "org.mpris.MediaPlayer2.Player"
    svc._player.state_changed.emit(PlayerState.PLAYING)
    svc._controller.current_changed.emit(None)
    svc._player.duration_changed.emit(200.0)
    svc._controller.queue_changed.emit(())
    svc._player.volume_changed.emit(50)
    svc._controller.shuffle_changed.emit(True)
    svc._controller.repeat_changed.emit(RepeatMode.ONE)

    by_keys = [keys for _i, keys in calls]
    assert ({"PlaybackStatus"} in by_keys)
    assert any({"Metadata", "CanGoNext", "CanGoPrevious", "CanPlay", "CanPause",
                "CanSeek"} == k for k in by_keys)
    assert ({"CanSeek"} in by_keys)
    assert ({"CanGoNext", "CanGoPrevious"} in by_keys)
    assert ({"Volume"} in by_keys)
    assert ({"Shuffle"} in by_keys)
    assert ({"LoopStatus"} in by_keys)
    assert all(i == iface for i, _k in calls)
    assert len(calls) == 7

    svc._player.seeked.emit(2.5)
    assert seeked == [round(2.5 * 1_000_000)]


# ---- TC-20-11: cover-art lifecycle ------------------------------------------


# Spec: TC-20-11
def test_cover_art_lifecycle() -> None:
    svc = _service()
    svc.available = False  # art refresh is bus-independent
    with_cover = _track(cover_data=b"\x89PNG\r\n\x1a\n", cover_mime="image/png")

    svc._controller.current_changed.emit(with_cover)
    assert svc._art_url is not None and svc._art_url.startswith("file://")
    art_path = Path(svc._art_url[len("file://"):])
    assert art_path.exists()
    m = track_metadata(with_cover, svc._art_url, svc._track_no)
    assert m["mpris:artUrl"] == svc._art_url

    # Switch to a track with no cover -> prior temp file removed, art dropped.
    svc._controller.current_changed.emit(_track(title="No Cover"))
    assert svc._art_url is None
    assert not art_path.exists()

    # Re-add, then clear on None.
    svc._controller.current_changed.emit(with_cover)
    art_path2 = Path(svc._art_url[len("file://"):])
    assert art_path2.exists()
    svc._controller.current_changed.emit(None)
    assert svc._art_url is None
    assert not art_path2.exists()


# ---- TC-20-15/16: root adaptor + OpenUri no-op ------------------------------


# Spec: TC-20-15
def test_root_adaptor_properties_and_methods(qtbot, monkeypatch) -> None:
    app = QApplication.instance()
    app.setApplicationName("Album Builder")
    app.setDesktopFileName("album-builder")
    host = QObject()
    window = QWidget()
    qtbot.addWidget(window)
    window.hide()
    a = MediaPlayer2Adaptor(host, window, app)

    assert a.CanQuit is True
    assert a.CanRaise is True
    assert a.HasTrackList is False
    assert a.Identity == "Album Builder"
    assert a.DesktopEntry == "album-builder"
    assert a.SupportedUriSchemes == ["file"]
    assert "audio/mpeg" in a.SupportedMimeTypes
    assert "audio/mp4" in a.SupportedMimeTypes

    quit_calls: list = []
    monkeypatch.setattr(app, "quit", lambda: quit_calls.append(True))
    a.Quit()
    assert quit_calls == [True]

    a.Raise()
    assert window.isVisible()


# Spec: TC-20-16
def test_openuri_is_a_noop() -> None:
    host = QObject()
    player = MagicMock()
    controller = MagicMock()
    a = _player_adaptor(host, player, controller)
    a.OpenUri("file:///x.mp3")  # must not raise
    controller.play_tracks.assert_not_called()
    controller.preview.assert_not_called()
    player.play.assert_not_called()


# ---- Integration tier (opt-in) ----------------------------------------------


@INTEGRATION
def test_metadata_wire_signatures_over_real_bus(qtbot) -> None:
    """Read Metadata back over the live session bus and assert the load-bearing
    wire signatures (`x` length, `o` trackid, `as` artist) that are opaque
    in-process. This is the direct proof the SIGABRT fix stays conformant."""
    player = Player()
    controller = PlaybackController(player)
    svc = MprisService(player, controller, QWidget())
    assert svc.available, "no session bus available for the integration test"
    controller.current_track = lambda: _track()
    svc._refresh_art(_track())

    proc = subprocess.Popen(
        [
            "dbus-send", "--session", "--print-reply",
            "--dest=" + "org.mpris.MediaPlayer2.albumbuilder",
            "/org/mpris/MediaPlayer2",
            "org.freedesktop.DBus.Properties.Get",
            "string:org.mpris.MediaPlayer2.Player", "string:Metadata",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    # Pump the Qt event loop so the property read is serviced while dbus-send waits.
    qtbot.waitUntil(lambda: proc.poll() is not None, timeout=5000)
    out = proc.stdout.read()
    svc.unregister()
    assert "int64" in out                       # mpris:length -> x
    assert "object path" in out                 # mpris:trackid -> o
    assert "array [" in out and "string" in out  # xesam:artist -> as
