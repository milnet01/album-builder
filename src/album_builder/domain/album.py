"""Album - state machine for a single album draft.

Mutations are method calls on the instance; persistence is layered above
in album_io.py (load/save) and AlbumStore (debounced disk writes).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4


class AlbumStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_name(name: str) -> str:
    n = name.strip()
    if not (1 <= len(n) <= 80):
        raise ValueError(f"name must be 1-80 chars after trim, got {len(n)}")
    return n


def _validate_target(t: int) -> int:
    if not (1 <= t <= 99):
        raise ValueError(f"target_count must be 1-99, got {t}")
    return t


@dataclass
class Album:
    id: UUID
    name: str
    target_count: int
    track_paths: list[Path]
    status: AlbumStatus
    cover_override: Path | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        # Defensive invariant for direct dataclass construction (load from JSON,
        # tests, future code). The mutating methods (`select`, `set_target`,
        # `reorder`) all enforce target_count >= len(track_paths); persistence
        # self-heal (album_io._deserialize, TC-04-09) bumps target_count on a
        # corrupt file before construction. Anything that bypasses both paths
        # gets caught here.
        if not (1 <= self.target_count <= 99):
            raise ValueError(
                f"target_count must be 1-99, got {self.target_count}"
            )
        if self.target_count < len(self.track_paths):
            raise ValueError(
                f"target_count ({self.target_count}) < len(track_paths) "
                f"({len(self.track_paths)}); fix at the load site or via "
                f"persistence self-heal"
            )
        if self.status == AlbumStatus.APPROVED and not self.track_paths:
            raise ValueError("approved album must have at least one track")

    @classmethod
    def create(cls, *, name: str, target_count: int) -> Album:
        now = _now()
        return cls(
            id=uuid4(),
            name=_validate_name(name),
            target_count=_validate_target(target_count),
            track_paths=[],
            status=AlbumStatus.DRAFT,
            cover_override=None,
            created_at=now,
            updated_at=now,
        )

    def rename(self, new_name: str) -> None:
        self.name = _validate_name(new_name)
        self.updated_at = _now()

    def _require_draft(self, action: str) -> None:
        if self.status != AlbumStatus.DRAFT:
            raise ValueError(f"cannot {action} an approved album; reopen for editing first")

    def select(self, track_path: Path) -> None:
        self._require_draft("select")
        if track_path in self.track_paths:
            return
        if len(self.track_paths) >= self.target_count:
            raise ValueError(
                f"album is at target ({self.target_count}); deselect first or raise the target"
            )
        self.track_paths.append(track_path)
        self.updated_at = _now()

    def deselect(self, track_path: Path) -> None:
        self._require_draft("deselect")
        try:
            self.track_paths.remove(track_path)
        except ValueError:
            return  # absent - no-op, no write
        self.updated_at = _now()

    def set_target(self, n: int) -> None:
        self._require_draft("set target")
        n = _validate_target(n)
        if n < len(self.track_paths):
            raise ValueError(
                f"target {n} is below current selection ({len(self.track_paths)}); "
                "deselect tracks first"
            )
        self.target_count = n
        self.updated_at = _now()

    def reorder(self, from_idx: int, to_idx: int) -> None:
        self._require_draft("reorder")
        n = len(self.track_paths)
        if not (0 <= from_idx < n and 0 <= to_idx < n):
            raise IndexError(f"reorder out of range: from={from_idx} to={to_idx} len={n}")
        if from_idx == to_idx:
            return  # no-op, no write
        item = self.track_paths.pop(from_idx)
        self.track_paths.insert(to_idx, item)
        self.updated_at = _now()

    def approve(self) -> None:
        """Flip status DRAFT -> APPROVED with timestamps.

        Domain-level checks: status must be DRAFT, track_paths non-empty.
        The MISSING-track-on-disk precondition (Spec 02 TC-02-10:
        FileNotFoundError if any path doesn't exist) is enforced ONE LAYER UP
        in `AlbumStore.approve()`, which calls this method only after the
        path-existence check. Direct callers of `Album.approve()` MUST
        replicate that check or accept the risk of approving an album whose
        files have moved out from under it.
        """
        if self.status != AlbumStatus.DRAFT:
            raise ValueError(f"cannot approve from status {self.status!r}; only draft -> approved")
        if not self.track_paths:
            raise ValueError("cannot approve an empty album; select at least one track")
        now = _now()
        self.status = AlbumStatus.APPROVED
        self.approved_at = now
        self.updated_at = now

    def unapprove(self) -> None:
        if self.status != AlbumStatus.APPROVED:
            raise ValueError(f"cannot unapprove from status {self.status!r}")
        # Defensive: an approved album with target_count < len(track_paths)
        # should be impossible (approve() requires at least one track and
        # the __post_init__ invariant rejects target<len at construction).
        # Re-check here so a future code path that bypasses both can't
        # silently leave a draft in an invalid state.
        assert self.target_count >= len(self.track_paths), (
            f"target_count ({self.target_count}) < len(track_paths) "
            f"({len(self.track_paths)}) on unapprove — invariant violated"
        )
        self.status = AlbumStatus.DRAFT
        self.approved_at = None
        self.updated_at = _now()
