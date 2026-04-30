"""Tests for album_builder.domain.album - see docs/specs/02-album-lifecycle.md,
04-track-selection.md, 05-track-ordering.md test contracts."""

from datetime import datetime
from pathlib import Path

import pytest

from album_builder.domain.album import Album, AlbumStatus


# Spec: TC-02-01
def test_album_create_returns_draft_with_fresh_uuid() -> None:
    a = Album.create(name="Memoirs of a Sinner", target_count=12)
    assert a.status == AlbumStatus.DRAFT
    assert a.track_paths == []
    assert a.target_count == 12
    assert a.approved_at is None
    assert isinstance(a.created_at, datetime)
    assert a.created_at.tzinfo is not None  # always UTC-aware
    a2 = Album.create(name="Other", target_count=8)
    assert a.id != a2.id


# Spec: TC-02-02
@pytest.mark.parametrize("bad", ["", "   ", "x" * 81])
def test_album_create_rejects_bad_names(bad: str) -> None:
    with pytest.raises(ValueError):
        Album.create(name=bad, target_count=12)


# Spec: TC-02-03
@pytest.mark.parametrize("bad", [0, -1, -99])
def test_album_create_rejects_bad_target(bad: int) -> None:
    with pytest.raises(ValueError):
        Album.create(name="ok", target_count=bad)


# Spec: TC-02-06
@pytest.mark.parametrize("bad", ["", "   ", "x" * 81])
def test_album_rename_rejects_bad_names(bad: str) -> None:
    a = Album.create(name="ok", target_count=12)
    with pytest.raises(ValueError):
        a.rename(bad)


# Spec: TC-02-06
def test_album_rename_updates_name_and_updated_at() -> None:
    a = Album.create(name="ok", target_count=12)
    before = a.updated_at
    a.rename("New Name")
    assert a.name == "New Name"
    assert a.updated_at >= before


# Spec: TC-04-01
def test_album_select_appends_when_absent() -> None:
    a = Album.create(name="x", target_count=3)
    p = Path("/abs/track1.mp3")
    a.select(p)
    assert a.track_paths == [p]


# Spec: TC-04-01, TC-04-03
def test_album_select_idempotent_preserves_order() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.select(Path("/abs/b.mp3"))
    a.select(Path("/abs/a.mp3"))  # already present
    assert a.track_paths == [Path("/abs/a.mp3"), Path("/abs/b.mp3")]


# Spec: TC-04-02
def test_album_select_rejects_when_approved() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.status = AlbumStatus.APPROVED  # bypass approve() for unit test
    with pytest.raises(ValueError):
        a.select(Path("/abs/b.mp3"))


# Spec: TC-04-04
def test_album_deselect_preserves_relative_order() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abcd":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.deselect(Path("/abs/b.mp3"))
    assert a.track_paths == [Path("/abs/a.mp3"), Path("/abs/c.mp3"), Path("/abs/d.mp3")]


# Spec: TC-04-05
def test_album_deselect_absent_is_noop() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.deselect(Path("/abs/missing.mp3"))
    assert a.track_paths == [Path("/abs/a.mp3")]


# Spec: TC-04-06, TC-04-07
def test_album_set_target_floor_is_current_selection_length() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abc":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.set_target(3)  # boundary-equal allowed
    assert a.target_count == 3
    with pytest.raises(ValueError):
        a.set_target(2)  # below current selection - refused


# Spec: TC-04-08
@pytest.mark.parametrize("bad", [0, -1, 100, 200])
def test_album_set_target_range(bad: int) -> None:
    a = Album.create(name="x", target_count=5)
    with pytest.raises(ValueError):
        a.set_target(bad)


# Spec: TC-05-01
def test_album_reorder_basic() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abcd":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.reorder(2, 0)  # move C to front: [a,b,c,d] -> [c,a,b,d]
    assert [p.stem for p in a.track_paths] == ["c", "a", "b", "d"]


# Spec: TC-05-02
def test_album_reorder_out_of_range_raises() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "ab":
        a.select(Path(f"/abs/{letter}.mp3"))
    with pytest.raises(IndexError):
        a.reorder(5, 0)
    with pytest.raises(IndexError):
        a.reorder(0, 5)
    with pytest.raises(IndexError):
        a.reorder(-1, 0)


# Spec: TC-05-03
def test_album_reorder_rejected_when_approved() -> None:
    a = Album.create(name="x", target_count=5)
    a.select(Path("/abs/a.mp3"))
    a.select(Path("/abs/b.mp3"))
    a.status = AlbumStatus.APPROVED
    with pytest.raises(ValueError):
        a.reorder(0, 1)


# Spec: TC-05-06
def test_album_reorder_does_not_change_set_membership() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abcd":
        a.select(Path(f"/abs/{letter}.mp3"))
    before = set(a.track_paths)
    a.reorder(3, 0)
    assert set(a.track_paths) == before


# Spec: TC-02-09
def test_album_approve_rejects_empty_selection() -> None:
    a = Album.create(name="x", target_count=3)
    with pytest.raises(ValueError):
        a.approve()


# Spec: TC-02-11
def test_album_approve_rejected_when_already_approved() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.status = AlbumStatus.APPROVED
    with pytest.raises(ValueError):
        a.approve()


# Spec: TC-02-12
def test_album_approve_flips_status_and_stamps() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    before = a.updated_at
    a.approve()
    assert a.status == AlbumStatus.APPROVED
    assert a.approved_at is not None
    assert a.updated_at >= before


# Spec: TC-02-14
def test_album_unapprove_clears_approval() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.approve()
    a.unapprove()
    assert a.status == AlbumStatus.DRAFT
    assert a.approved_at is None


# Indie-review L1-H3: __post_init__ invariant catches corrupt direct-construction
# (load-from-corrupt-JSON, hand-built test fixtures) that bypasses the mutating
# methods' guards.
def test_album_post_init_rejects_target_below_track_count() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4
    with pytest.raises(ValueError, match="target_count"):
        Album(
            id=uuid4(), name="x", target_count=2,
            track_paths=[Path("/abs/a.mp3"), Path("/abs/b.mp3"), Path("/abs/c.mp3")],
            status=AlbumStatus.DRAFT, cover_override=None,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )


def test_album_post_init_rejects_target_out_of_range() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4
    with pytest.raises(ValueError, match="target_count must be 1-99"):
        Album(
            id=uuid4(), name="x", target_count=0, track_paths=[],
            status=AlbumStatus.DRAFT, cover_override=None,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )


def test_album_post_init_rejects_approved_without_tracks() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4
    with pytest.raises(ValueError, match="approved album"):
        Album(
            id=uuid4(), name="x", target_count=3, track_paths=[],
            status=AlbumStatus.APPROVED, cover_override=None,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            approved_at=datetime.now(UTC),
        )


# Tier 3: Album.unapprove asserts the target invariant defensively. Direct
# callers that mutate `track_paths` through the dataclass attribute (rather
# than `select()`) and then unapprove would otherwise sneak past the
# __post_init__ check. The assert closes that gap.
def test_album_unapprove_asserts_target_invariant() -> None:
    a = Album.create(name="x", target_count=2)
    a.select(Path("/abs/a.mp3"))
    a.approve()
    # Bypass select()'s guard by mutating the list directly. This is the
    # exact misuse the assert exists to catch.
    a.track_paths.extend([Path("/abs/b.mp3"), Path("/abs/c.mp3")])
    with pytest.raises(AssertionError, match="invariant"):
        a.unapprove()


# Tier 3 (L1-M2): Album equality is UUID-identity, not field-by-field.
# Two reads of the same album from disk often differ only by `updated_at`
# millisecond drift — default-dataclass __eq__ marks them unequal and
# breaks `album in some_list` / `dict[album]` callers.
def test_album_equality_is_uuid_identity() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4
    aid = uuid4()
    base = dict(
        name="x",
        target_count=3,
        track_paths=[Path("/a.mp3")],
        status=AlbumStatus.DRAFT,
        cover_override=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    a1 = Album(id=aid, updated_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC), **base)
    a2 = Album(id=aid, updated_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC), **base)
    assert a1 == a2
    a3 = Album(id=uuid4(), updated_at=base["created_at"], **base)
    assert a1 != a3
    # Hashable: usable as dict key / set member.
    assert hash(a1) == hash(a2)
    assert {a1, a2, a3} == {a1, a3}
    # Foreign objects compare unequal, not raise.
    assert a1 != "not an album"
