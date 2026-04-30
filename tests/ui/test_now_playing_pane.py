"""Tests for album_builder.ui.now_playing_pane - Spec 06 right pane."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.track import Track
from album_builder.services.player import Player
from album_builder.ui.now_playing_pane import NowPlayingPane


def _make_track(tmp: Path, **over) -> Track:
    base = dict(
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
    base.update(over)
    return Track(**base)


@pytest.fixture
def pane(qtbot):
    p = Player()
    pane = NowPlayingPane(p)
    qtbot.addWidget(pane)
    pane.show()
    return pane, p


def test_no_track_shows_placeholder(pane) -> None:
    p, _ = pane
    assert p.title_label.text() == ""
    assert p.placeholder_label.isVisible()


def test_set_track_shows_metadata(pane, tmp_path: Path) -> None:
    p, _ = pane
    p.set_track(_make_track(tmp_path))
    assert p.title_label.text() == "Walking The Line"
    assert p.artist_label.text() == "18 Down"
    assert p.album_label.text() == "Memoirs of a Sinner"
    assert "A. Smith" in p.composer_label.text()
    assert p.comment_label.text() == "rough mix"
    assert not p.placeholder_label.isVisible()


def test_set_track_none_clears(pane, tmp_path: Path) -> None:
    p, _ = pane
    p.set_track(_make_track(tmp_path))
    p.set_track(None)
    assert p.title_label.text() == ""
    assert p.album_label.text() == ""
    assert p.placeholder_label.isVisible()


def test_set_track_with_no_composer_clears_label(pane, tmp_path: Path) -> None:
    p, _ = pane
    p.set_track(_make_track(tmp_path, composer=""))
    assert p.composer_label.text() == ""


def test_set_track_with_no_comment_clears_label(pane, tmp_path: Path) -> None:
    p, _ = pane
    p.set_track(_make_track(tmp_path, comment=""))
    assert p.comment_label.text() == ""


def test_set_track_with_no_cover_shows_placeholder_text(pane, tmp_path: Path) -> None:
    p, _ = pane
    p.set_track(_make_track(tmp_path, cover_data=None))
    assert p.cover_label.text() == "(no cover)"


def test_lyrics_panel_present(pane) -> None:
    """v0.4.0: the v0.3.0 LyricsPlaceholder QFrame is replaced by the
    Spec 07 LyricsPanel widget. Pin the contract so MainWindow can rely
    on the attribute when wiring tracker + alignment service."""
    p, _ = pane
    assert p.lyrics_panel is not None
    assert p.lyrics_panel.objectName() == "LyricsPanel"


def test_transport_bar_present(pane) -> None:
    p, _ = pane
    assert p.transport is not None


def test_invalid_cover_data_shows_unavailable_text(pane, tmp_path: Path) -> None:
    """Bytes that don't decode as a known image format must not crash."""
    p, _ = pane
    p.set_track(_make_track(tmp_path, cover_data=b"\x00\x01not-an-image"))
    assert p.cover_label.text() == "(cover unavailable)"
