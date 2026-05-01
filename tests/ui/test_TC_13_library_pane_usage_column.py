"""Library-pane Used-column tests (Spec 13 TC-13-09..32 across model/pane)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy

from album_builder.domain.album import AlbumStatus
from album_builder.domain.track import Track
from album_builder.services.album_store import AlbumStore
from album_builder.services.usage_index import UsageIndex
from album_builder.ui.library_pane import COLUMNS, LibraryPane, TrackTableModel


def _track(path_str: str, title: str = "T") -> Track:
    return Track(
        path=Path(path_str), title=title, artist="A", album_artist="A",
        composer="C", album="Alb", comment="", lyrics_text=None,
        cover_data=None, cover_mime=None, duration_seconds=180.0,
        file_size_bytes=0, is_missing=False,
    )


@pytest.fixture
def store(qapp, tmp_path):
    return AlbumStore(tmp_path / "Albums")


@pytest.fixture
def usage_index(qapp, store):
    return UsageIndex(store)


# Spec: TC-13 prereq - model accepts a UsageIndex reference.
def test_set_usage_index_stores_reference(qapp, usage_index) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    model.set_usage_index(usage_index)
    assert model._usage_index is usage_index


# Spec: TC-13 prereq - set_album_state accepts current_album_id kwarg.
def test_set_album_state_accepts_current_album_id(qapp) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    aid = uuid4()
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.APPROVED, target=1,
        current_album_id=aid,
    )
    assert model._current_album_id == aid


# Spec: TC-13 prereq - default None preserves existing call-site behaviour.
def test_set_album_state_current_album_id_defaults_to_none(qapp) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    assert model._current_album_id is None


# Spec: TC-13-09a - column at index len(COLUMNS) - 1, header "Used".
def test_TC_13_09a_used_column_position_and_header(qapp) -> None:
    last = COLUMNS[-1]
    assert last == ("Used", "_used")


def test_used_column_resolved_by_helper(qapp) -> None:
    from album_builder.ui.library_pane import _column_index
    assert _column_index("_used") == len(COLUMNS) - 1


def _model_with_index_count(qapp, count: int) -> TrackTableModel:
    """Build a TrackTableModel with one track and a UsageIndex that
    returns the given count for that track."""
    track = _track("/a.mp3")
    model = TrackTableModel([track])
    fake_index = MagicMock(spec=UsageIndex)
    fake_index.count_for.return_value = count
    fake_index.album_ids_for.return_value = ()
    model.set_usage_index(fake_index)
    return model


def _used_idx(model: TrackTableModel):
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    return model.index(0, used_col)


# Spec: TC-13-10 - DisplayRole returns "" when count == 0.
def test_TC_13_10_display_empty_when_count_zero(qapp) -> None:
    model = _model_with_index_count(qapp, 0)
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == ""


# Spec: TC-13-11 - DisplayRole returns str(count) when count >= 1.
def test_TC_13_11_display_str_count(qapp) -> None:
    for count in (1, 2, 17, 100):
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.DisplayRole,
        ) == str(count)


# Spec: TC-13-18 - no abbreviation: 17 -> "17", 100 -> "100", never "10+".
def test_TC_13_18_no_abbreviation(qapp) -> None:
    for count, expected in [(17, "17"), (99, "99"), (100, "100"), (250, "250")]:
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.DisplayRole,
        ) == expected


# Spec: TC-13-13 - AccessibleTextRole singular/plural.
def test_TC_13_13_accessible_text_role(qapp) -> None:
    cases = [
        (0, ""),
        (1, "Used in 1 other approved album"),
        (2, "Used in 2 other approved albums"),
        (5, "Used in 5 other approved albums"),
    ]
    for count, expected in cases:
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.AccessibleTextRole,
        ) == expected


# Spec: TC-13-14 - UserRole returns the integer count.
def test_TC_13_14_sort_role_returns_int(qapp) -> None:
    for count in (0, 1, 5, 42):
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.UserRole,
        ) == count


# Spec: TC-13-28 - early-return discipline: every unhandled role returns None,
# never raises (no getattr(track, "_used") fallthrough).
def test_TC_13_28_early_return_for_unhandled_roles(qapp) -> None:
    model = _model_with_index_count(qapp, 1)
    idx = _used_idx(model)
    for role in (
        Qt.ItemDataRole.DecorationRole,
        Qt.ItemDataRole.EditRole,
        Qt.ItemDataRole.FontRole,
        Qt.ItemDataRole.BackgroundRole,
        Qt.ItemDataRole.ForegroundRole,
    ):
        assert model.data(idx, role) is None


def _make_album(store, name: str, *, status: AlbumStatus, paths: list[Path]):
    album = store.create(name=name, target_count=max(1, len(paths)))
    for p in paths:
        album.select(p)
    if status == AlbumStatus.APPROVED:
        album.approve()
    return album


# Spec: TC-13-16 - self-exclusion when current is approved + only on current.
def test_TC_13_16_self_exclusion_only_on_current(qapp, store) -> None:
    p = Path("/tracks/only-here.mp3")
    a1 = _make_album(store, "Only", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths={p}, status=AlbumStatus.APPROVED, target=1,
        current_album_id=a1.id,
    )
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == ""


# Spec: TC-13-22 - self-exclusion: current approved + 2 others -> count 2.
def test_TC_13_22_self_exclusion_with_others(qapp, store) -> None:
    p = Path("/tracks/three-times.mp3")
    current = _make_album(
        store, "Current", status=AlbumStatus.APPROVED, paths=[p],
    )
    _make_album(store, "Other A", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Other B", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths={p}, status=AlbumStatus.APPROVED, target=1,
        current_album_id=current.id,
    )
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == "2"


# Spec: TC-13-23 - current is draft -> no exclusion, all approved contribute.
def test_TC_13_23_no_exclusion_when_current_draft(qapp, store) -> None:
    p = Path("/tracks/in-everything.mp3")
    _make_album(store, "Approved A", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Approved B", status=AlbumStatus.APPROVED, paths=[p])
    draft = _make_album(
        store, "Draft", status=AlbumStatus.DRAFT, paths=[p],
    )
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths={p}, status=AlbumStatus.DRAFT, target=1,
        current_album_id=draft.id,
    )
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == "2"


# Spec: TC-13-12 - tooltip exact multi-line string with sorted album names.
def test_TC_13_12_tooltip_alphabetical_with_middot(qapp, store) -> None:
    p = Path("/tracks/multi.mp3")
    _make_album(store, "Zulu", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "alpha", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Bravo", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    tooltip = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    assert tooltip == (
        "Used in approved albums:\n"
        "  · alpha\n"
        "  · Bravo\n"
        "  · Zulu"
    )


# Spec: TC-13-27 - count == 0 returns None (not empty string).
def test_TC_13_27_tooltip_none_when_count_zero(qapp) -> None:
    model = _model_with_index_count(qapp, 0)
    assert model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole) is None


# Spec: TC-13-20 - live rename lookup; renamed album shows new name.
def test_TC_13_20_tooltip_live_rename_lookup(qapp, store) -> None:
    p = Path("/tracks/renamed.mp3")
    a = _make_album(store, "Old Name", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    tip1 = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    assert "Old Name" in tip1

    store.rename(a.id, "New Name")
    tip2 = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    assert "New Name" in tip2
    assert "Old Name" not in tip2


# Spec: TC-13-29 - race tolerance: store.get(id) returning None silently dropped.
def test_TC_13_29_tooltip_skips_missing_album(qapp, store) -> None:
    p = Path("/tracks/race.mp3")
    a1 = _make_album(store, "Alpha", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Beta", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    # Index still contains both ids; store has only one.
    store._albums.pop(a1.id)

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    tip = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    assert "Beta" in tip
    assert "Alpha" not in tip


def test_tooltip_returns_none_when_all_ids_missing(qapp, store) -> None:
    p = Path("/tracks/all-gone.mp3")
    a = _make_album(store, "Solo", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()
    store._albums.pop(a.id)

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    assert model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole) is None


# Spec: TC-13-30 - plain-text safety: HTML-like names render as literal text.
def test_TC_13_30_tooltip_plain_text_html_safe(qapp, store) -> None:
    p = Path("/tracks/html.mp3")
    _make_album(
        store, "<b>Loud</b>", status=AlbumStatus.APPROVED, paths=[p],
    )
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    tip = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    # Either escaped (&lt;b&gt;Loud&lt;/b&gt;) or rendered as literal characters.
    contains_escaped = "&lt;b&gt;Loud&lt;/b&gt;" in tip
    contains_literal = "<b>Loud</b>" in tip
    assert contains_escaped or contains_literal
    assert "Loud" in tip


# Spec: TC-13-21 - headerData AccessibleTextRole + non-regression for other columns.
def test_TC_13_21_header_accessible_text(qapp) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    title_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "title")

    assert model.headerData(
        used_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.AccessibleTextRole,
    ) == "Cross-album reuse count"

    # Other columns: AccessibleTextRole returns the visible header text
    # (no regression to None).
    assert model.headerData(
        title_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.AccessibleTextRole,
    ) == "Title"

    # Vertical orientation: still returns None.
    assert model.headerData(
        used_col, Qt.Orientation.Vertical, Qt.ItemDataRole.AccessibleTextRole,
    ) is None

    # DisplayRole still works (no regression).
    assert model.headerData(
        used_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole,
    ) == "Used"


# Spec: TC-13-31 - empty-table guard: rowCount == 0 -> no dataChanged emit.
def test_TC_13_31_empty_table_guard(qapp, store) -> None:
    pane = LibraryPane()
    idx = UsageIndex(store)
    pane.set_usage_index(idx)
    assert pane._model.rowCount() == 0

    spy = QSignalSpy(pane._model.dataChanged)
    idx.changed.emit()  # would normally trigger _on_usage_changed
    assert len(spy) == 0  # skipped because empty


# Spec: TC-13-26 - proxy.invalidate fires when sortColumn == USED_COL.
def test_TC_13_26_proxy_invalidate_on_used_sort(qapp, store) -> None:
    pane = LibraryPane()
    pane._model.set_tracks([_track("/a.mp3"), _track("/b.mp3", title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    pane.table.sortByColumn(used_col, Qt.SortOrder.DescendingOrder)

    spy_invalidate = MagicMock()
    pane._proxy.invalidate = spy_invalidate
    idx.changed.emit()
    spy_invalidate.assert_called_once()


def test_proxy_not_invalidated_when_sort_not_used(qapp, store) -> None:
    pane = LibraryPane()
    pane._model.set_tracks([_track("/a.mp3"), _track("/b.mp3", title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    title_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "title")
    pane.table.sortByColumn(title_col, Qt.SortOrder.AscendingOrder)

    spy_invalidate = MagicMock()
    pane._proxy.invalidate = spy_invalidate
    idx.changed.emit()
    spy_invalidate.assert_not_called()


def _make_album_obj(name: str, status: AlbumStatus, paths: list[Path]):
    """Construct a domain-layer Album directly (no AlbumStore round-trip)."""
    from datetime import UTC, datetime
    from uuid import uuid4
    from album_builder.domain.album import Album
    now = datetime.now(UTC)
    a = Album(
        id=uuid4(), name=name, target_count=max(1, len(paths)),
        track_paths=list(paths), status=AlbumStatus.DRAFT,
        cover_override=None, created_at=now, updated_at=now,
    )
    if status == AlbumStatus.APPROVED:
        a.approve()
    return a


# Spec: TC-13-24 - set_current_album propagates the album_id into the model.
def test_TC_13_24_set_current_album_propagates_id(qapp) -> None:
    pane = LibraryPane()
    p = Path("/a.mp3")
    pane._model.set_tracks([_track(str(p))])
    a = _make_album_obj("Current", AlbumStatus.APPROVED, [p])

    pane.set_current_album(a)
    assert pane._model._current_album_id == a.id

    pane.set_current_album(None)
    assert pane._model._current_album_id is None

    draft = _make_album_obj("Draft", AlbumStatus.DRAFT, [p])
    pane.set_current_album(draft)
    assert pane._model._current_album_id == draft.id


# Spec: TC-13-17 - sort cycle desc -> asc -> desc on header click (Qt 2-state).
def test_TC_13_17_sort_cycle(qapp, store) -> None:
    pane = LibraryPane()
    pane._model.set_tracks([_track("/a.mp3"), _track("/b.mp3", title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    header = pane.table.horizontalHeader()

    header.sectionClicked.emit(used_col)  # 1st click
    assert pane._proxy.sortOrder() == Qt.SortOrder.DescendingOrder

    header.sectionClicked.emit(used_col)  # 2nd click
    assert pane._proxy.sortOrder() == Qt.SortOrder.AscendingOrder

    header.sectionClicked.emit(used_col)  # 3rd click
    assert pane._proxy.sortOrder() == Qt.SortOrder.DescendingOrder


# Spec: TC-13-25 - heterogeneous sort role (int + tuple) does not raise.
def test_TC_13_25_sort_heterogeneity_no_raise(qapp, store) -> None:
    pane = LibraryPane()
    p1, p2 = Path("/a.mp3"), Path("/b.mp3")
    pane._model.set_tracks([_track(str(p1)), _track(str(p2), title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    a = _make_album_obj("A", AlbumStatus.DRAFT, [p1])
    pane.set_current_album(a)

    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    toggle_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_toggle")

    # Both should sort without raising.
    pane._proxy.sort(used_col, Qt.SortOrder.DescendingOrder)
    pane._proxy.sort(toggle_col, Qt.SortOrder.DescendingOrder)
