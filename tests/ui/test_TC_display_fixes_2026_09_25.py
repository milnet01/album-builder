"""Display defects seen in a demo screenshot (MUSI-0364, MUSI-0365, MUSI-0366).

All three were present before 2026-09-25 and visible at an ordinary window
size: the library's Title column collapsed to nothing, album-order rows drew
their text twice, and the row play button was blank.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionButton, QStyleOptionViewItem

from album_builder.domain.album import Album
from album_builder.domain.library import Library
from album_builder.domain.track import Track
from album_builder.ui.album_order_pane import AlbumOrderPane
from album_builder.ui.library_pane import COLUMNS, LibraryPane
from album_builder.ui.target_counter import TargetCounter
from album_builder.ui.theme import palette_for, qt_stylesheet
from album_builder.ui.toast import Toast


def _track(stem: str) -> Track:
    return Track(
        path=Path(f"/abs/{stem}.mp3"), title=stem, artist="x", album_artist="x",
        album="", composer="", comment="", lyrics_text=None, cover_data=None,
        cover_mime=None, duration_seconds=10.0, file_size_bytes=0, is_missing=False,
    )


@pytest.fixture
def order_pane(qtbot) -> AlbumOrderPane:
    pane = AlbumOrderPane()
    qtbot.addWidget(pane)
    pane.setStyleSheet(qt_stylesheet(palette_for("dark-colourful")))
    album = Album.create(name="x", target_count=5)
    album.track_paths = [Path(f"/abs/{c}.mp3") for c in "abc"]
    pane.set_album(album, [_track(c) for c in "abc"])
    pane.resize(300, 300)
    pane.show()
    qtbot.waitExposed(pane)
    QApplication.processEvents()
    return pane


# Spec: TC-01-20
def test_title_column_stays_visible_in_a_narrow_library(qtbot) -> None:
    pane = LibraryPane()
    qtbot.addWidget(pane)
    pane.set_library(Library(folder=Path("/abs"), tracks=(_track("a"),)))
    pane.resize(500, 400)
    pane.show()
    qtbot.waitExposed(pane)
    title_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "title")

    assert pane.table.horizontalHeader().sectionSize(title_col) >= 150


# Spec: TC-05-16
def test_order_row_text_is_not_painted_under_the_row_widget(
    order_pane: AlbumOrderPane,
) -> None:
    item_list = order_pane.list
    option = QStyleOptionViewItem()
    item_list.itemDelegate().initStyleOption(option, item_list.model().index(0, 0))

    assert option.text == ""
    assert item_list.item(0).text().endswith("a")  # still there for screen readers


def _glyph_buttons(qtbot, order_pane: AlbumOrderPane):
    counter = TargetCounter()
    toast = Toast()
    for widget in (counter, toast):
        qtbot.addWidget(widget)
        widget.setStyleSheet(qt_stylesheet(palette_for("dark-colourful")))
        widget.show()
    QApplication.processEvents()
    return {
        "_owners": (counter, toast),  # keep the parents alive for the test
        "row play": order_pane.play_button_at(0),
        "track count down": counter.btn_down,
        "track count up": counter.btn_up,
        "notification close": toast.btn_close,
    }


# Spec: TC-06-27
@pytest.mark.parametrize(
    "name", ["row play", "track count down", "track count up", "notification close"],
)
def test_fixed_width_glyph_buttons_have_room_for_their_glyph(
    qtbot, order_pane: AlbumOrderPane, name: str,
) -> None:
    buttons = _glyph_buttons(qtbot, order_pane)
    button = buttons[name]
    option = QStyleOptionButton()
    option.initFrom(button)
    contents = button.style().subElementRect(
        QStyle.SubElement.SE_PushButtonContents, option, button,
    )

    assert contents.width() >= button.fontMetrics().horizontalAdvance(button.text())
