"""Right pane - cover + metadata + lyrics panel + transport.

The lyrics panel was a placeholder ``QFrame#LyricsPlaceholder`` through
v0.3.0 (Phase 3A); v0.4.0 replaces it with the synchronised scrolling
``LyricsPanel`` widget owned by Spec 07.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from album_builder.domain.track import Track
from album_builder.services.player import Player
from album_builder.ui.lyrics_panel import LyricsPanel
from album_builder.ui.transport_bar import TransportBar


class NowPlayingPane(QFrame):
    def __init__(self, player: Player, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Now playing", objectName="PaneTitle"))

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

        # Spec 07 lyrics panel — replaces the v0.3.0 LyricsPlaceholder.
        # TC-07-16: lyrics panel absorbs the leftover vertical space below
        # the now-playing metadata (stretch=1) — no competing addStretch
        # after it, otherwise the slack would go to the spacer instead.
        self.lyrics_panel = LyricsPanel()
        layout.addWidget(self.lyrics_panel, stretch=1)

        self.transport = TransportBar(player)
        layout.addWidget(self.transport)

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
            # L7-M5: stale lyrics from the prior track must not persist
            # across track-cleared. Mirror the per-field clears above.
            self.lyrics_panel.set_lyrics(None)
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
