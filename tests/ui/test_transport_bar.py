"""Tests for album_builder.ui.transport_bar - Spec 06 transport widgets."""

from __future__ import annotations

import pytest

from album_builder.services.player import Player, PlayerState
from album_builder.ui.theme import Glyphs
from album_builder.ui.transport_bar import TransportBar


@pytest.fixture
def player_and_bar(qtbot):
    p = Player()
    b = TransportBar(p)
    qtbot.addWidget(b)
    return p, b


# Spec: TC-06-10
def test_initial_state_shows_play_glyph(player_and_bar) -> None:
    _, b = player_and_bar
    assert b.btn_play.text() == Glyphs.PLAY


# Spec: TC-06-10
def test_initial_state_shows_unmute_glyph(player_and_bar) -> None:
    _, b = player_and_bar
    assert b.btn_mute.text() == Glyphs.UNMUTE


# Spec: TC-06-14
def test_initial_buffering_label_hidden(player_and_bar) -> None:
    _, b = player_and_bar
    assert not b.buffering_label.isVisible()


# Spec: TC-06-14
def test_buffering_label_shown_on_buffering_signal(player_and_bar) -> None:
    p, b = player_and_bar
    # Qt's setVisible() only reports True once the parent widget itself is
    # shown — the bar is a top-level QWidget under qtbot, so show() once.
    b.show()
    p.buffering_changed.emit(True)
    assert b.buffering_label.isVisible()
    p.buffering_changed.emit(False)
    assert not b.buffering_label.isVisible()


# Spec: TC-06-11
def test_volume_slider_writes_to_player(player_and_bar) -> None:
    p, b = player_and_bar
    b.volume_slider.setValue(40)
    assert p.volume() == 40


# Spec: TC-06-11
def test_volume_slider_initialises_from_player(qtbot) -> None:
    """Constructing TransportBar after the player's volume has been set
    (e.g. restored from settings.json) must reflect that value, not the
    Qt default."""
    p = Player()
    p.set_volume(35)
    b = TransportBar(p)
    qtbot.addWidget(b)
    assert b.volume_slider.value() == 35


# Spec: TC-06-12
def test_mute_button_click_mutes(player_and_bar) -> None:
    p, b = player_and_bar
    assert p.muted() is False
    b.btn_mute.click()
    assert p.muted() is True
    assert b.btn_mute.text() == Glyphs.MUTE


# Spec: TC-06-12
def test_mute_button_click_unmutes(player_and_bar) -> None:
    p, b = player_and_bar
    p.set_muted(True)
    b._sync_mute_glyph()
    b.btn_mute.click()
    assert p.muted() is False
    assert b.btn_mute.text() == Glyphs.UNMUTE


# Spec: TC-06-12
def test_mute_glyph_syncs_to_restored_state(qtbot) -> None:
    """Constructing TransportBar with a player whose mute was restored from
    settings.json must show the muted glyph, not the default unmuted one."""
    p = Player()
    p.set_muted(True)
    b = TransportBar(p)
    qtbot.addWidget(b)
    assert b.btn_mute.text() == Glyphs.MUTE


# Spec: TC-06-13
def test_state_playing_shows_pause_glyph(player_and_bar) -> None:
    p, b = player_and_bar
    p.state_changed.emit(PlayerState.PLAYING)
    assert b.btn_play.text() == Glyphs.PAUSE
    assert b.btn_play.accessibleName() == "Pause"


# Spec: TC-06-13
def test_state_stopped_shows_play_glyph(player_and_bar) -> None:
    p, b = player_and_bar
    p.state_changed.emit(PlayerState.PLAYING)
    p.state_changed.emit(PlayerState.STOPPED)
    assert b.btn_play.text() == Glyphs.PLAY
    assert b.btn_play.accessibleName() == "Play"


# Spec: TC-06-13
def test_state_paused_shows_play_glyph(player_and_bar) -> None:
    p, b = player_and_bar
    p.state_changed.emit(PlayerState.PLAYING)
    p.state_changed.emit(PlayerState.PAUSED)
    assert b.btn_play.text() == Glyphs.PLAY


# Spec: TC-06-08
def test_duration_change_updates_scrubber_range(player_and_bar) -> None:
    p, b = player_and_bar
    p.duration_changed.emit(180.0)
    assert b.scrubber.minimum() == 0
    assert b.scrubber.maximum() == 180
    assert b.lbl_duration.text() == "3:00"


# Spec: TC-06-08
def test_position_change_updates_current_time(player_and_bar) -> None:
    p, b = player_and_bar
    # Scrubber needs a non-zero range before it can accept an integer value.
    p.duration_changed.emit(200.0)
    p.position_changed.emit(65.7)
    # The label uses half-up rounding (65.7 -> 66 -> "1:06");
    # the scrubber uses int-truncation (65.7 -> 65). The split is
    # deliberate — assert both arms so a future refactor can't silently
    # collapse them.
    assert b.lbl_current.text() == "1:06"
    assert b.scrubber.value() == 65


# Spec: L7-H3
def test_position_change_does_not_fight_drag(player_and_bar, monkeypatch) -> None:
    """When the user is mid-drag on the scrubber, incoming position ticks
    must NOT overwrite the slider position — but the time label MUST still
    update so the user sees where playback is."""
    _, b = player_and_bar
    b.scrubber.setRange(0, 200)
    b.scrubber.setValue(50)
    # sliderPressed.emit() doesn't flip isSliderDown() under the offscreen
    # QPA, so monkeypatch the accessor to force the guarded branch.
    monkeypatch.setattr(b.scrubber, "isSliderDown", lambda: True)
    b._on_position_changed(90.0)
    assert b.scrubber.value() == 50, (
        "L7-H3: incoming ticks must NOT overwrite scrubber while user drags"
    )
    assert b.lbl_current.text() == "1:30", (
        "L7-H3: time label must still update during drag"
    )


# Spec: TC-06-08
def test_format_time_unit_cases() -> None:
    assert TransportBar._format_time(0) == "0:00"
    assert TransportBar._format_time(0.5) == "0:01"  # half-up
    assert TransportBar._format_time(65) == "1:05"
    assert TransportBar._format_time(125.4) == "2:05"
    assert TransportBar._format_time(3600) == "1:00:00"
    assert TransportBar._format_time(3661) == "1:01:01"


# Spec: TC-06-09
def test_play_button_click_calls_toggle(player_and_bar, monkeypatch) -> None:
    p, b = player_and_bar
    called = []
    monkeypatch.setattr(p, "toggle", lambda: called.append(True))
    b.btn_play.click()
    assert called == [True]


# Spec: L7-H3 — scrubber must seek on `sliderReleased`, not on every
# `sliderMoved` tick. The known-trap note in Spec 06 acknowledged this
# but the wrong signal stayed wired — hundreds of seek() calls per drag
# spam QMediaPlayer's positionChanged loop and produce audible stutter
# on slow backends.
def test_scrubber_drag_does_not_seek_until_release(player_and_bar, monkeypatch) -> None:
    p, b = player_and_bar
    # Set a duration so scrubber values aren't clamped to 0.
    b.scrubber.setRange(0, 100)
    seeks: list[float] = []
    monkeypatch.setattr(p, "seek", lambda s: seeks.append(s))
    # Simulate a drag: many sliderMoved emissions with no release.
    for value in (10, 20, 30, 40, 45):
        b.scrubber.sliderMoved.emit(value)
    assert seeks == [], (
        "sliderMoved must NOT seek; only sliderReleased should "
        f"(L7-H3). Got: {seeks}"
    )
    # On release the final value seeks once.
    b.scrubber.setValue(45)
    b.scrubber.sliderReleased.emit()
    assert seeks == [45.0]
