"""Alignment orchestration — Spec 07.

Owns in-flight `AlignmentWorker` jobs keyed by audio path. Validates
preconditions (lyrics present, audio long enough, LRC not already fresh)
before constructing a worker; emits `status_changed` for the LyricsPanel
status pill. Auto-align is opt-in (Spec 07 §Alignment job, default off).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.lyrics import Lyrics
from album_builder.domain.track import Track
from album_builder.persistence.lrc_io import is_lrc_fresh
from album_builder.persistence.settings import AlignmentSettings, read_alignment
from album_builder.services.alignment_status import AlignmentStatus
from album_builder.services.alignment_worker import AlignmentWorker

logger = logging.getLogger(__name__)


# Spec 07 §Errors: audio shorter than ~2 s is rejected — not enough signal
# for forced alignment to converge.
MIN_AUDIO_SECONDS = 2.0


# Spec 07 §Alignment job: WhisperX caches the two halves of the pipeline
# in two different places. faster-whisper goes to HuggingFace Hub
# (~/.cache/huggingface/hub). The default English alignment model is a
# torchaudio bundle (WAV2VEC2_ASR_BASE_960H) — that one downloads as a
# raw .pth into ~/.cache/torch/hub/checkpoints/. Per the spec ("a one-
# shot dialog explains size and asks for confirmation"), the dialog
# should fire only when the cache is missing — once the ~1 GB download
# has happened, alignment runs silently.
HF_HUB_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
TORCH_HUB_CHECKPOINTS = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"

# torchaudio names the file after the underlying fairseq checkpoint, not
# after the bundle constant. WhisperX picks WAV2VEC2_ASR_BASE_960H for
# English by default (whisperx/alignment.py: DEFAULT_ALIGN_MODELS_TORCH).
TORCHAUDIO_WAV2VEC_EN_BASE = "wav2vec2_fairseq_base_ls960_asr_ls960.pth"


def whisperx_models_cached(model_size: str) -> bool:
    """Best-effort check that WhisperX's required models are already cached
    locally. Used by the UI to suppress the download-confirm dialog on
    subsequent alignments.

    Conservative: requires BOTH the faster-whisper transcription model
    (HF Hub) AND the default English wav2vec2 alignment model (torch
    hub). If either is missing, returns False.

    For non-English audio, WhisperX selects a different alignment model
    at runtime based on detected language — many of those go to HF Hub
    instead of torch hub. We cannot know which path applies ahead of the
    transcription step, so a partial false-positive is possible (English
    models cached; a Russian song still triggers a fresh ~300 MB
    wav2vec2-large download silently). Acceptable: the user already
    opted in on the first dialog, and the secondary model is much
    smaller than the headline 1 GB.
    """
    whisper_dir = HF_HUB_CACHE / f"models--Systran--faster-whisper-{model_size}"
    wav2vec_pth = TORCH_HUB_CHECKPOINTS / TORCHAUDIO_WAV2VEC_EN_BASE
    return whisper_dir.is_dir() and wav2vec_pth.is_file()


WorkerFactory = Callable[[Path, str, str], AlignmentWorker]


def _default_worker_factory(track_path: Path, lyrics_text: str, model_size: str) -> AlignmentWorker:
    return AlignmentWorker(track_path, lyrics_text, model_size)


class AlignmentService(QObject):
    """Construct and supervise alignment workers for tracks on demand."""

    status_changed = pyqtSignal(object, object)  # Type: (Path, AlignmentStatus)
    progress = pyqtSignal(object, int)           # Type: (Path, percent 0..100)
    lyrics_ready = pyqtSignal(object, object)    # Type: (Path, Lyrics)
    error = pyqtSignal(object, str)              # Type: (Path, message)

    def __init__(
        self,
        settings: AlignmentSettings | None = None,
        worker_factory: WorkerFactory | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        # Settings are passed in for testability; fall back to disk on first
        # construction for the production wiring.
        self._settings = settings if settings is not None else read_alignment()
        self._worker_factory = worker_factory or _default_worker_factory
        self._workers: dict[Path, AlignmentWorker] = {}

    def settings(self) -> AlignmentSettings:
        return self._settings

    @property
    def model_size(self) -> str:
        """Configured WhisperX model identifier (e.g. 'medium.en'). Exposed
        so the UI can pass it to `whisperx_models_cached()` without
        reaching into private settings state."""
        return self._settings.model_size

    def update_settings(self, settings: AlignmentSettings) -> None:
        self._settings = settings

    def is_running(self, track_path: Path) -> bool:
        return track_path in self._workers

    def start_alignment(self, track: Track) -> None:
        """Spawn a worker for `track`, subject to the precondition checks.

        Each rejection emits the corresponding `status_changed` so the
        LyricsPanel can update its pill text.
        """
        path = track.path
        if not track.lyrics_text or not track.lyrics_text.strip():
            self.status_changed.emit(path, AlignmentStatus.NO_LYRICS_TEXT)
            return
        if is_lrc_fresh(path):
            self.status_changed.emit(path, AlignmentStatus.READY)
            return
        if track.duration_seconds < MIN_AUDIO_SECONDS:
            self.status_changed.emit(path, AlignmentStatus.AUDIO_TOO_SHORT)
            return
        if path in self._workers:
            # Idempotent — already running for this path.
            return

        worker = self._worker_factory(path, track.lyrics_text, self._settings.model_size)
        self._workers[path] = worker
        worker.progress.connect(lambda p, _path=path: self.progress.emit(_path, p))
        worker.finished_ok.connect(lambda lyrics, _path=path: self._on_finished(_path, lyrics))
        worker.failed.connect(lambda msg, _path=path: self._on_failed(_path, msg))
        # Cleanup hook: drop the worker reference when the thread ends.
        worker.finished.connect(lambda _path=path: self._workers.pop(_path, None))

        self.status_changed.emit(path, AlignmentStatus.ALIGNING)
        worker.start()

    def auto_align_on_play(self, track: Track) -> None:
        """Honour `alignment.auto_align_on_play` from settings.

        Default is False (Spec 07: alignment is opt-in). Tests pin this
        via TC-07-13 — passing a track here with default settings must
        not start a worker.
        """
        if not self._settings.auto_align_on_play:
            return
        self.start_alignment(track)

    def cancel(self, track_path: Path) -> None:
        worker = self._workers.get(track_path)
        if worker is None:
            return
        worker.requestInterruption()
        # The worker exits via _AlignmentInterrupted without firing
        # finished_ok or failed, so the LyricsPanel's status pill would
        # otherwise remain stuck at ALIGNING. Spec 07 §Errors mandates
        # "status reverts to `not yet aligned`." L4-M5.
        self.status_changed.emit(track_path, AlignmentStatus.NOT_YET_ALIGNED)

    # ---- Internal ----------------------------------------------------

    def _on_finished(self, path: Path, lyrics: Lyrics) -> None:
        self.status_changed.emit(path, AlignmentStatus.READY)
        self.lyrics_ready.emit(path, lyrics)

    def _on_failed(self, path: Path, msg: str) -> None:
        logger.warning("Alignment failed for %s: %s", path, msg)
        self.status_changed.emit(path, AlignmentStatus.FAILED)
        self.error.emit(path, msg)
