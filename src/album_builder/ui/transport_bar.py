"""Transport bar - Spec 06 §user-visible behavior, transport bar elements.

The widget is dumb-on-purpose: it reflects player state, the player is
the source of truth. Buttons call ``player.toggle()`` / ``player.set_muted``
directly; the volume slider writes via ``player.set_volume``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from album_builder.domain.play_queue import RepeatMode
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player, PlayerState
from album_builder.ui.theme import Glyphs

# Spec 16 repeat button cycle. An explicit 3-way map, NOT enum-ordinal
# succession: RepeatMode is declared OFF/ONE/ALL, which does not match this
# OFF->ALL->ONE cycle order, so `RepeatMode((i + 1) % 3)` would be wrong.
_NEXT_REPEAT = {
    RepeatMode.OFF: RepeatMode.ALL,
    RepeatMode.ALL: RepeatMode.ONE,
    RepeatMode.ONE: RepeatMode.OFF,
}


class TransportBar(QWidget):
    def __init__(
        self,
        player: Player,
        controller: PlaybackController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._controller = controller
        self.setObjectName("TransportBar")

        # Queue-level controls (Spec 16) - drive the PlaybackController.
        self.btn_shuffle = QPushButton(Glyphs.SHUFFLE, objectName="TransportShuffle")
        self.btn_shuffle.setAccessibleName("Shuffle")
        self.btn_shuffle.setCheckable(True)
        self.btn_shuffle.setFixedWidth(36)
        # setChecked emits toggled, not clicked, so this seeds the visual
        # without firing set_shuffle at construction.
        self.btn_shuffle.setChecked(controller.shuffle_enabled())
        self.btn_shuffle.clicked.connect(self._on_shuffle_clicked)

        self.btn_prev = QPushButton(Glyphs.SKIP_PREV, objectName="TransportPrev")
        self.btn_prev.setAccessibleName("Previous")
        self.btn_prev.setFixedWidth(36)
        self.btn_prev.clicked.connect(self._on_prev_clicked)

        self.btn_play = QPushButton(Glyphs.PLAY, objectName="TransportPlay")
        self.btn_play.setAccessibleName("Play")
        self.btn_play.setFixedWidth(48)
        self.btn_play.clicked.connect(self._on_play_clicked)

        self.btn_next = QPushButton(Glyphs.SKIP_NEXT, objectName="TransportNext")
        self.btn_next.setAccessibleName("Next")
        self.btn_next.setFixedWidth(36)
        self.btn_next.clicked.connect(self._on_next_clicked)

        # Repeat: 3-state cycle, no static glyph - _sync_repeat_glyph is the
        # sole owner of its text/checked/accessible name (seeded below).
        self.btn_repeat = QPushButton(objectName="TransportRepeat")
        self.btn_repeat.setCheckable(True)
        self.btn_repeat.setFixedWidth(36)
        self.btn_repeat.clicked.connect(self._cycle_repeat)

        self.lbl_current = QLabel("0:00", objectName="TransportTime")
        self.lbl_current.setAccessibleName("Current playback time")

        self.scrubber = QSlider(Qt.Orientation.Horizontal, objectName="TransportScrubber")
        self.scrubber.setRange(0, 0)
        self.scrubber.setAccessibleName("Playback position")
        # L7-H3: seek on release rather than on every sliderMoved tick.
        # Hundreds of seek() calls during a drag flooded QMediaPlayer's
        # positionChanged loop and produced audible stutter on slow
        # backends. Reading self.scrubber.value() inside the slot picks
        # up the final drag position (sliderReleased fires after the
        # value is committed).
        self.scrubber.sliderReleased.connect(self._on_scrub_released)

        self.lbl_duration = QLabel("0:00", objectName="TransportTime")
        self.lbl_duration.setAccessibleName("Track duration")

        self.btn_mute = QPushButton(Glyphs.UNMUTE, objectName="TransportMute")
        self.btn_mute.setAccessibleName("Mute")
        self.btn_mute.setFixedWidth(36)
        self.btn_mute.clicked.connect(self._on_mute_clicked)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal, objectName="TransportVolume")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(player.volume())
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.setAccessibleName("Volume")
        self.volume_slider.valueChanged.connect(player.set_volume)

        self.buffering_label = QLabel("Buffering...", objectName="TransportBuffering")
        self.buffering_label.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        layout.addWidget(self.btn_shuffle)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_repeat)
        layout.addWidget(self.buffering_label)
        layout.addWidget(self.lbl_current)
        layout.addWidget(self.scrubber, stretch=1)
        layout.addWidget(self.lbl_duration)
        layout.addSpacing(12)
        layout.addWidget(self.btn_mute)
        layout.addWidget(self.volume_slider)

        # Reflect player state.
        player.position_changed.connect(self._on_position_changed)
        player.duration_changed.connect(self._on_duration_changed)
        player.state_changed.connect(self._on_state_changed)
        player.buffering_changed.connect(self._on_buffering_changed)
        # Sync the mute glyph to whatever was restored from settings.
        self._sync_mute_glyph()
        # Seed the repeat button from the controller's current mode.
        self._sync_repeat_glyph(controller.repeat_mode())

    # ---- Slots ------------------------------------------------------

    def _on_play_clicked(self) -> None:
        self._player.toggle()

    def _on_prev_clicked(self) -> None:
        self._controller.previous()

    def _on_next_clicked(self) -> None:
        self._controller.next()

    def _on_shuffle_clicked(self) -> None:
        # Checkable button: isChecked() already reflects the post-click state.
        self._controller.set_shuffle(self.btn_shuffle.isChecked())

    def _cycle_repeat(self) -> None:
        # Read the controller's live mode, step the explicit cycle, and let
        # _sync_repeat_glyph set the authoritative checked state (overriding the
        # checkable button's native auto-toggle that fired before this slot).
        nxt = _NEXT_REPEAT[self._controller.repeat_mode()]
        self._controller.set_repeat(nxt)
        self._sync_repeat_glyph(nxt)

    def _sync_repeat_glyph(self, mode: RepeatMode) -> None:
        self.btn_repeat.setChecked(mode is not RepeatMode.OFF)
        if mode is RepeatMode.ONE:
            self.btn_repeat.setText(Glyphs.REPEAT_ONE)
            self.btn_repeat.setAccessibleName("Repeat one")
        elif mode is RepeatMode.ALL:
            self.btn_repeat.setText(Glyphs.REPEAT_ALL)
            self.btn_repeat.setAccessibleName("Repeat all")
        else:
            self.btn_repeat.setText(Glyphs.REPEAT_ALL)
            self.btn_repeat.setAccessibleName("Repeat off")

    def _on_mute_clicked(self) -> None:
        self._player.set_muted(not self._player.muted())
        self._sync_mute_glyph()

    def _on_scrub_released(self) -> None:
        self._player.seek(float(self.scrubber.value()))

    def _on_position_changed(self, seconds: float) -> None:
        # Don't fight the user mid-drag.
        if not self.scrubber.isSliderDown():
            self.scrubber.setValue(int(seconds))
        self.lbl_current.setText(self._format_time(seconds))

    def _on_duration_changed(self, seconds: float) -> None:
        self.scrubber.setRange(0, round(seconds))
        self.lbl_duration.setText(self._format_time(seconds))

    def _on_state_changed(self, state) -> None:
        if state == PlayerState.PLAYING:
            self.btn_play.setText(Glyphs.PAUSE)
            self.btn_play.setAccessibleName("Pause")
        else:
            self.btn_play.setText(Glyphs.PLAY)
            self.btn_play.setAccessibleName("Play")

    def _on_buffering_changed(self, buffering: bool) -> None:
        self.buffering_label.setVisible(buffering)

    def _sync_mute_glyph(self) -> None:
        if self._player.muted():
            self.btn_mute.setText(Glyphs.MUTE)
            self.btn_mute.setAccessibleName("Unmute")
        else:
            self.btn_mute.setText(Glyphs.UNMUTE)
            self.btn_mute.setAccessibleName("Mute")

    @staticmethod
    def _format_time(seconds: float) -> str:
        # Spec 06 display: m:ss; h:mm:ss past the hour boundary.
        # Classic half-up rounding via int(s + 0.5) — same as
        # _format_duration in library_pane.
        s = int(seconds + 0.5)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"
