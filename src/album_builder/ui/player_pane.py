"""Player-tab listening surface - Spec 18 (Phase E).

Composes existing widgets into a dedicated now-playing layout: cover + metadata
(``NowPlayingCard``) + full ``TransportBar`` on the left, synced ``LyricsPanel``
over an Up Next / Playlists tab group on the right. It owns no playback state and
adds no queue/playlist logic - it is driven by the same ``Player`` +
``PlaybackController`` as the curation ``NowPlayingPane``, so the two surfaces stay
coherent via the Spec 18 broadcast signals. ``MainWindow`` constructs and wires the
``queue_pane`` / ``playlists_pane`` and hands them in; this pane only reparents them
into its tab group (their signals are unaffected by reparenting).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QSplitter, QTabWidget, QVBoxLayout, QWidget

from album_builder.domain.track import Track
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player
from album_builder.ui.lyrics_panel import LyricsPanel
from album_builder.ui.now_playing_card import NowPlayingCard
from album_builder.ui.playlists_pane import PlaylistsPane
from album_builder.ui.queue_pane import QueuePane
from album_builder.ui.transport_bar import TransportBar


class PlayerPane(QWidget):
    def __init__(
        self,
        player: Player,
        controller: PlaybackController,
        queue_pane: QueuePane,
        playlists_pane: PlaylistsPane,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.card = NowPlayingCard()
        self.lyrics_panel = LyricsPanel()
        self.transport = TransportBar(player, controller)

        # Left column: a QFrame#Pane. The QFrame#Pane rule is a *type#id*
        # selector, so a plain QWidget with objectName="Pane" would NOT match
        # and would fall through to bg_base, leaving the transparent card on the
        # wrong background. Card at top, stretch, transport pinned at the bottom.
        left = QFrame(objectName="Pane")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.card)
        left_layout.addStretch(1)
        left_layout.addWidget(self.transport)

        # Right column: lyrics (the tall element) over an Up Next / Playlists
        # tab group. The queue_pane / playlists_pane are reparented in here.
        tabs = QTabWidget()
        tabs.addTab(queue_pane, "Up Next")
        tabs.addTab(playlists_pane, "Playlists")

        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)
        right.addWidget(self.lyrics_panel)
        right.addWidget(tabs)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(right)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

    def set_track(self, track: Track | None) -> None:
        self.card.set_track(track)
        if track is None:
            # Symmetric with NowPlayingPane.set_track(None): this surface clears
            # its own lyrics panel, so MainWindow's None-branch needs no separate
            # lyrics-clear call (Spec 18 §Concepts - now-playing surface).
            self.lyrics_panel.set_lyrics(None)
