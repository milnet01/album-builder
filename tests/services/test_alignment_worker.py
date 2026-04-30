"""AlignmentWorker tests — Spec 07.

Only the pure-Python helpers are unit-tested here; the WhisperX-driven
`run()` path needs ~1 GB of model downloads and is exercised behind the
`AB_INTEGRATION_LYRICS=1` integration tier (paralleling Phase 3A's
`AB_INTEGRATION_AUDIO` gate).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from album_builder.domain.lyrics import Lyrics
from album_builder.services.alignment_worker import (
    AlignmentWorker,
    _segments_to_lyrics,
)


def test_segments_to_lyrics_pairs_lines_with_segment_starts(tmp_path):
    text = "walking the line\nfeeling the weight\nsearching for more"
    aligned = {
        "segments": [
            {"start": 1.0, "end": 4.0},
            {"start": 4.5, "end": 7.5},
            {"start": 8.0, "end": 11.0},
        ]
    }
    lyrics = _segments_to_lyrics(text, aligned, tmp_path / "song.mpeg")
    assert isinstance(lyrics, Lyrics)
    assert len(lyrics.lines) == 3
    assert lyrics.lines[0].time_seconds == pytest.approx(1.0)
    assert lyrics.lines[0].text == "walking the line"
    assert lyrics.lines[2].time_seconds == pytest.approx(8.0)


def test_segments_to_lyrics_skips_blank_input_lines(tmp_path):
    text = "\nwalking the line\n\n"
    aligned = {"segments": [{"start": 1.0, "end": 4.0}]}
    lyrics = _segments_to_lyrics(text, aligned, tmp_path / "song.mpeg")
    assert len(lyrics.lines) == 1
    assert lyrics.lines[0].text == "walking the line"


def test_segments_to_lyrics_pads_trailing_lines_to_last_end(tmp_path):
    """If alignment "ran out of audio" before all lyric lines, trailing lines
    fall back to the last segment's end time. Spec 07 §Errors row 5."""
    text = "a\nb\nc"
    aligned = {"segments": [{"start": 1.0, "end": 4.0}]}
    lyrics = _segments_to_lyrics(text, aligned, tmp_path / "song.mpeg")
    assert lyrics.lines[0].time_seconds == pytest.approx(1.0)
    assert lyrics.lines[1].time_seconds == pytest.approx(4.0)
    assert lyrics.lines[2].time_seconds == pytest.approx(4.0)


def test_segments_to_lyrics_handles_no_segments(tmp_path):
    """Edge case: WhisperX returned no segments (silent audio?)."""
    text = "a\nb"
    aligned = {"segments": []}
    lyrics = _segments_to_lyrics(text, aligned, tmp_path / "song.mpeg")
    assert lyrics.lines[0].time_seconds == 0.0
    assert lyrics.lines[1].time_seconds == 0.0


# Indie-review L4-M2: a malformed alignment payload may have a final
# segment without an `end` key. `.get("end", 0.0)` is the safe access;
# bracket-access raised KeyError that crashed the worker right at the
# end of an otherwise-successful alignment.
def test_segments_to_lyrics_tolerates_missing_end_on_last_segment(tmp_path):
    text = "a\nb\nc"
    aligned = {"segments": [{"start": 1.0}]}  # no `end` key
    lyrics = _segments_to_lyrics(text, aligned, tmp_path / "song.mpeg")
    assert lyrics.lines[0].time_seconds == pytest.approx(1.0)
    # Trailing lines fall back to last-segment-end which is 0.0 in this
    # malformed case rather than raising KeyError.
    assert lyrics.lines[1].time_seconds == pytest.approx(0.0)
    assert lyrics.lines[2].time_seconds == pytest.approx(0.0)


# Indie-review L4-M1: when segment count != lyric line count, the
# silent mis-pairing is a debugging trap. Log an INFO message so the
# user sees a record of why their LRC has fewer/more lines than expected.
def test_segments_to_lyrics_logs_count_mismatch(tmp_path, caplog):
    import logging as _logging

    text = "a\nb\nc"
    aligned = {"segments": [{"start": 1.0, "end": 4.0}]}
    with caplog.at_level(_logging.INFO, logger="album_builder.services.alignment_worker"):
        _segments_to_lyrics(text, aligned, tmp_path / "song.mpeg")
    assert any(
        "segment" in rec.message.lower() and "line" in rec.message.lower()
        for rec in caplog.records
    ), f"expected segment/line mismatch log; got {[r.message for r in caplog.records]}"


def test_segments_to_lyrics_no_log_when_counts_match(tmp_path, caplog):
    import logging as _logging

    text = "a\nb"
    aligned = {"segments": [{"start": 1.0, "end": 4.0}, {"start": 4.5, "end": 7.0}]}
    with caplog.at_level(_logging.INFO, logger="album_builder.services.alignment_worker"):
        _segments_to_lyrics(text, aligned, tmp_path / "song.mpeg")
    # No mismatch -> no log.
    assert not any(
        "mismatch" in rec.message.lower() for rec in caplog.records
    )


def test_segments_to_lyrics_empty_text_returns_empty_lyrics(tmp_path):
    lyrics = _segments_to_lyrics("", {"segments": [{"start": 0.0, "end": 1.0}]},
                                 tmp_path / "song.mpeg")
    assert lyrics.lines == ()


# Spec: L4-L5 (Tier 1 indie-review 2026-04-30)
def test_worker_emits_install_hint_when_whisperx_missing(qtbot, tmp_path, monkeypatch):
    """When whisperx isn't installed, run() must emit a copy/paste-able
    install hint — not the bare 'No module named whisperx' the generic
    Exception branch would produce. The Phase 3B plan specified this exact
    hint string ('pip install whisperx')."""
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    worker = AlignmentWorker(audio, "lyrics text")

    def _raise():
        raise ImportError("No module named 'whisperx'")

    monkeypatch.setattr(
        "album_builder.services.alignment_worker._load_whisperx", _raise
    )
    failures: list[str] = []
    worker.failed.connect(failures.append)
    worker.run()  # synchronous — call directly so qtbot can observe state
    assert len(failures) == 1
    assert "WhisperX not installed" in failures[0]
    assert "pip install whisperx" in failures[0]
    # The bare ImportError text must NOT have leaked through.
    assert "No module named" not in failures[0]


# Note: the live cancel-mid-flight path (TC-07-08) is covered by
# test_alignment_service.py::test_cancel_no_lrc_written via a FakeWorker.
# QThread.isInterruptionRequested() only returns True for a thread that has
# actually been started; calling worker.run() synchronously from the test
# main thread bypasses that machinery, so a per-worker pre-start cancel
# test would be testing the test harness, not the production code.


# Lyrics integration tier — only runs when explicitly enabled, on machines
# with whisperx + a real model cached. Mirrors Phase 3A's audio integration
# tier shape.
INTEGRATION = pytest.mark.skipif(
    os.environ.get("AB_INTEGRATION_LYRICS") != "1",
    reason="Set AB_INTEGRATION_LYRICS=1 to run lyrics-pipeline integration tests",
)


@INTEGRATION
def test_worker_real_whisperx_short_silence_does_not_crash(qtbot, tmp_path):
    """End-to-end smoke: 1 s of silence → worker either fails gracefully or
    produces an empty Lyrics. Either is acceptable; a crash is not."""
    pytest.importorskip("whisperx")
    import wave

    audio = tmp_path / "silent.wav"
    with wave.open(str(audio), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)  # 1 s silence

    worker = AlignmentWorker(Path(audio), "anything")
    seen_done = []
    seen_failed = []
    worker.finished_ok.connect(seen_done.append)
    worker.failed.connect(seen_failed.append)
    worker.run()
    assert seen_done or seen_failed
