"""Cover + metadata block - extracted from NowPlayingPane for reuse (Spec 18).

The curation ``NowPlayingPane`` and the Player-tab ``PlayerPane`` both render the
same cover + title/album/artist/composer/comment block; this widget is the single
implementation. It owns **no** lyrics panel - the L7-M5 clear-stale-lyrics-on-None
behavior stays with whichever pane owns the ``LyricsPanel`` (see now_playing_pane.py
and player_pane.py).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from album_builder.domain.track import Track


class NowPlayingCard(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NowPlayingCard")
        # Spec 18: an id-scoped transparent background so the card inherits its
        # host container's backdrop (bg_pane) without (a) reusing
        # objectName="Pane" - which would double the #Pane border where the card
        # nests inside a Pane - or (b) falling through to the generic
        # `QWidget { background-color: bg_base }` rule. Id-scoped so it cannot
        # cascade onto the child cover/metadata labels, which keep their own
        # objectName rules (notably QLabel#NowPlayingCover's bg_pane fill).
        self.setStyleSheet("QFrame#NowPlayingCard { background: transparent; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.cover_label = QLabel(objectName="NowPlayingCover")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedHeight(280)
        self.cover_label.setMinimumWidth(280)
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("", objectName="NowPlayingTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.album_label = QLabel("", objectName="NowPlayingMeta")
        self.album_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.album_label)

        self.artist_label = QLabel("", objectName="NowPlayingMeta")
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.artist_label)

        self.composer_label = QLabel("", objectName="NowPlayingMetaSecondary")
        self.composer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.composer_label)

        self.comment_label = QLabel("", objectName="NowPlayingMetaSecondary")
        self.comment_label.setWordWrap(True)
        self.comment_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.comment_label)

        self.placeholder_label = QLabel("(nothing loaded)", objectName="PlaceholderText")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.placeholder_label)

        self.set_track(None)

    def set_track(self, track: Track | None) -> None:
        if track is None:
            self.cover_label.clear()
            self.cover_label.setText("")
            self.title_label.setText("")
            self.album_label.setText("")
            self.artist_label.setText("")
            self.composer_label.setText("")
            self.comment_label.setText("")
            self.placeholder_label.setVisible(True)
            return
        self.placeholder_label.setVisible(False)
        self._set_cover(track)
        self.title_label.setText(track.title or "")
        self.album_label.setText(track.album or "")
        self.artist_label.setText(track.artist or "")
        if track.composer:
            self.composer_label.setText(f"composer: {track.composer}")
        else:
            self.composer_label.setText("")
        if track.comment:
            self.comment_label.setText(track.comment)
        else:
            self.comment_label.setText("")

    def _set_cover(self, track: Track) -> None:
        if not track.cover_data:
            self.cover_label.clear()
            self.cover_label.setText("(no cover)")
            return
        pix = QPixmap()
        pix.loadFromData(track.cover_data)
        if pix.isNull():
            self.cover_label.clear()
            self.cover_label.setText("(cover unavailable)")
            return
        scaled = pix.scaledToHeight(
            260, Qt.TransformationMode.SmoothTransformation,
        )
        self.cover_label.setPixmap(scaled)
