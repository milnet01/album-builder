"""Alignment worker — Spec 07 §Alignment job.

Lazily imports WhisperX inside `run()` so the rest of the app starts
without a ~3 GB PyTorch dependency in the venv. WhisperX is an optional
runtime dep — if it's missing, the worker emits `failed(...)` with an
install hint and the controller surfaces that to the user.

The worker writes the LRC file to `<audio>.lrc` only on a fully
successful alignment. A killed / interrupted worker leaves no `.lrc`
behind, so re-running is idempotent (Spec 07 TC-07-08).
"""

from __future__ import annotations

import gc
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from album_builder.domain.lyric_timing import NothingHeard, heard_words, line_start_times
from album_builder.domain.lyrics import LyricLine, Lyrics
from album_builder.i18n import tr
from album_builder.persistence.lrc_io import write_lrc

logger = logging.getLogger(__name__)


class AlignmentWorker(QThread):
    """QThread that produces a `Lyrics` from `(audio, lyrics_text)` by
    matching the lyric words to the words WhisperX hears, writes the
    sibling LRC, and emits one of `finished_ok` / `failed` exactly once."""

    progress = pyqtSignal(int)         # 0..100
    finished_ok = pyqtSignal(object)   # Type: Lyrics
    failed = pyqtSignal(str)
    # WhisperX is not installed. Emitted before `failed`, so the UI decides
    # on the install dialog from this state, never from the message text,
    # which is translated (TC-07-17).
    runtime_missing = pyqtSignal()

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
        except NothingHeard:
            logger.info("AlignmentWorker: no words heard in %s", self._track_path)
            self.failed.emit(tr(
                "No singing was heard in this song, so the lyrics could not be timed."
            ))
            return
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
            self.runtime_missing.emit()
            self.failed.emit(tr(
                "WhisperX not installed. Install via: {command}",
                command=f"{sys.executable} -m pip install whisperx",
            ))
            return
        except Exception as exc:  # pragma: no cover — covered by integration tier
            logger.exception("AlignmentWorker failed for %s", self._track_path)
            self.failed.emit(str(exc))
            return
        if self.isInterruptionRequested():
            return  # cancelled during the last step: write nothing (LY-A6)
        try:
            write_lrc(self._track_path, lyrics)
        except OSError as exc:
            logger.warning("Could not write LRC for %s: %s", self._track_path, exc)
            self.failed.emit(tr("could not write LRC: {error}", error=exc))
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

        aligned = self._transcribe_and_align(whisperx)
        return _timed_lyrics(self._lyrics_text, aligned, self._track_path)

    def _transcribe_and_align(self, whisperx) -> dict:
        """Hear the song and time each word heard. Both models are dropped
        and collected before returning, success or not, so a song's ~1 GB
        is not held while the next one waits (owner decision 2026-11-05)."""
        model = align_model = audio = None
        try:
            # Stage 1: transcription via faster-whisper
            self.progress.emit(5)
            device = "cpu"  # Spec 07: CUDA optional; CPU is the default budget
            model = whisperx.load_model(self._model_size, device, compute_type="int8")
            self._check_interrupted()

            audio = whisperx.load_audio(str(self._track_path))
            self.progress.emit(20)

            result = model.transcribe(audio, batch_size=8)
            self._check_interrupted()
            self.progress.emit(50)

            # Stage 2: wav2vec2 times each heard word
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
            return aligned
        finally:
            model = align_model = audio = None
            gc.collect()

    def _check_interrupted(self) -> None:
        if self.isInterruptionRequested():
            raise _AlignmentInterrupted


def _load_whisperx():
    """Module-level factory so tests can monkey-patch it without touching a
    real `import whisperx`."""
    import whisperx  # type: ignore[import-not-found]  # optional runtime dep

    return whisperx


def _timed_lyrics(lyrics_text: str, aligned_result: dict, track_path: Path) -> Lyrics:
    """The user's non-blank lyric lines, each timed by matching its words
    to the words heard (Spec 07 TC-07-18). Raises NothingHeard."""
    raw_lines = [ln.rstrip() for ln in lyrics_text.splitlines() if ln.strip()]
    if not raw_lines:
        return Lyrics(track_path=track_path)
    heard, end_time = heard_words(aligned_result)
    starts = line_start_times(raw_lines, heard, end_time=end_time)
    lines = tuple(
        LyricLine(time_seconds=t, text=text) for t, text in zip(starts, raw_lines, strict=True)
    )
    return Lyrics(lines=lines, track_path=track_path)


class _AlignmentInterrupted(Exception):
    """Internal sentinel — the worker was cancelled mid-run."""
