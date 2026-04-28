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
