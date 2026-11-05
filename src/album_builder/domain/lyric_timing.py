"""Time lyric lines by matching the user's lyric words to the words heard.

Spec 07 TC-07-18 / TC-07-19 (MUSI-0404). WhisperX transcribes the song and
times each word it hears. The old pipeline paired lyric LINES with transcript
SEGMENTS by position, so one merged or split segment shifted every later line.
This module lines up the two word sequences instead, so each lyric line takes
the time of its own words. Pure logic: no Qt, no model.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# A word: letters or digits, with inner apostrophes ("don't"). The apostrophe
# is dropped afterwards so "don't" and "dont" match.
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")

HeardWord = tuple[str, float | None]  # (normalised word, start time or None)


class NothingHeard(Exception):
    """The transcript holds no words, so no line can be timed (TC-07-19)."""


def words_of(text: str) -> list[str]:
    """`text` as normalised words: case-folded, punctuation dropped."""
    return [m.group(0).casefold().replace("'", "") for m in _WORD.finditer(text)]


def heard_words(aligned: dict) -> tuple[list[HeardWord], float]:
    """Flatten a WhisperX aligned result into timed words, plus the latest
    end time seen (where trailing unheard lines go).

    A segment's per-word timings are used when present; a segment without
    them spreads its text evenly across its own start..end."""
    out: list[HeardWord] = []
    end = 0.0
    for seg in aligned.get("segments") or []:
        seg_start, seg_end = seg.get("start"), seg.get("end")
        for value in (seg_start, seg_end):
            if value is not None:
                end = max(end, float(value))
        timed = seg.get("words")
        if timed:
            for w in timed:
                start = w.get("start")
                if w.get("end") is not None:
                    end = max(end, float(w["end"]))
                for token in words_of(w.get("word", "")):
                    out.append((token, float(start) if start is not None else None))
            continue
        tokens = words_of(seg.get("text", ""))
        if seg_start is None:
            out.extend((t, None) for t in tokens)
            continue
        span = (float(seg_end) - float(seg_start)) if seg_end is not None else 0.0
        step = span / len(tokens) if tokens else 0.0
        out.extend((t, float(seg_start) + i * step) for i, t in enumerate(tokens))
    return out, end


def line_start_times(lines: list[str], heard: list[HeardWord], *, end_time: float) -> list[float]:
    """Start time for each of `lines`.

    Matched words take their heard time; a run of misheard words is spread
    over the heard span it replaced. A line starts at its first timed word.
    A line with none sits evenly between its timed neighbours; trailing
    lines go to `end_time` (Spec 07 §Errors). Times never decrease.
    Raises NothingHeard when `heard` is empty."""
    if not heard:
        raise NothingHeard
    lyric: list[str] = []
    owner: list[int] = []  # line index of each lyric word
    for li, line in enumerate(lines):
        for token in words_of(line):
            lyric.append(token)
            owner.append(li)
    heard_tokens = [w for w, _ in heard]
    time_of: list[float | None] = [None] * len(lyric)
    matcher = SequenceMatcher(None, lyric, heard_tokens, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                time_of[i1 + k] = heard[j1 + k][1]
        elif tag == "replace":
            for k in range(i2 - i1):
                time_of[i1 + k] = heard[j1 + (k * (j2 - j1)) // (i2 - i1)][1]

    starts: list[float | None] = [None] * len(lines)
    for i, t in enumerate(time_of):
        if t is not None and starts[owner[i]] is None:
            starts[owner[i]] = t
    return _fill_gaps(starts, end_time)


def _fill_gaps(starts: list[float | None], end_time: float) -> list[float]:
    """Space untimed lines between timed neighbours; send trailing ones to
    `end_time`; leading ones take the first known time; never decrease."""
    known = [i for i, t in enumerate(starts) if t is not None]
    out: list[float] = []
    for i, t in enumerate(starts):
        if t is None:
            before = max((k for k in known if k < i), default=None)
            after = min((k for k in known if k > i), default=None)
            if after is None:
                t = end_time
            elif before is None:
                t = starts[after]
            else:
                lo, hi = starts[before], starts[after]
                t = lo + (hi - lo) * (i - before) / (after - before)
        out.append(max(t, out[-1]) if out else t)
    return out
