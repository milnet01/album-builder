"""Spec 11 TC-11-06 / TC-11-07: the library's coloured row strips.

A row carrying ACCENT_ROLE "primary" (a song in the current album) paints
a left strip in accent_primary_2; "warning" (in the album, file missing)
paints it in `warning`. Rows with no accent paint no strip. The strips
were promised by Spec 11 but never drawn: the QSS rules meant to draw
them cannot select a table item by a custom role (MUSI-0403)."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QTableView

from album_builder.ui.library_pane import ACCENT_ROLE, RowAccentDelegate
from album_builder.ui.theme import Palette


def _left_pixel(view: QTableView, row: int) -> QColor:
    img = view.viewport().grab().toImage()
    y = view.rowViewportPosition(row) + view.rowHeight(row) // 2
    return img.pixelColor(0, y)


def _close(a: QColor, b: QColor) -> bool:
    return all(abs(x - y) <= 12 for x, y in zip(a.getRgb()[:3], b.getRgb()[:3], strict=True))


# Spec: TC-11-06, TC-11-07
def test_accent_rows_paint_their_strip(qtbot) -> None:
    pal = Palette.dark_colourful()
    model = QStandardItemModel(3, 2)
    for row, accent in enumerate(["primary", "warning", None]):
        for col in range(2):
            item = QStandardItem(f"r{row}c{col}")
            item.setData(accent, ACCENT_ROLE)
            model.setItem(row, col, item)
    view = QTableView()
    view.setModel(model)
    view.verticalHeader().hide()
    view.setItemDelegate(RowAccentDelegate(view, palette=pal))
    view.resize(300, 150)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)

    assert _close(_left_pixel(view, 0), QColor(pal.accent_primary_2))
    assert _close(_left_pixel(view, 1), QColor(pal.warning))
    plain = _left_pixel(view, 2)
    assert not _close(plain, QColor(pal.accent_primary_2))
    assert not _close(plain, QColor(pal.warning))


# Spec: TC-11-06 - every column of an in-album row reports the accent (the
# play column used to report none, so the strip at the row's left edge was
# never drawn); the Used column stays out (Spec 13).
def test_model_reports_accent_on_every_column_but_used(qapp, tracks_dir) -> None:
    from album_builder.domain.album import Album
    from album_builder.domain.library import Library
    from album_builder.ui.library_pane import COLUMNS, LibraryPane

    lib = Library.scan(tracks_dir)
    pane = LibraryPane()
    pane.set_library(lib)
    album = Album.create(name="A", target_count=3)
    album.track_paths = [lib.tracks[0].path]
    pane.set_current_album(album)
    model = pane._model
    row = next(r for r in range(model.rowCount()) if model._tracks[r].path == lib.tracks[0].path)
    for col, spec in enumerate(COLUMNS):
        expected = None if spec[1] == "_used" else "primary"
        assert model.data(model.index(row, col), ACCENT_ROLE) == expected, spec[1]
