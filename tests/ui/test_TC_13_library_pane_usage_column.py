"""Library-pane Used-column tests (Spec 13 TC-13-09..32 across model/pane)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from album_builder.domain.album import AlbumStatus
from album_builder.domain.track import Track
from album_builder.services.album_store import AlbumStore
from album_builder.services.usage_index import UsageIndex
from album_builder.ui.library_pane import TrackTableModel


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
    from album_builder.ui.library_pane import COLUMNS
    last = COLUMNS[-1]
    assert last == ("Used", "_used")


def test_used_column_resolved_by_helper(qapp) -> None:
    from album_builder.ui.library_pane import COLUMNS, _column_index
    assert _column_index("_used") == len(COLUMNS) - 1
