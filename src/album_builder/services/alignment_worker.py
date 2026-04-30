"""Forced-alignment worker — Spec 07 §Alignment job.

Lazily imports WhisperX inside `run()` so the rest of the app starts
without a ~3 GB PyTorch dependency in the venv. WhisperX is an optional
runtime dep — if it's missing, the worker emits `failed(...)` with an
install hint and the controller surfaces that to the user.

The worker writes the LRC file to `<audio>.lrc` only on a fully
successful alignment. A killed / interrupted worker leaves no `.lrc`
behind, so re-running is idempotent (Spec 07 TC-07-08).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from album_builder.domain.lyrics import LyricLine, Lyrics
from album_builder.persistence.lrc_io import write_lrc

logger = logging.getLogger(__name__)


class AlignmentWorker(QThread):
    """QThread that produces a `Lyrics` from `(audio, lyrics_text)` via
    WhisperX forced alignment, writes the sibling LRC, and emits one of
    `finished_ok` / `failed` exactly once."""

    progress = pyqtSignal(int)         # 0..100
    finished_ok = pyqtSignal(object)   # Type: Lyrics
    failed = pyqtSignal(str)

    def __init__(
        self,
        track_path: Path,
        lyrics_text: str,
        model_size: str = "medium.en",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._track_path = Path(track_path)
        self._lyrics_text = lyrics_text
        self._model_size = model_size

    def run(self) -> None:
        try:
            lyrics = self._do_alignment()
        except _AlignmentInterrupted:
            # Cancellation path — clean exit, no `.lrc`, no failed signal
            # (the controller treats cancellation as "back to NOT_YET_ALIGNED").
            return
        except ImportError:
            # WhisperX is an optional runtime dep; surface the install hint
            # the user can copy/paste rather than the bare "No module named
            # 'whisperx'" the generic Exception branch would produce. L4-L5.
            # The hint anchors at `sys.executable -m pip install` so the
            # install lands in the SAME interpreter the worker is running
            # in — bare `pip install` would target whatever pip is on PATH
            # (typically system Python on PEP 668 distros), missing the
            # app's venv entirely.
            logger.warning(
                "AlignmentWorker: whisperx not installed for %s", self._track_path,
            )
            self.failed.emit(
                f"WhisperX not installed. Install via: "
                f"{sys.executable} -m pip install whisperx"
            )
            return
        except Exception as exc:  # pragma: no cover — covered by integration tier
            logger.exception("AlignmentWorker failed for %s", self._track_path)
            self.failed.emit(str(exc))
            return
        try:
            write_lrc(self._track_path, lyrics)
        except OSError as exc:
            logger.warning("Could not write LRC for %s: %s", self._track_path, exc)
            self.failed.emit(f"could not write LRC: {exc}")
            return
        self.finished_ok.emit(lyrics)

    # ---- Internal ----------------------------------------------------

    def _do_alignment(self) -> Lyrics:
        # Honour the interruption flag BEFORE any expensive import or model
        # download — a controller that calls cancel() before run() ever
        # reached must see no work happen at all (TC-07-08).
        self._check_interrupted()
        # L4-H1-real: a cancel() that races with the very first run()
        # instruction can fire AFTER the pre-import check but BEFORE the
        # post-import check. Wrap the import in try/finally so the post
        # check runs even if the import itself raised — which lets the
        # cancel surface as _AlignmentInterrupted rather than as an
        # ImportError-shaped failed.emit on a torn-down worker.
        try:
            whisperx = _load_whisperx()  # raises ImportError if not installed
        finally:
            self._check_interrupted()

        # Stage 1: free transcription via faster-whisper to get segment timing
        self.progress.emit(5)
        device = "cpu"  # Spec 07: CUDA optional; CPU is the default budget
        compute_type = "int8"
        model = whisperx.load_model(self._model_size, device, compute_type=compute_type)
        self._check_interrupted()

        audio = whisperx.load_audio(str(self._track_path))
        self.progress.emit(20)

        result = model.transcribe(audio, batch_size=8)
        self._check_interrupted()
        self.progress.emit(50)

        # Stage 2: wav2vec2 forced alignment of the known plain text against
        # the segment-level timing
        align_model, metadata = whisperx.load_align_model(
            language_code=result.get("language", "en"), device=device
        )
        self._check_interrupted()
        self.progress.emit(70)

        aligned = whisperx.align(
            result["segments"], align_model, metadata, audio, device,
            return_char_alignments=False,
        )
        self.progress.emit(90)

        return _segments_to_lyrics(self._lyrics_text, aligned, self._track_path)

    def _check_interrupted(self) -> None:
        if self.isInterruptionRequested():
            raise _AlignmentInterrupted


def _load_whisperx():
    """Module-level factory so tests can monkey-patch it without touching a
    real `import whisperx`."""
    import whisperx  # type: ignore[import-not-found]  # optional runtime dep

    return whisperx


def _segments_to_lyrics(lyrics_text: str, aligned_result: dict, track_path: Path) -> Lyrics:
    """Map WhisperX alignment output back to the user's plain lyrics text.

    `aligned_result["segments"]` is an ordered list of segments with
    `start`/`end` keys. We split the user's lyrics on newlines, drop empty
    lines, and pair each non-empty line with the start time of the
    matching segment by index. If WhisperX returned fewer segments than
    lyric lines (alignment "ran out of audio"), trailing lines get the
    last segment's end time.
    """
    segments = aligned_result.get("segments") or []
    raw_lines = [ln.rstrip() for ln in lyrics_text.splitlines() if ln.strip()]
    if not raw_lines:
        return Lyrics(track_path=track_path)
    # L4-M2: malformed alignment payloads may omit `end` on the last
    # segment; `.get` keeps the fallback robust instead of KeyError'ing
    # at the end of an otherwise-successful alignment.
    fallback_end = float(segments[-1].get("end", 0.0)) if segments else 0.0
    # L4-M1: silent mis-pairing on count mismatch is a debugging trap;
    # log a single INFO line so the user can correlate "fewer LRC lines
    # than I expected" with the actual segment count.
    if len(segments) != len(raw_lines):
        logger.info(
            "alignment count mismatch: %d segment(s) vs %d lyric line(s) for %s; "
            "trailing lines pinned to last-segment end (%.3fs)",
            len(segments), len(raw_lines), track_path, fallback_end,
        )
    lines: list[LyricLine] = []
    for i, text in enumerate(raw_lines):
        if i < len(segments):
            start = float(segments[i].get("start", 0.0))
        else:
            start = fallback_end
        lines.append(LyricLine(time_seconds=start, text=text))
    return Lyrics(lines=tuple(lines), track_path=track_path)


class _AlignmentInterrupted(Exception):
    """Internal sentinel — the worker was cancelled mid-run."""
