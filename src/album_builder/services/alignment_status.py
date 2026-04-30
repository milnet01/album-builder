"""Alignment status enum + helpers — Spec 07 §status pill.

`compute_status` covers the on-disk-derived states; the live ALIGNING /
FAILED / AUDIO_TOO_SHORT states are owned by `AlignmentService`.
"""

from __future__ import annotations

from enum import Enum, auto

from album_builder.domain.track import Track
from album_builder.persistence.lrc_io import is_lrc_fresh


class AlignmentStatus(Enum):
    NO_LYRICS_TEXT = auto()
    NOT_YET_ALIGNED = auto()
    ALIGNING = auto()
    READY = auto()
    FAILED = auto()
    AUDIO_TOO_SHORT = auto()


def compute_status(track: Track) -> AlignmentStatus:
    """Derive the alignment status from on-disk + tag state.

    `ALIGNING`, `FAILED`, and `AUDIO_TOO_SHORT` are runtime states owned by
    `AlignmentService`; this function never returns them. The service
    transitions through them and re-syncs to the on-disk-derived value
    (READY or NOT_YET_ALIGNED) on completion.
    """
    if not track.lyrics_text or not track.lyrics_text.strip():
        return AlignmentStatus.NO_LYRICS_TEXT
    if is_lrc_fresh(track.path):
        return AlignmentStatus.READY
    return AlignmentStatus.NOT_YET_ALIGNED


def status_label(status: AlignmentStatus, percent: int | None = None) -> str:
    """User-visible string for the LyricsPanel status pill."""
    match status:
        case AlignmentStatus.NO_LYRICS_TEXT:
            return "LRC: no lyrics text"
        case AlignmentStatus.NOT_YET_ALIGNED:
            return "LRC: not yet aligned"
        case AlignmentStatus.ALIGNING:
            if percent is None:
                return "LRC: aligning..."
            return f"LRC: aligning... {percent}%"
        case AlignmentStatus.READY:
            return "LRC: ✓ ready"
        case AlignmentStatus.FAILED:
            return "LRC: alignment failed"
        case AlignmentStatus.AUDIO_TOO_SHORT:
            return "LRC: audio too short to align"
