"""QueuePane (Up Next list) - Spec 15 (Phase B), TC-15-25 / 26 / 32."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.track import Track
from album_builder.ui.queue_pane import QueuePane


def _track(name: str, *, title: str | None = None, artist: str = "A") -> Track:
    return Track(
        path=Path(f"/tracks/{name}.mp3"),
        title=title if title is not None else name,
        artist=artist,
        album_artist=artist,
        composer="",
        album="",
        comment="",
        lyrics_text=None,
        cover_data=None,
        cover_mime=None,
        duration_seconds=1.0,
        file_size_bytes=1,
        is_missing=False,
    )


@pytest.fixture
def pane(qtbot):
    p = QueuePane()
    qtbot.addWidget(p)
    return p


# Spec: TC-15-25
def test_set_queue_lists_rows_in_order(pane) -> None:
    pane.set_queue((_track("a"), _track("b"), _track("c")))
    assert pane.list.count() == 3
    assert pane.list.item(0).text().startswith("a")
    assert pane.list.item(1).text().startswith("b")
    assert pane.list.item(2).text().startswith("c")


# Spec: TC-15-25
def test_set_queue_empty_shows_placeholder(pane) -> None:
    pane.set_queue((_track("a"),))      # populate first
    pane.set_queue(())                  # then clear
    assert pane.list.count() == 1
    item = pane.list.item(0)
    assert item.text() == "Nothing queued"
    # Placeholder is non-interactive: it can be neither selected nor activated.
    assert item.flags() == Qt.ItemFlag.NoItemFlags


# Spec: TC-15-26
def test_set_current_highlights_and_clears(pane) -> None:
    pane.set_queue((_track("a"), _track("b"), _track("c")))
    pane.set_current(1)
    assert pane.list.currentRow() == 1
    pane.set_current(-1)
    assert pane.list.currentRow() == -1


# Spec: TC-15-26
def test_set_current_highlights_one_copy_of_duplicate(pane) -> None:
    dup = _track("dup")
    pane.set_queue((dup, _track("b"), dup))
    pane.set_current(2)
    assert pane.list.currentRow() == 2
    assert pane.list.item(2).isSelected()
    assert not pane.list.item(0).isSelected()


# Spec: TC-15-32
def test_markup_title_rendered_as_plain_text(pane) -> None:
    pane.set_queue((_track("x", title="<b>x</b>"),))
    # Qt does not interpret markup in a plain list item - the literal shows.
    assert pane.list.item(0).text() == "<b>x</b> - A"


# Spec: TC-15 §UI surface (row activation - the double-click / Enter analogue)
def test_row_activated_emits_play_order_position(pane, qtbot) -> None:
    pane.set_queue((_track("a"), _track("b")))
    with qtbot.waitSignal(pane.row_activated) as blocker:
        pane.list.itemActivated.emit(pane.list.item(1))
    assert blocker.args == [1]


# Spec: TC-15 §UI surface (accessibility)
def test_list_has_accessible_name(pane) -> None:
    assert pane.list.accessibleName() == "Playback queue"
