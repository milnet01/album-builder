"""Spec 07 TC-07-18 / TC-07-19: lyric lines are timed by matching the
user's lyric WORDS to the words WhisperX heard, not by pairing lines with
transcript segments by position (MUSI-0404). Pure logic, no Qt, no model."""

from __future__ import annotations

import pytest

from album_builder.domain.lyric_timing import NothingHeard, heard_words, line_start_times


def _heard(*pairs):
    return [(w, t) for w, t in pairs]


# Spec: TC-07-18 - two sung lines merged into one transcript segment still
# get their own start times (index pairing put line 2 at segment 2).
def test_merged_segment_still_times_each_line() -> None:
    lines = ["walking the line", "feeling the weight", "searching for more"]
    heard = _heard(("walking", 1.0), ("the", 1.3), ("line", 1.6),
                   ("feeling", 4.5), ("the", 4.8), ("weight", 5.1),
                   ("searching", 8.0), ("for", 8.4), ("more", 8.7))
    assert line_start_times(lines, heard, end_time=11.0) == pytest.approx([1.0, 4.5, 8.0])


# Spec: TC-07-18 - case and punctuation do not matter; a misheard word
# inside a line does not lose the line.
def test_case_punctuation_and_misheard_words() -> None:
    lines = ["Hello, World!", "Don't stop now"]
    heard = _heard(("hello", 2.0), ("word", 2.4), ("dont", 6.0), ("stop", 6.3), ("now", 6.6))
    assert line_start_times(lines, heard, end_time=9.0) == pytest.approx([2.0, 6.0])


# Spec: TC-07-18 - a line whose words were not heard sits between its
# neighbours; trailing unheard lines go to the end time (Spec 07 §Errors).
def test_unheard_lines_are_spaced_and_trailing_lines_go_to_the_end() -> None:
    lines = ["one two", "la la la", "three four", "never sung"]
    heard = _heard(("one", 1.0), ("two", 1.5), ("three", 5.0), ("four", 5.5))
    times = line_start_times(lines, heard, end_time=20.0)
    assert times[0] == pytest.approx(1.0)
    assert 1.0 < times[1] < 5.0
    assert times[2] == pytest.approx(5.0)
    assert times[3] == pytest.approx(20.0)


# Spec: TC-07-18 - times never run backwards, even if a chorus repeat makes
# the matcher pick an earlier occurrence.
def test_times_never_decrease() -> None:
    lines = ["la la", "chorus words", "la la", "chorus words"]
    heard = _heard(("chorus", 3.0), ("words", 3.4), ("chorus", 9.0), ("words", 9.4))
    times = line_start_times(lines, heard, end_time=12.0)
    assert times == sorted(times)


# Spec: TC-07-19 - nothing heard at all is a failure, not a "ready" with
# every line at 0:00 (review LY-A3).
def test_nothing_heard_raises() -> None:
    with pytest.raises(NothingHeard):
        line_start_times(["a line"], [], end_time=5.0)


# Spec: TC-07-18 - words come from WhisperX's per-word timings; a segment
# without word timings spreads its text across its own start..end; a word
# without a start keeps its place with no time; a missing `end` is fine.
def test_heard_words_from_aligned_result() -> None:
    aligned = {"segments": [
        {"start": 1.0, "end": 2.0, "words": [
            {"word": "Hello,", "start": 1.0, "end": 1.4},
            {"word": "2026", "end": 1.8},
        ]},
        {"start": 4.0, "end": 6.0, "text": " big sky "},
        {"start": 7.0, "text": "end"},
    ]}
    words, end = heard_words(aligned)
    assert words == [("hello", 1.0), ("2026", None), ("big", 4.0), ("sky", 5.0), ("end", 7.0)]
    assert end == pytest.approx(7.0)
