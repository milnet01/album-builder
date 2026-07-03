"""Tests for album_builder.persistence.playlist_io - see
docs/specs/17-saved-playlists.md test contracts (TC-17-06..10). No Qt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.domain.playlist import Playlist
from album_builder.persistence.playlist_io import (
    PLAYLISTS_FILE,
    load_playlists,
    save_playlists,
)
from album_builder.persistence.schema import SchemaTooNewError, UnreadableSchemaError
from album_builder.persistence.state_io import STATE_DIR


def _file(root: Path) -> Path:
    return root / STATE_DIR / PLAYLISTS_FILE


# Spec: TC-17-06
def test_round_trips_ids_names_order_and_duplicates(tmp_path: Path) -> None:
    happy = Playlist(id="aaa", name="Happy", track_paths=[Path("/abs/a.mp3")])
    energetic = Playlist(
        id="bbb", name="Energetic", track_paths=[Path("/abs/b.mp3"), Path("/abs/b.mp3")]
    )
    save_playlists(tmp_path, [happy, energetic])

    path = _file(tmp_path)
    assert path.exists()
    doc = json.loads(path.read_text())
    assert doc["schema_version"] == 1
    assert isinstance(doc["playlists"], list)

    loaded = load_playlists(tmp_path)
    assert [pl.id for pl in loaded] == ["aaa", "bbb"]
    assert [pl.name for pl in loaded] == ["Happy", "Energetic"]
    assert loaded[1].track_paths == [Path("/abs/b.mp3"), Path("/abs/b.mp3")]  # dup kept


# Spec: TC-17-07
def test_absent_file_returns_empty(tmp_path: Path) -> None:
    assert load_playlists(tmp_path) == []


# Spec: TC-17-08
def test_relative_path_heals_to_absolute(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "playlists": [
                    {"id": "x", "name": "P", "track_paths": ["rel/a.mp3", "/abs/b.mp3"]}
                ],
            }
        )
    )
    loaded = load_playlists(tmp_path)
    paths = loaded[0].track_paths
    assert paths[0].is_absolute()
    assert paths[0] == Path("rel/a.mp3").absolute()  # .absolute(), not .resolve()
    assert paths[1] == Path("/abs/b.mp3")  # already absolute, unchanged


def _write(root: Path, text: str) -> None:
    path = _file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# Spec: TC-17-09
def test_corrupt_and_schema_errors_raise(tmp_path: Path) -> None:
    _write(tmp_path, json.dumps({"schema_version": 999, "playlists": []}))
    with pytest.raises(SchemaTooNewError):
        load_playlists(tmp_path)

    _write(tmp_path, json.dumps({"playlists": []}))  # missing schema_version
    with pytest.raises(UnreadableSchemaError):
        load_playlists(tmp_path)

    _write(tmp_path, "{not json")  # non-JSON
    with pytest.raises(json.JSONDecodeError):
        load_playlists(tmp_path)

    _write(tmp_path, "[]")  # valid JSON, non-object
    with pytest.raises(UnreadableSchemaError):
        load_playlists(tmp_path)


# Spec: TC-17-10
def test_dangling_path_survives_round_trip(tmp_path: Path) -> None:
    ghost = Path("/does/not/exist.mp3")
    save_playlists(tmp_path, [Playlist(id="x", name="P", track_paths=[ghost])])
    loaded = load_playlists(tmp_path)
    assert loaded[0].track_paths == [ghost]  # not pruned
