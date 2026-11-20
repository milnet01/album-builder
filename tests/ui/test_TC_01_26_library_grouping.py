"""Library side-list grouping by artist or album - Spec 01 TC-01-26/27/28."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.library import Library
from album_builder.ui.library_pane import LibraryPane


@pytest.fixture
def grouped_dir(tmp_path: Path, tagged_track) -> Path:
    tagged_track("01-a.mp3", title="alpha", artist="18 Down", album="Memoirs")
    tagged_track("02-b.mp3", title="bravo", artist="18 down", album="Memoirs")
    tagged_track("03-c.mp3", title="charlie", artist="Other Artist", album="b-sides")
    tagged_track("04-d.mp3", title="delta", artist="Other Artist", album="")
    return tmp_path


@pytest.fixture
def pane(qtbot, grouped_dir: Path) -> LibraryPane:
    p = LibraryPane()
    p.set_library(Library.scan(grouped_dir))
    qtbot.addWidget(p)
    p.show()
    return p


def _set_mode(pane: LibraryPane, mode: str) -> None:
    pane.group_box.setCurrentIndex(pane.group_box.findData(mode))


def _entries(pane: LibraryPane) -> list[str]:
    lst = pane.group_list
    return [lst.item(i).text() for i in range(lst.count())]


def _pick(pane: LibraryPane, text: str) -> None:
    lst = pane.group_list
    row = next(i for i in range(lst.count()) if lst.item(i).text() == text)
    lst.setCurrentRow(row)


def _titles(pane: LibraryPane) -> list[str]:
    return sorted(pane.title_at(r) for r in range(pane.row_count()))


# Spec: TC-01-26
def test_grouping_starts_off_with_side_list_hidden(pane) -> None:
    assert pane.group_box.currentData() == "none"
    assert not pane.group_list.isVisible()


# Spec: TC-01-26
def test_by_artist_lists_each_artist_once_after_all_songs(pane) -> None:
    _set_mode(pane, "artist")
    assert pane.group_list.isVisible()
    entries = _entries(pane)
    assert entries[0].startswith("All songs")
    assert pane.group_list.currentRow() == 0
    assert len(entries) == 3  # "18 Down" and "18 down" share one entry
    assert entries[1].casefold() == "18 down"
    assert entries[2] == "Other Artist"


# Spec: TC-01-26
def test_by_album_names_empty_album_unknown(pane) -> None:
    _set_mode(pane, "album")
    assert _entries(pane)[1:] == ["b-sides", "Memoirs", "Unknown album"]


# Spec: TC-01-27
def test_picking_an_entry_filters_and_search_narrows_within(pane) -> None:
    _set_mode(pane, "artist")
    _pick(pane, "Other Artist")
    assert _titles(pane) == ["charlie", "delta"]
    pane.search_box.setText("del")
    assert _titles(pane) == ["delta"]
    pane.group_list.setCurrentRow(0)  # All songs
    assert _titles(pane) == ["delta"]  # the search still applies
    pane.search_box.setText("")
    assert _titles(pane) == ["alpha", "bravo", "charlie", "delta"]


# Spec: TC-01-27
def test_unknown_album_entry_and_no_grouping_restore_all(pane) -> None:
    _set_mode(pane, "album")
    _pick(pane, "Unknown album")
    assert _titles(pane) == ["delta"]
    _set_mode(pane, "none")
    assert not pane.group_list.isVisible()
    assert pane.row_count() == 4


# Spec: TC-01-28
def test_library_change_keeps_pick_while_it_exists(pane, grouped_dir, tagged_track) -> None:
    _set_mode(pane, "artist")
    _pick(pane, "Other Artist")
    tagged_track("05-e.mp3", title="echo", artist="New Artist", album="Memoirs")
    pane.set_library(Library.scan(grouped_dir))
    assert "New Artist" in _entries(pane)
    assert pane.group_list.currentItem().text() == "Other Artist"
    assert _titles(pane) == ["charlie", "delta"]


# Spec: TC-01-28
def test_library_change_drops_vanished_pick_to_all_songs(pane, grouped_dir) -> None:
    _set_mode(pane, "artist")
    _pick(pane, "Other Artist")
    (grouped_dir / "03-c.mp3").unlink()
    (grouped_dir / "04-d.mp3").unlink()
    pane.set_library(Library.scan(grouped_dir))
    assert pane.group_list.currentRow() == 0
    assert "Other Artist" not in _entries(pane)
    assert _titles(pane) == ["alpha", "bravo"]
