"""Right pane - "Now playing" title + cover/metadata card + lyrics + transport.

The cover + metadata block is the shared ``NowPlayingCard`` (Spec 18); this pane
composes it with the Spec 07 ``LyricsPanel`` and the Spec 16 ``TransportBar``.
The pane owns the lyrics panel, so it keeps the L7-M5 clear-stale-lyrics-on-None
behavior (the card owns no lyrics). Its public surface - ``set_track``,
``lyrics_panel``, ``transport`` - is unchanged; the cover/metadata labels are now
reached through ``.card`` (e.g. ``pane.card.title_label``).
"""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from album_builder.domain.track import Track
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player
from album_builder.ui.lyrics_panel import LyricsPanel
from album_builder.ui.now_playing_card import NowPlayingCard
from album_builder.ui.transport_bar import TransportBar


class NowPlayingPane(QFrame):
    def __init__(
        self, player: Player, controller: PlaybackController, parent=None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Now playing", objectName="PaneTitle"))

        # Spec 18: the cover + metadata block is the shared NowPlayingCard; it
        # is transparent so it renders on this Pane's bg_pane backdrop.
        self.card = NowPlayingCard()
        layout.addWidget(self.card)

        # Spec 07 lyrics panel — replaces the v0.3.0 LyricsPlaceholder.
        # TC-07-16: lyrics panel absorbs the leftover vertical space below
        # the now-playing card (stretch=1) — no competing addStretch after
        # it, otherwise the slack would go to the spacer instead.
        self.lyrics_panel = LyricsPanel()
        layout.addWidget(self.lyrics_panel, stretch=1)

        self.transport = TransportBar(player, controller)
        layout.addWidget(self.transport)

        self.set_track(None)

    def set_track(self, track: Track | None) -> None:
        self.card.set_track(track)
        if track is None:
            # L7-M5: a track-clear also blanks stale lyrics on this pane (the
            # card owns no lyrics panel, so this pane clears its own).
            self.lyrics_panel.set_lyrics(None)
