"""Transport bar - Spec 06 §user-visible behavior, transport bar elements.

The widget is dumb-on-purpose: it reflects player state, the player is
the source of truth. Buttons call ``player.toggle()`` / ``player.set_muted``
directly; the volume slider writes via ``player.set_volume``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from album_builder.services.player import Player, PlayerState
from album_builder.ui.theme import Glyphs


class TransportBar(QWidget):
    def __init__(self, player: Player, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self.setObjectName("TransportBar")

        self.btn_play = QPushButton(Glyphs.PLAY, objectName="TransportPlay")
        self.btn_play.setAccessibleName("Play")
        self.btn_play.setFixedWidth(48)
        self.btn_play.clicked.connect(self._on_play_clicked)

        self.lbl_current = QLabel("0:00", objectName="TransportTime")
        self.lbl_current.setAccessibleName("Current playback time")

        self.scrubber = QSlider(Qt.Orientation.Horizontal, objectName="TransportScrubber")
        self.scrubber.setRange(0, 0)
        self.scrubber.setAccessibleName("Playback position")
        self.scrubber.sliderMoved.connect(self._on_scrub)

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
        layout.addWidget(self.btn_play)
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

    # ---- Slots ------------------------------------------------------

    def _on_play_clicked(self) -> None:
        self._player.toggle()

    def _on_mute_clicked(self) -> None:
        self._player.set_muted(not self._player.muted())
        self._sync_mute_glyph()

    def _on_scrub(self, value: int) -> None:
        self._player.seek(float(value))

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
