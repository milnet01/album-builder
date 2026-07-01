"""Tests for album_builder.ui.transport_bar - Spec 06 transport widgets."""

from __future__ import annotations

import pytest

from album_builder.domain.play_queue import RepeatMode
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player, PlayerState
from album_builder.ui.now_playing_pane import NowPlayingPane
from album_builder.ui.theme import Glyphs, Palette, qt_stylesheet
from album_builder.ui.transport_bar import TransportBar


@pytest.fixture
def player_and_bar(qtbot):
    p = Player()
    b = TransportBar(p, PlaybackController(p))
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
    b = TransportBar(p, PlaybackController(p))
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
    b = TransportBar(p, PlaybackController(p))
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


# ---------------------------------------------------------------------------
# Spec 16 - transport controls (Phase C): prev / next / shuffle / repeat.
# ---------------------------------------------------------------------------


# Spec: TC-16-01
def test_transport_exposes_new_and_existing_buttons(player_and_bar) -> None:
    _, b = player_and_bar
    assert b.btn_prev.text() == Glyphs.SKIP_PREV
    assert b.btn_next.text() == Glyphs.SKIP_NEXT
    assert b.btn_shuffle.text() == Glyphs.SHUFFLE
    for attr in ("btn_play", "btn_mute", "scrubber", "volume_slider", "btn_repeat"):
        assert hasattr(b, attr)


# Spec: TC-16-02
def test_prev_next_buttons_call_controller(player_and_bar, monkeypatch) -> None:
    _, b = player_and_bar
    calls = []
    monkeypatch.setattr(b._controller, "previous", lambda: calls.append("prev"))
    monkeypatch.setattr(b._controller, "next", lambda: calls.append("next"))
    b.btn_prev.click()
    b.btn_next.click()
    assert calls == ["prev", "next"]


# Spec: TC-16-03
def test_shuffle_button_toggles_controller(player_and_bar) -> None:
    _, b = player_and_bar
    c = b._controller
    assert b.btn_shuffle.isChecked() is False
    b.btn_shuffle.click()
    assert b.btn_shuffle.isChecked() is True
    assert c.shuffle_enabled() is True
    b.btn_shuffle.click()
    assert b.btn_shuffle.isChecked() is False
    assert c.shuffle_enabled() is False


# Spec: TC-16-04
def test_shuffle_button_seeds_from_controller(qtbot, monkeypatch) -> None:
    p = Player()
    c = PlaybackController(p)
    c.set_shuffle(True)
    calls = []
    # Spy AFTER seeding state: construction must not call set_shuffle (it seeds
    # via setChecked, which emits toggled, not clicked).
    monkeypatch.setattr(c, "set_shuffle", lambda v: calls.append(v))
    b = TransportBar(p, c)
    qtbot.addWidget(b)
    assert b.btn_shuffle.isChecked() is True
    assert calls == []


# Spec: TC-16-05
def test_repeat_button_cycles_modes(player_and_bar) -> None:
    _, b = player_and_bar
    c = b._controller  # fresh controller: starts OFF
    assert c.repeat_mode() is RepeatMode.OFF
    b.btn_repeat.click()
    assert c.repeat_mode() is RepeatMode.ALL
    b.btn_repeat.click()
    assert c.repeat_mode() is RepeatMode.ONE
    b.btn_repeat.click()
    assert c.repeat_mode() is RepeatMode.OFF


# Spec: TC-16-06
def test_repeat_button_visual_per_mode(player_and_bar) -> None:
    _, b = player_and_bar
    # OFF (seeded at construction).
    assert b.btn_repeat.text() == Glyphs.REPEAT_ALL
    assert b.btn_repeat.isChecked() is False
    assert b.btn_repeat.accessibleName() == "Repeat off"
    # OFF -> ALL.
    b.btn_repeat.click()
    assert b.btn_repeat.text() == Glyphs.REPEAT_ALL
    assert b.btn_repeat.isChecked() is True
    assert b.btn_repeat.accessibleName() == "Repeat all"
    # ALL -> ONE.
    b.btn_repeat.click()
    assert b.btn_repeat.text() == Glyphs.REPEAT_ONE
    assert b.btn_repeat.isChecked() is True
    assert b.btn_repeat.accessibleName() == "Repeat one"
    # ONE -> OFF.
    b.btn_repeat.click()
    assert b.btn_repeat.text() == Glyphs.REPEAT_ALL
    assert b.btn_repeat.isChecked() is False
    assert b.btn_repeat.accessibleName() == "Repeat off"


# Spec: TC-16-07
def test_repeat_button_seeds_from_controller(qtbot, monkeypatch) -> None:
    p = Player()
    c = PlaybackController(p)
    c.set_repeat(RepeatMode.ALL)
    calls = []
    monkeypatch.setattr(c, "set_repeat", lambda m: calls.append(m))
    b = TransportBar(p, c)
    qtbot.addWidget(b)
    assert b.btn_repeat.isChecked() is True
    assert b.btn_repeat.text() == Glyphs.REPEAT_ALL
    assert b.btn_repeat.accessibleName() == "Repeat all"
    assert calls == []


# Spec: TC-16-08
def test_new_button_accessible_names(player_and_bar) -> None:
    _, b = player_and_bar
    assert b.btn_prev.accessibleName() == "Previous"
    assert b.btn_next.accessibleName() == "Next"
    assert b.btn_shuffle.accessibleName() == "Shuffle"
    # btn_repeat's mode-dependent name is covered by TC-16-06.


# Spec: TC-16-09
def test_existing_controls_unaffected_by_new_signature(
    player_and_bar, monkeypatch
) -> None:
    p, b = player_and_bar
    toggled = []
    monkeypatch.setattr(p, "toggle", lambda: toggled.append(True))
    b.btn_play.click()
    assert toggled == [True]
    assert p.muted() is False
    b.btn_mute.click()
    assert p.muted() is True
    b.volume_slider.setValue(42)
    assert p.volume() == 42


# Spec: TC-16-10
def test_prev_next_on_empty_queue_load_no_source(player_and_bar) -> None:
    p, b = player_and_bar
    # Fresh controller, empty queue, nothing ever loaded. next() calls a benign
    # player.stop() but never set_source, so source() stays None.
    b.btn_prev.click()
    b.btn_next.click()
    assert p.source() is None


# Spec: TC-16-11
def test_now_playing_pane_threads_controller(qtbot, monkeypatch) -> None:
    p = Player()
    c = PlaybackController(p)
    pane = NowPlayingPane(p, c)
    qtbot.addWidget(pane)
    calls = []
    monkeypatch.setattr(c, "next", lambda: calls.append(True))
    pane.transport.btn_next.click()
    assert calls == [True]


# Spec: TC-16-12
def test_shuffle_repeat_buttons_checkable_with_objectnames(player_and_bar) -> None:
    _, b = player_and_bar
    assert b.btn_shuffle.objectName() == "TransportShuffle"
    assert b.btn_repeat.objectName() == "TransportRepeat"
    assert b.btn_shuffle.isCheckable()
    assert b.btn_repeat.isCheckable()


# Spec: TC-16-13
def test_stylesheet_has_checked_rule_for_toggles() -> None:
    qss = qt_stylesheet(Palette.dark_colourful())
    assert "TransportShuffle:checked" in qss
    assert "TransportRepeat:checked" in qss
