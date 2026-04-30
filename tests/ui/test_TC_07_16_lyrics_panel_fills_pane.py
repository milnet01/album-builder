"""Spec 07 TC-07-16 - lyrics panel fills the available right-pane height.

The v0.4.0 implementation pinned the lyrics panel to setFixedHeight(150),
and NowPlayingPane finished its layout with addStretch(1) after the panel
- together those two stranded the lyrics in ~150 px regardless of how
tall the right pane was. v0.5.2 lifts the fixed-height to a min-height
and drops the competing stretch so the panel grows with the window.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QApplication

from album_builder.domain.track import Track
from album_builder.services.player import Player
from album_builder.ui.lyrics_panel import LyricsPanel
from album_builder.ui.now_playing_pane import NowPlayingPane


def _make_track(tmp: Path) -> Track:
    return Track(
        path=tmp / "song.mpeg",
        title="Walking The Line",
        artist="18 Down",
        album_artist="18 Down",
        album="Memoirs of a Sinner",
        composer="A. Smith",
        comment="rough mix",
        lyrics_text=None,
        cover_data=None,
        cover_mime=None,
        duration_seconds=240.0,
        is_missing=False,
        file_size_bytes=1234,
    )


# Spec: TC-07-16(a) — LyricsPanel uses setMinimumHeight(150), not setFixedHeight.
def test_lyrics_panel_uses_min_height_not_fixed(qtbot) -> None:
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    # Fixed height pins both min and max to the same value. Min-height
    # only pins the floor; max stays at Qt's default sentinel.
    assert panel.minimumHeight() == 150, (
        "TC-07-16(a): minimum height is 150 px (the v0.4.0 fixed-height value)"
    )
    assert panel.maximumHeight() > 150, (
        "TC-07-16(a): maximum height must NOT be pinned at 150; the panel "
        "needs to grow with the right pane"
    )


# Spec: TC-07-16(b) — NowPlayingPane gives the lyrics panel non-zero stretch
# and does not add a competing addStretch after it.
def test_now_playing_pane_gives_lyrics_non_zero_stretch(qtbot, tmp_path: Path) -> None:
    p = Player()
    pane = NowPlayingPane(p)
    qtbot.addWidget(pane)
    layout = pane.layout()
    # Find the index of the lyrics panel in the QVBoxLayout.
    lyrics_index = -1
    for i in range(layout.count()):
        if layout.itemAt(i).widget() is pane.lyrics_panel:
            lyrics_index = i
            break
    assert lyrics_index >= 0, "lyrics_panel must be a direct child of pane's layout"
    assert layout.stretch(lyrics_index) > 0, (
        "TC-07-16(b): the lyrics panel must be added with non-zero stretch "
        "so it absorbs leftover vertical space"
    )
    # No item AFTER the lyrics panel may be a non-zero-stretch QSpacerItem
    # competing for the same vertical slack. Most direct check: nothing
    # below the lyrics panel except the transport bar (a real widget,
    # which is allowed to keep its preferred size).
    for i in range(lyrics_index + 1, layout.count()):
        item = layout.itemAt(i)
        if item.widget() is None and item.spacerItem() is not None:
            assert layout.stretch(i) == 0, (
                "TC-07-16(b): no addStretch() after the lyrics panel — "
                "it would steal the vertical slack the panel needs"
            )


# Spec: TC-07-16(c) — at 420x800, the lyrics panel grows past 300 px.
def test_lyrics_panel_grows_when_pane_is_tall(qtbot, tmp_path: Path) -> None:
    p = Player()
    pane = NowPlayingPane(p)
    qtbot.addWidget(pane)
    pane.resize(420, 800)
    QApplication.processEvents()
    h = pane.lyrics_panel.height()
    assert h >= 300, (
        f"TC-07-16(c): at a 420x800 right pane the lyrics panel must grow "
        f"to at least 2x its 150 px minimum (>=300 px); got {h} px"
    )
