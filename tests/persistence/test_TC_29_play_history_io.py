"""play_history.json read/write - Spec 29 §4.1 (TC-29-01, TC-29-02)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from album_builder.domain.play_history import SongStats
from album_builder.persistence.play_history_io import (
    history_path,
    load_history,
    save_history,
)
from album_builder.persistence.schema import SchemaTooNewError, UnreadableSchemaError

FAV = datetime(2026, 11, 18, 15, 4, 5, 123000, tzinfo=UTC)
PLAYED = datetime(2026, 11, 18, 16, 10, tzinfo=UTC)
GOOD = {"favourited": None, "last_played": "2026-11-17T09:00:00.000Z", "plays": 1}


def _write(root: Path, songs: object, version: object = 1) -> None:
    path = history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": version, "songs": songs}), encoding="utf-8")


# Spec: TC-29-01
def test_round_trip(tmp_path: Path) -> None:
    stats = {
        "Slow Tide.mp3": SongStats(plays=12, last_played=PLAYED, favourited=FAV),
        "Walking Home Late.flac": SongStats(plays=1, last_played=PLAYED),
        "Hearted.ogg": SongStats(favourited=FAV),
    }
    save_history(tmp_path, stats)
    assert load_history(tmp_path) == stats

    text = history_path(tmp_path).read_text(encoding="utf-8")
    assert json.loads(text)["songs"]["Walking Home Late.flac"] == {
        "favourited": None,
        "last_played": "2026-11-18T16:10:00.000Z",
        "plays": 1,
    }
    assert '"favourited": "2026-11-18T15:04:05.123Z"' in text
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True)


# Spec: TC-29-01
def test_empty_entry_not_written_and_absent_file_is_empty(tmp_path: Path) -> None:
    assert load_history(tmp_path) == {}
    save_history(tmp_path, {"gone.mp3": SongStats(), "kept.mp3": SongStats(plays=1)})
    songs = json.loads(history_path(tmp_path).read_text(encoding="utf-8"))["songs"]
    assert list(songs) == ["kept.mp3"]


# Spec: TC-29-02
@pytest.mark.parametrize(
    ("bad", "expected"),
    [
        ({"plays": "3"}, SongStats(last_played=PLAYED, favourited=FAV)),
        ({"plays": -1}, SongStats(last_played=PLAYED, favourited=FAV)),
        ({"plays": True}, SongStats(last_played=PLAYED, favourited=FAV)),
        ({"plays": 2.5}, SongStats(last_played=PLAYED, favourited=FAV)),
        ({"last_played": "yesterday"}, SongStats(plays=4, favourited=FAV)),
        ({"last_played": "2026-11-18T16:10:00.000"}, SongStats(plays=4, favourited=FAV)),
        ({"last_played": 5}, SongStats(plays=4, favourited=FAV)),
        ({"favourited": "not a time"}, SongStats(plays=4, last_played=PLAYED)),
        ({"favourited": "2026-11-18T15:04:05"}, SongStats(plays=4, last_played=PLAYED)),
        ({"favourited": []}, SongStats(plays=4, last_played=PLAYED)),
    ],
)
def test_field_heal(tmp_path: Path, bad: dict, expected: SongStats) -> None:
    entry = {
        "favourited": "2026-11-18T15:04:05.123Z",
        "last_played": "2026-11-18T16:10:00.000Z",
        "plays": 4,
        **bad,
    }
    _write(tmp_path, {"bad.mp3": entry, "good.mp3": GOOD})
    loaded = load_history(tmp_path)
    assert loaded["bad.mp3"] == expected
    assert loaded["good.mp3"] == SongStats(
        plays=1, last_played=datetime(2026, 11, 17, 9, tzinfo=UTC),
    )


# Spec: TC-29-02
def test_non_object_entry_dropped_alone(tmp_path: Path) -> None:
    _write(tmp_path, {"bad.mp3": [1, 2], "worse.mp3": None, "good.mp3": GOOD})
    assert list(load_history(tmp_path)) == ["good.mp3"]


# Spec: TC-29-03
@pytest.mark.parametrize(
    "raw",
    [
        b"\xff\xfe not utf-8",
        b"{ not json",
        b"[]",
        b'{"songs": {}}',
        b'{"schema_version": 1}',
        b'{"schema_version": 1, "songs": []}',
    ],
)
def test_whole_file_failures_raise(tmp_path: Path, raw: bytes) -> None:
    path = history_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    with pytest.raises((UnreadableSchemaError, json.JSONDecodeError)):
        load_history(tmp_path)


# Spec: TC-29-03
def test_newer_schema_raises(tmp_path: Path) -> None:
    _write(tmp_path, {}, version=2)
    with pytest.raises(SchemaTooNewError):
        load_history(tmp_path)
