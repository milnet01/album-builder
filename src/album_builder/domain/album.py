"""Album - state machine for a single album draft.

Mutations are method calls on the instance; persistence is layered above
in album_io.py (load/save) and AlbumStore (debounced disk writes).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4


class AlbumStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017


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
