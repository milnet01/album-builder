"""The pick column is visible without a sideways scroll (Spec 04 TC-04-26, MUSI-0392)."""

from __future__ import annotations

from album_builder.ui.library_pane import COLUMNS, LibraryPane, _column_index


# Spec: TC-04-26 - the pick column sits second, right after the play column.
def test_pick_column_is_second() -> None:
    assert [c[1] for c in COLUMNS[:2]] == ["_play", "_toggle"]


# Spec: TC-04-26 - at the table's narrowest width the pick column is on screen.
def test_pick_column_on_screen_at_minimum_width(qtbot) -> None:
    pane = LibraryPane()
    qtbot.addWidget(pane)
    pane.resize(pane.table.minimumWidth(), 400)
    pane.show()
    qtbot.waitExposed(pane)
    header = pane.table.horizontalHeader()
    col = _column_index("_toggle")
    left = header.sectionViewportPosition(col)
    right = left + header.sectionSize(col)
    assert 0 <= left
    assert right <= pane.table.viewport().width(), (
        f"pick column ends at {right} px, viewport is {pane.table.viewport().width()} px"
    )
