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


# Indie-review L7-H1: _restyle_items must base its font off the list
# widget's font (which inherits Spec 11 typography from QSS) rather than
# constructing a default QFont() that drops the family/size and falls
# back to whatever Qt's bare-default font happens to be on the platform.
def test_restyle_inherits_list_font_family(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    # Pin a recognisable list font that the styling pass should preserve.
    from PyQt6.QtGui import QFont
    list_font = QFont("Inter", 14)
    panel.list.setFont(list_font)
    panel.set_lyrics(_lyrics("a", "b", "c"))
    panel.set_current_line(1)
    for i in range(3):
        item_font = panel.list.item(i).font()
        assert item_font.family() == "Inter", (
            f"row {i} font family lost: {item_font.family()!r}"
        )
        assert item_font.pointSize() == 14, (
            f"row {i} point size lost: {item_font.pointSize()}"
        )
    # And the bold property is still toggled correctly on the active row.
    assert panel.list.item(1).font().bold() is True
    assert panel.list.item(0).font().bold() is False


# Indie-review L7-H4: _restyle_items must update only the affected items
# on a line crossing (old current, new current, optional adjacent), not
# walk every line in the list. Spec 07 perf budget claims O(1) tick.
def test_restyle_updates_only_three_items_per_crossing(qtbot, monkeypatch):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics(*[chr(c) for c in range(ord("a"), ord("a") + 20)]))
    panel.set_current_line(5)

    # Count setForeground calls on a fresh crossing.
    touched: list[int] = []
    real_item = panel.list.item

    def tracking_item(i):
        item = real_item(i)
        real_set_fg = item.setForeground

        def track(brush):
            touched.append(i)
            return real_set_fg(brush)

        item.setForeground = track  # type: ignore[assignment]
        return item

    monkeypatch.setattr(panel.list, "item", tracking_item)
    panel.set_current_line(6)
    # Old current (5) + new current (6) at minimum; bounded by a small
    # constant — assert <= 4 to allow for adjacent-row repaints (e.g.
    # past->past upstream).
    assert len(set(touched)) <= 4, (
        f"O(1) crossing should touch <= 4 rows; touched {sorted(set(touched))}"
    )


# Indie-review L7-M1: a panel constructed without an explicit palette
# silently uses Palette.dark_colourful(); a future v2 theme switch would
# leave LyricsPanel out of date. Document via assertion that the panel's
# bound palette is reachable for inspection (so external code can verify
# at construction).
def test_lyrics_panel_exposes_bound_palette(qtbot):
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    p = panel.palette_for_lyrics()  # public accessor required by L7-M1
    from album_builder.ui.theme import Palette
    assert isinstance(p, Palette)


def test_set_current_line_no_op_when_unchanged(qtbot):
    """Re-setting the same index shouldn't blow up."""
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("a", "b"))
    panel.set_current_line(0)
    panel.set_current_line(0)
    assert panel.current_line() == 0
