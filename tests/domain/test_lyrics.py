"""Lyrics domain tests — Spec 07 LRC parser, formatter, line_at."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from album_builder.domain.lyrics import (
    LRCParseError,
    LyricLine,
    Lyrics,
    format_lrc,
    line_at,
    parse_lrc,
)

SAMPLE_LRC = """[ti:something more]
[ar:18 Down]
[al:Memoirs of a Sinner]
[length:00:24]

[00:00.00][Intro]
[00:08.34]walking the line again
[00:12.47]feeling the weight of every word
[00:17.20]searching for something more
[00:24.00][Verse 1]
"""


# Spec: TC-07-01
def test_parse_lrc_basic():
    lyrics = parse_lrc(SAMPLE_LRC)
    assert len(lyrics.lines) == 5
    intro = lyrics.lines[0]
    assert intro.time_seconds == pytest.approx(0.0)
    assert intro.is_section_marker is True
    assert intro.text == "[Intro]"
    line2 = lyrics.lines[1]
    assert line2.time_seconds == pytest.approx(8.34)
    assert line2.is_section_marker is False
    assert line2.text == "walking the line again"
    last = lyrics.lines[-1]
    assert last.time_seconds == pytest.approx(24.0)
    assert last.is_section_marker is True
    assert last.text == "[Verse 1]"


# Spec: TC-07-01
def test_parse_lrc_centiseconds_two_or_three_digits():
    text = "[00:08.3]a\n[00:08.34]b\n[00:08.345]c"
    lyrics = parse_lrc(text)
    assert lyrics.lines[0].time_seconds == pytest.approx(8.30)
    assert lyrics.lines[1].time_seconds == pytest.approx(8.34)
    assert lyrics.lines[2].time_seconds == pytest.approx(8.345)


# Spec: TC-07-01
def test_parse_lrc_skips_headers_and_blanks():
    text = "[ti:thing]\n\n[ar:nobody]\n[00:01.00]hi\n\n"
    lyrics = parse_lrc(text)
    assert len(lyrics.lines) == 1
    assert lyrics.lines[0].text == "hi"


# Spec: TC-07-01
def test_parse_lrc_multiple_stamps_per_line():
    text = "[00:08.34][01:30.10]walking"
    lyrics = parse_lrc(text)
    assert len(lyrics.lines) == 2
    assert lyrics.lines[0].time_seconds == pytest.approx(8.34)
    assert lyrics.lines[0].text == "walking"
    assert lyrics.lines[1].time_seconds == pytest.approx(90.10)
    assert lyrics.lines[1].text == "walking"


def test_parse_lrc_orders_by_time():
    text = "[00:10.00]b\n[00:05.00]a"
    lyrics = parse_lrc(text)
    assert [ln.time_seconds for ln in lyrics.lines] == [5.0, 10.0]


def test_parse_lrc_raises_on_no_timestamps():
    with pytest.raises(LRCParseError):
        parse_lrc("just\nplain\ntext\n")


# Indie-review L1-H2: a file with 1 valid timestamped line and 9 garbage
# lines (no leading timestamp, not a tag header) currently parses
# "successfully", giving the persistence layer no signal to drive the
# `<stem>.lrc.bak` decision (Spec 07 TC-07-10). Raise when the malformed
# ratio exceeds 50% of non-blank/non-header lines.
def test_parse_lrc_raises_on_majority_malformed():
    text = "[00:01.00]hi\n" + "\n".join(["random garbage line"] * 9)
    with pytest.raises(LRCParseError):
        parse_lrc(text)


def test_parse_lrc_tolerates_minority_malformed():
    """8 valid + 2 garbage = 20% < 50% threshold; parses cleanly."""
    text = "\n".join([
        "[00:01.00]a",
        "[00:02.00]b",
        "[00:03.00]c",
        "[00:04.00]d",
        "[00:05.00]e",
        "[00:06.00]f",
        "[00:07.00]g",
        "[00:08.00]h",
        "stage direction garbage",
        "another garbage line",
    ])
    lyrics = parse_lrc(text)
    assert len(lyrics.lines) == 8


# Indie-review L1-H1: parse_lrc should accept a `track_path` kwarg so the
# domain Lyrics returned has its `track_path` field populated without the
# persistence layer having to rebuild a fresh dataclass after the parse.
def test_parse_lrc_threads_track_path():
    from pathlib import Path
    p = Path("/abs/song.mp3")
    lyrics = parse_lrc("[00:01.00]hi", track_path=p)
    assert lyrics.track_path == p


def test_parse_lrc_handles_three_digit_minutes():
    """Some LRCs use 3-digit minute fields for tracks > 99 minutes."""
    text = "[100:00.00]way late"
    lyrics = parse_lrc(text)
    assert lyrics.lines[0].time_seconds == pytest.approx(6000.0)


# Spec: TC-07-02
def test_format_lrc_round_trip():
    lyrics = parse_lrc(SAMPLE_LRC)
    rendered = format_lrc(
        lyrics,
        ti="something more",
        ar="18 Down",
        al="Memoirs of a Sinner",
        length="00:24",
    )
    # Re-parse must yield identical lines
    re_parsed = parse_lrc(rendered)
    assert len(re_parsed.lines) == len(lyrics.lines)
    for a, b in zip(lyrics.lines, re_parsed.lines, strict=True):
        assert a.time_seconds == pytest.approx(b.time_seconds)
        assert a.text == b.text
        assert a.is_section_marker == b.is_section_marker


def test_format_lrc_centisecond_rounding():
    lyrics = Lyrics(lines=(LyricLine(time_seconds=8.345, text="x"),))
    out = format_lrc(lyrics)
    # Half-up: 8.345 → 8.35
    assert "[00:08.35]x" in out


def test_format_lrc_omits_empty_headers():
    lyrics = Lyrics(lines=(LyricLine(time_seconds=0.0, text="hi"),))
    out = format_lrc(lyrics)
    assert "[ti:" not in out
    assert "[ar:" not in out


# Spec: TC-07-03
def test_line_at_boundaries():
    lyrics = parse_lrc("[00:00.00]a\n[00:05.00]b\n[00:10.00]c")
    # before first
    assert line_at(lyrics, -1.0) == -1
    # exactly at first
    assert line_at(lyrics, 0.0) == 0
    # between first and second
    assert line_at(lyrics, 2.5) == 0
    # exactly at second
    assert line_at(lyrics, 5.0) == 1
    # exactly at last
    assert line_at(lyrics, 10.0) == 2
    # after last
    assert line_at(lyrics, 100.0) == 2


def test_line_at_empty_lyrics():
    lyrics = Lyrics(lines=())
    assert line_at(lyrics, 0.0) == -1


# Spec: TC-07-12
def test_lyrics_frozen_and_hashable():
    lyrics = parse_lrc("[00:00.00]a\n[00:05.00]b")
    # Hashable
    assert hash(lyrics) == hash(lyrics)
    # Frozen
    with pytest.raises(FrozenInstanceError):
        lyrics.lines = ()  # type: ignore[misc]


# Spec: TC-07-12
def test_lyric_line_frozen_and_hashable():
    line = LyricLine(time_seconds=1.0, text="x", is_section_marker=False)
    assert hash(line) == hash(line)
    with pytest.raises(FrozenInstanceError):
        line.time_seconds = 2.0  # type: ignore[misc]


def test_lyrics_coerces_iterable_to_tuple():
    lyrics = Lyrics(
        lines=[LyricLine(time_seconds=0.0, text="a")],  # type: ignore[arg-type]
    )
    assert isinstance(lyrics.lines, tuple)
