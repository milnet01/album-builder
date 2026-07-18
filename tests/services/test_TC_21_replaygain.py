"""ReplayGain gain_factor + Player composite + ReplayGainService - Spec 21
(TC-21-04/05/06/07)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtTest import QSignalSpy

from album_builder.domain.track import Track
from album_builder.persistence.settings import ReplayGainSettings
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player
from album_builder.services.replaygain import ReplayGainService, gain_factor


def _track(track_gain=None, album_gain=None) -> Track:
    return Track(
        path=Path("/x.mp3"), title="t", artist="a", album_artist="a", composer="",
        album="", comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=1.0, file_size_bytes=1, is_missing=False,
        replaygain_track_gain=track_gain, replaygain_album_gain=album_gain,
    )


# ---- TC-21-04: gain_factor (pure) -------------------------------------------


# Spec: TC-21-04
def test_gain_factor_maps_and_falls_back() -> None:
    assert gain_factor(None, "album") == 1.0
    assert gain_factor(_track(album_gain=-6.0), "album") == pytest.approx(10 ** (-6 / 20))
    # album mode falls back to track gain when album absent
    assert gain_factor(_track(track_gain=-6.0), "album") == pytest.approx(10 ** (-6 / 20))
    # track mode picks track gain, falls back to album
    assert gain_factor(_track(track_gain=-3.0, album_gain=-6.0), "track") == pytest.approx(
        10 ** (-3 / 20)
    )
    assert gain_factor(_track(album_gain=-6.0), "track") == pytest.approx(10 ** (-6 / 20))
    # both absent -> 1.0
    assert gain_factor(_track(), "album") == 1.0
    # out-of-whitelist mode resolves like album (total function, no raise)
    assert gain_factor(_track(album_gain=-6.0), "weird") == pytest.approx(10 ** (-6 / 20))


# ---- TC-21-05: Player composite output --------------------------------------


# Spec: TC-21-05
def test_player_composite_output_and_clamp() -> None:
    p = Player()
    p.set_volume(80)
    p.set_replaygain_factor(0.5)
    assert p._output.volume() == pytest.approx(0.4)
    assert p.volume() == 80  # user volume unchanged by the factor (INV-21-1)
    p.set_volume(60)
    assert p._output.volume() == pytest.approx(0.3)  # factor still applied
    p.set_replaygain_factor(1.0)
    assert p._output.volume() == pytest.approx(0.6)
    # boost at volume 60 clamps (0.6 * 2 = 1.2 -> 1.0)
    p.set_replaygain_factor(2.0)
    assert p._output.volume() == pytest.approx(1.0)
    assert p.volume() == 60  # INV-21-1 under a non-1.0 factor


def test_set_replaygain_factor_emits_no_volume_changed() -> None:
    p = Player()
    p.set_volume(80)
    spy = QSignalSpy(p.volume_changed)
    p.set_replaygain_factor(0.5)
    assert len(spy) == 0  # INV-21-2
    # a real user-volume change still emits once
    p.set_volume(50)
    assert len(spy) == 1


# ---- TC-21-06/07: ReplayGainService -----------------------------------------


def _service(enabled, mode="album"):
    player = Player()
    controller = PlaybackController(player)
    factors: list[float] = []
    player.set_replaygain_factor = lambda f: factors.append(f)  # type: ignore[method-assign]
    svc = ReplayGainService(player, controller, ReplayGainSettings(enabled, mode))
    return svc, controller, factors


# Spec: TC-21-06
def test_service_disabled_drives_factor_1() -> None:
    svc, _c, factors = _service(enabled=False)
    svc.on_track_changed(_track(album_gain=-6.0))
    assert factors == [pytest.approx(1.0)]  # NOT not-called; always drives 1.0


def test_service_enabled_drives_track_factor() -> None:
    svc, _c, factors = _service(enabled=True, mode="album")
    t = _track(album_gain=-6.0)
    svc.on_track_changed(t)
    assert factors[-1] == pytest.approx(gain_factor(t, "album"))


def test_service_setters_relevel_cached_track_and_update_state() -> None:
    svc, _c, factors = _service(enabled=False, mode="album")
    t = _track(track_gain=-3.0, album_gain=-6.0)
    svc.on_track_changed(t)  # cached; disabled -> 1.0
    factors.clear()
    svc.set_enabled(True)  # re-levels the cached track, no second on_track_changed
    assert svc.enabled() is True
    assert factors[-1] == pytest.approx(gain_factor(t, "album"))
    svc.set_mode("track")
    assert svc.mode() == "track"
    assert factors[-1] == pytest.approx(gain_factor(t, "track"))


# Spec: TC-21-07
def test_service_uses_cache_not_live_controller_query() -> None:
    # Restore-path scenario: controller.current_track() is None (empty queue),
    # but on_track_changed(restored) must level the restored track, not 1.0.
    svc, controller, factors = _service(enabled=True, mode="album")
    assert controller.current_track() is None
    restored = _track(album_gain=-6.0)
    svc.on_track_changed(restored)
    assert factors[-1] == pytest.approx(gain_factor(restored, "album"))
    assert factors[-1] != pytest.approx(1.0)
