"""Lyrics domain — Spec 07.

Pure-Python LRC parser, formatter, and `line_at` lookup. No Qt; no I/O.
The Qt-aware `LyricsTracker` lives in services/.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Spec 07 §Outputs: timestamp form is `[mm:ss.xx]`. We accept 1-3 minute
# digits (some LRC tools emit 3 for very long tracks) and 1-3 fraction
# digits (centisecond is two; some encoders emit milliseconds = three).
_STAMP = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]")
_TAG_HEADER = re.compile(r"^\[(?:ti|ar|al|au|by|length|offset|re|ve):.*\]$")
_SECTION_MARKER = re.compile(r"^\[[^\]]+\]$")


class LRCParseError(ValueError):
    """Raised by `parse_lrc` when the input contains no recognisable lines."""


@dataclass(frozen=True)
class LyricLine:
    time_seconds: float
    text: str
    is_section_marker: bool = False


@dataclass(frozen=True)
class Lyrics:
    lines: tuple[LyricLine, ...] = field(default_factory=tuple)
    track_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.lines, tuple):
            object.__setattr__(self, "lines", tuple(self.lines))


def _stamp_to_seconds(match: re.Match[str]) -> float:
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    frac_str = match.group(3) or "0"
    # Centiseconds (2 digits) vs milliseconds (3 digits) — divide by the
    # appropriate power of ten so the fraction lands in the right place.
    frac = int(frac_str) / (10 ** len(frac_str))
    return minutes * 60 + seconds + frac


def parse_lrc(text: str) -> Lyrics:
    """Parse an LRC string into a `Lyrics`. Raises `LRCParseError` on no lines.

    Tag headers (`[ti:..]`, `[ar:..]`, `[al:..]`, `[length:..]`) are skipped
    silently. Lines without a leading timestamp are skipped. Multiple
    timestamps on one line emit one `LyricLine` per stamp with shared text.
    """
    lines: list[LyricLine] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if _TAG_HEADER.match(stripped):
            continue
        # Walk leading timestamps
        stamps: list[float] = []
        cursor = 0
        while True:
            m = _STAMP.match(stripped, cursor)
            if not m:
                break
            stamps.append(_stamp_to_seconds(m))
            cursor = m.end()
        if not stamps:
            continue
        body = stripped[cursor:].strip()
        is_marker = bool(_SECTION_MARKER.match(body))
        for t in stamps:
            lines.append(LyricLine(time_seconds=t, text=body, is_section_marker=is_marker))
    if not lines:
        raise LRCParseError("LRC contains no parseable timestamped lines")
    lines.sort(key=lambda ln: ln.time_seconds)
    return Lyrics(lines=tuple(lines))


def _format_stamp(seconds: float) -> str:
    """Format seconds as `[mm:ss.xx]` with classic half-up centisecond rounding."""
    total_centis = int(seconds * 100 + 0.5)
    minutes, rem_centis = divmod(total_centis, 60 * 100)
    secs, centis = divmod(rem_centis, 100)
    return f"[{minutes:02d}:{secs:02d}.{centis:02d}]"


def format_lrc(
    lyrics: Lyrics,
    *,
    ti: str = "",
    ar: str = "",
    al: str = "",
    length: str = "",
) -> str:
    """Render a `Lyrics` to LRC text. Empty header fields are omitted."""
    parts: list[str] = []
    for tag, value in (("ti", ti), ("ar", ar), ("al", al), ("length", length)):
        if value:
            parts.append(f"[{tag}:{value}]")
    if parts:
        parts.append("")  # blank line between headers and body
    for ln in lyrics.lines:
        parts.append(f"{_format_stamp(ln.time_seconds)}{ln.text}")
    return "\n".join(parts) + "\n"


def line_at(lyrics: Lyrics, t: float) -> int:
    """Return the index of the active line at time `t`.

    `-1` if `t` is before the first line or `lyrics.lines` is empty.
    `len - 1` once `t >= last.time_seconds`.
    """
    if not lyrics.lines:
        return -1
    if t < lyrics.lines[0].time_seconds:
        return -1
    # Linear scan from the back is the simplest correct implementation;
    # `LyricsTracker` adds the cached-hint optimisation for the hot path.
    last = len(lyrics.lines) - 1
    for i in range(last, -1, -1):
        if lyrics.lines[i].time_seconds <= t:
            return i
    return -1
