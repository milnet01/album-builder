"""Library-pane Used-column tests (Spec 13 TC-13-09..32 across model/pane)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.album import AlbumStatus
from album_builder.domain.track import Track
from album_builder.services.album_store import AlbumStore
from album_builder.services.usage_index import UsageIndex
from album_builder.ui.library_pane import COLUMNS, TrackTableModel


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
