"""LRC sidecar I/O — Spec 07.

Sibling files at `<audio>.lrc`. Reads parse via the domain `parse_lrc`;
malformed LRCs are renamed to `<stem>.lrc.bak` and the original removed
so the freshness check correctly reports "not yet aligned" until the
worker regenerates.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from album_builder.domain.lyrics import LRCParseError, Lyrics, format_lrc, parse_lrc
from album_builder.persistence.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)


def lrc_path_for(audio_path: Path) -> Path:
    """Return `<audio>.lrc` next to the audio file."""
    return audio_path.with_suffix(".lrc")


def is_lrc_fresh(audio_path: Path) -> bool:
    """True iff the sibling LRC exists and is at least as new as the audio.

    Returns False if either file is missing — defensive against `stat`
    races on a watcher rescan.
    """
    lrc = lrc_path_for(audio_path)
    try:
        return lrc.stat().st_mtime >= audio_path.stat().st_mtime
    except OSError:
        return False


def read_lrc(audio_path: Path) -> Lyrics | None:
    """Read and parse the sibling LRC.

    Returns the parsed `Lyrics` on success, `None` if the LRC file is
    missing. On parse failure, the malformed file is renamed to
    `<stem>.lrc.bak` (overwriting any existing `.bak`) and `None` is
    returned — the caller treats this as "not yet aligned" and may
    offer to regenerate. Spec 07 TC-07-10.
    """
    lrc = lrc_path_for(audio_path)
    try:
        text = lrc.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("LRC unreadable at %s: %s", lrc, exc)
        return None
    try:
        # parse_lrc binds track_path so downstream consumers (LyricsTracker,
        # panel) can identify which audio this Lyrics is for (L1-H1).
        return parse_lrc(text, track_path=audio_path)
    except LRCParseError as exc:
        bak = lrc.with_suffix(".lrc.bak")
        try:
            shutil.move(str(lrc), str(bak))
            logger.info("Backed up malformed LRC: %s -> %s (%s)", lrc, bak, exc)
        except OSError as move_exc:
            logger.warning("Could not back up malformed LRC %s: %s", lrc, move_exc)
        return None


def write_lrc(audio_path: Path, lyrics: Lyrics) -> None:
    """Atomically write the LRC next to the audio file.

    The freshness check (`is_lrc_fresh`) compares mtimes; the atomic
    rename gives the new file a fresh mtime, so the check returns True
    immediately after this returns.
    """
    lrc = lrc_path_for(audio_path)
    text = format_lrc(lyrics)
    atomic_write_text(lrc, text)
