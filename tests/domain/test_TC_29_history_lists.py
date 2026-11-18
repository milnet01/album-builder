"""The three smart lists over keys - Spec 29 §4.4 (TC-29-11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from album_builder.domain.play_history import (
    SongStats,
    favourites,
    most_played,
    recently_played,
)

T0 = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


# Spec: TC-29-11
def test_favourites_newest_heart_first_no_limit() -> None:
    stats = {
        f"s{i:03}.mp3": SongStats(favourited=_at(i)) for i in range(60)
    }
    stats["unhearted.mp3"] = SongStats(plays=3, last_played=_at(0))
    result = favourites(stats)
    assert len(result) == 60
    assert result[0] == "s059.mp3"
    assert result[-1] == "s000.mp3"
    assert "unhearted.mp3" not in result


# Spec: TC-29-11
def test_recently_played_newest_first_limit_and_ties() -> None:
    stats = {f"s{i:03}.mp3": SongStats(plays=1, last_played=_at(i)) for i in range(60)}
    stats["hearted_only.mp3"] = SongStats(favourited=_at(100))
    result = recently_played(stats)
    assert len(result) == 50
    assert result[0] == "s059.mp3"
    assert result[-1] == "s010.mp3"
    assert "hearted_only.mp3" not in result
    # Equal times order by key, never by insertion.
    tied = {
        "b.mp3": SongStats(plays=1, last_played=T0),
        "a.mp3": SongStats(plays=1, last_played=T0),
    }
    assert recently_played(tied) == ["a.mp3", "b.mp3"]
    assert recently_played(stats, limit=2) == ["s059.mp3", "s058.mp3"]


# Spec: TC-29-11
def test_most_played_order_ties_and_limit() -> None:
    stats = {
        # Inserted so that insertion order disagrees with every tie-break.
        "z_old.mp3": SongStats(plays=5, last_played=_at(1)),
        "y_new.mp3": SongStats(plays=5, last_played=_at(2)),
        "b_same.mp3": SongStats(plays=5, last_played=_at(2)),
        "top.mp3": SongStats(plays=9, last_played=_at(0)),
        "none.mp3": SongStats(favourited=_at(3)),
    }
    assert most_played(stats) == ["top.mp3", "b_same.mp3", "y_new.mp3", "z_old.mp3"]
    many = {f"s{i:03}.mp3": SongStats(plays=i + 1, last_played=T0) for i in range(60)}
    result = most_played(many)
    assert len(result) == 50
    assert result[0] == "s059.mp3"
    assert result[-1] == "s010.mp3"
