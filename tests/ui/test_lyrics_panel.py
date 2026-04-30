"""LyricsPanel tests — Spec 07 §status pill + visual styling."""

from __future__ import annotations

from PyQt6.QtGui import QColor

from album_builder.domain.lyrics import LyricLine, Lyrics
from album_builder.services.alignment_status import AlignmentStatus
from album_builder.ui.lyrics_panel import LyricsPanel
from album_builder.ui.theme import Palette


def _lyrics(*texts: str) -> Lyrics:
    return Lyrics(
        lines=tuple(
            LyricLine(time_seconds=float(i), text=t) for i, t in enumerate(texts)
        )
    )


# Spec: TC-07-06
def test_status_label_initial_state(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    assert "no lyrics text" in panel.status_label.text().lower()


# Spec: TC-07-06
def test_status_label_each_state(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_status(AlignmentStatus.NOT_YET_ALIGNED)
    assert "not yet aligned" in panel.status_label.text().lower()
    panel.set_status(AlignmentStatus.READY)
    assert "ready" in panel.status_label.text().lower()
    panel.set_status(AlignmentStatus.ALIGNING, percent=42)
    assert "42%" in panel.status_label.text()


# Spec: TC-07-06
def test_align_now_button_visible_only_for_not_yet_aligned_or_failed(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_status(AlignmentStatus.NO_LYRICS_TEXT)
    assert panel.is_align_button_visible() is False
    panel.set_status(AlignmentStatus.NOT_YET_ALIGNED)
    assert panel.is_align_button_visible() is True
    panel.set_status(AlignmentStatus.ALIGNING, percent=50)
    assert panel.is_align_button_visible() is False
    panel.set_status(AlignmentStatus.READY)
    assert panel.is_align_button_visible() is False
    panel.set_status(AlignmentStatus.FAILED)
    assert panel.is_align_button_visible() is True
    panel.set_status(AlignmentStatus.AUDIO_TOO_SHORT)
    assert panel.is_align_button_visible() is False


def test_align_now_button_emits_request(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_status(AlignmentStatus.NOT_YET_ALIGNED)
    fired = []
    panel.align_now_requested.connect(lambda: fired.append(True))
    panel.align_button.click()
    assert fired == [True]


def test_set_lyrics_populates_list(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("a", "b", "c"))
    assert panel.list.count() == 3
    assert panel.list.item(0).text() == "a"
    assert panel.list.item(2).text() == "c"


def test_set_lyrics_none_clears_list(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("a", "b"))
    panel.set_lyrics(None)
    assert panel.list.count() == 0


def test_set_current_line_marks_now_only_one_row(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("a", "b", "c", "d"))
    panel.set_current_line(2)
    assert panel.line_state(0) == "past"
    assert panel.line_state(1) == "past"
    assert panel.line_state(2) == "now"
    assert panel.line_state(3) == "future"


def test_set_current_line_minus_one_all_future(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("a", "b", "c"))
    panel.set_current_line(-1)
    for i in range(3):
        assert panel.line_state(i) == "future"


# Spec: TC-07-15
def test_visual_styling_uses_palette_tokens(qtbot):
    palette = Palette.dark_colourful()
    panel = LyricsPanel(palette=palette)
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("a", "b", "c"))
    panel.set_current_line(1)

    past_color = panel.list.item(0).foreground().color()
    now_color = panel.list.item(1).foreground().color()
    future_color = panel.list.item(2).foreground().color()

    # Past = text_disabled
    assert past_color == QColor(palette.text_disabled)
    # Now = accent_warm + bold
    assert now_color == QColor(palette.accent_warm)
    assert panel.list.item(1).font().bold() is True
    # Future = text_tertiary
    assert future_color == QColor(palette.text_tertiary)


def test_set_current_line_no_op_when_unchanged(qtbot):
    """Re-setting the same index shouldn't blow up."""
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("a", "b"))
    panel.set_current_line(0)
    panel.set_current_line(0)
    assert panel.current_line() == 0
