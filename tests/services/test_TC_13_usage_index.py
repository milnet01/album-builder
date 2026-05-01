"""Tests for album_builder.services.usage_index (Spec 13 TC-13-01..08)."""

from __future__ import annotations

import pytest

from album_builder.services.album_store import AlbumStore
from album_builder.services.usage_index import UsageIndex


@pytest.fixture
def store(qapp, tmp_path):
    return AlbumStore(tmp_path / "Albums")


# Spec: TC-13-01 prereq - basic constructor, signal exists, empty index.
def test_constructor_and_signal_exposure(qapp, store) -> None:
    idx = UsageIndex(store)
    # `changed` signal exposed
    assert hasattr(idx, "changed")
    # Empty store -> empty result on lookup of any path.
    from pathlib import Path
    assert idx.count_for(Path("/nonexistent")) == 0
    assert idx.album_ids_for(Path("/nonexistent")) == ()
