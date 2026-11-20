"""The mini player - Spec 30 §4.2.

A small top-level window that drives the same Player, PlaybackController and
PlayHistory as the full window; there is no second pipeline. MainWindow owns
when it shows, where it goes and what closing it does.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from album_builder.domain.track import Track
from album_builder.i18n import tr
from album_builder.persistence.state_io import MINI_MIN_WIDTH
from album_builder.services.play_history import PlayHistory
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player, PlayerState
from album_builder.services.window_placement import CAPTION_PREFIX
from album_builder.ui.theme import Glyphs

COVER_PX = 64


def mini_title() -> str:
    """The window title. KWin finds the window by its fixed ASCII prefix."""
    return CAPTION_PREFIX + tr("mini player")


def _button(glyph: str, name: str, width: int = 36) -> QPushButton:
    button = QPushButton(glyph)
    button.setAccessibleName(name)
    button.setToolTip(name)
    button.setFixedWidth(width)
    return button


class MiniPlayer(QWidget):
    expand_requested = pyqtSignal()
    close_requested = pyqtSignal()
    on_top_toggled = pyqtSignal(bool)

    def __init__(
        self,
        player: Player,
        controller: PlaybackController,
        history: PlayHistory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("MiniPlayer")
        self.setWindowTitle(mini_title())
        self._player = player
        self._controller = controller
        self._history = history
        self._track: Track | None = None

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(COVER_PX, COVER_PX)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel(objectName="MiniTitle")
        self.artist_label = QLabel(objectName="MiniArtist")
        for label in (self.title_label, self.artist_label):
            # Ignored, so a long title never widens the window past its size.
            label.setSizePolicy(label.sizePolicy().Policy.Ignored,
                                label.sizePolicy().Policy.Preferred)

        self.progress = QSlider(Qt.Orientation.Horizontal, objectName="MiniProgress")
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName(tr("Playback position"))
        # Seek on release, as TransportBar does: one seek per drag.
        self.progress.sliderReleased.connect(
            lambda: self._player.seek(float(self.progress.value()))
        )

        self.btn_prev = _button(Glyphs.SKIP_PREV, tr("Previous"))
        self.btn_prev.clicked.connect(lambda: self._controller.previous())
        self.btn_play = _button(Glyphs.PLAY, tr("Play"), 44)
        self.btn_play.clicked.connect(lambda: self._controller.toggle())
        self.btn_next = _button(Glyphs.SKIP_NEXT, tr("Next"))
        self.btn_next.clicked.connect(lambda: self._controller.next())

        self.volume = QSlider(Qt.Orientation.Horizontal, objectName="MiniVolume")
        self.volume.setRange(0, 100)
        self.volume.setValue(player.volume())
        self.volume.setFixedWidth(70)
        self.volume.setAccessibleName(tr("Volume"))
        self.volume.valueChanged.connect(lambda v: self._player.set_volume(v))

        self.heart = _button(Glyphs.HEART_OUTLINE, tr("Favourite"))
        self.heart.setCheckable(True)
        self.heart.toggled.connect(self._on_heart_toggled)

        self.pin = _button(Glyphs.PIN, tr("Keep on top"))
        self.pin.setCheckable(True)
        self.pin.setChecked(True)
        self.pin.toggled.connect(self.on_top_toggled)

        self.btn_full = _button(Glyphs.FULL_WINDOW, tr("Full window"))
        self.btn_full.clicked.connect(self.expand_requested)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title_label)
        text.addWidget(self.artist_label)
        text.addWidget(self.progress)

        # Spec 25: the playback buttons and the progress bar stay left to
        # right under a right-to-left language.
        self.controls = QWidget()
        self.controls.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        buttons = QHBoxLayout(self.controls)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(4)
        for widget in (self.btn_prev, self.btn_play, self.btn_next):
            buttons.addWidget(widget)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(8)
        row.addWidget(self.cover_label)
        row.addLayout(text, stretch=1)
        row.addWidget(self.controls)
        for widget in (self.volume, self.heart, self.pin, self.btn_full):
            row.addWidget(widget)
        self.progress.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # Width resizes; height is the layout's (Spec 30 §3).
        self.setMinimumWidth(MINI_MIN_WIDTH)
        self.setFixedHeight(self.sizeHint().height())

        player.position_changed.connect(self._on_position)
        player.duration_changed.connect(lambda s: self.progress.setRange(0, int(s)))
        player.state_changed.connect(self._on_state)
        player.volume_changed.connect(self._on_volume_changed)
        controller.current_changed.connect(self.set_track)
        history.changed.connect(self._sync_heart)
        self.set_track(None)

    # ---- MainWindow's controls ---------------------------------------

    def set_on_top_supported(self, supported: bool) -> None:
        self.pin.setVisible(supported)

    def set_on_top(self, on: bool) -> None:
        self.pin.blockSignals(True)
        self.pin.setChecked(on)
        self.pin.blockSignals(False)

    def closeEvent(self, e) -> None:
        # MainWindow decides: closing the mini player quits the app (§3).
        e.ignore()
        self.close_requested.emit()

    # ---- Following the shared pipeline -------------------------------

    def set_track(self, track: Track | None) -> None:
        self._track = track
        self.title_label.setText((track.title or "") if track else "")
        self.artist_label.setText((track.artist or "") if track else "")
        self.cover_label.clear()
        if track is not None and track.cover_data:
            pix = QPixmap()
            pix.loadFromData(track.cover_data)
            if not pix.isNull():
                # As NowPlayingCard._set_cover scales, at this window's size.
                self.cover_label.setPixmap(pix.scaledToHeight(
                    COVER_PX, Qt.TransformationMode.SmoothTransformation,
                ))
        self._sync_heart()

    def _sync_heart(self) -> None:
        track = self._track
        on = track is not None and self._history.stats_for(track).favourited is not None
        self.heart.blockSignals(True)
        self.heart.setChecked(on)
        self.heart.blockSignals(False)
        self.heart.setEnabled(track is not None and self._history.has_key(track))
        self.heart.setText(Glyphs.HEART if on else Glyphs.HEART_OUTLINE)
        self.heart.setToolTip(tr("Remove from favourites") if on else tr("Add to favourites"))

    def _on_heart_toggled(self, on: bool) -> None:
        if self._track is not None:
            self._history.set_favourite(self._track, on)

    def _on_position(self, seconds: float) -> None:
        if not self.progress.isSliderDown():
            self.progress.setValue(int(seconds))

    def _on_state(self, state) -> None:
        playing = state == PlayerState.PLAYING
        self.btn_play.setText(Glyphs.PAUSE if playing else Glyphs.PLAY)
        self.btn_play.setAccessibleName(tr("Pause") if playing else tr("Play"))

    def _on_volume_changed(self, v: int) -> None:
        if not self.volume.isSliderDown():
            self.volume.setValue(v)
