"""AlignmentWorker tests — Spec 07.

Only the pure-Python helpers are unit-tested here; the WhisperX-driven
`run()` path needs ~1 GB of model downloads and is exercised behind the
`AB_INTEGRATION_LYRICS=1` integration tier (paralleling Phase 3A's
`AB_INTEGRATION_AUDIO` gate).
"""

from __future__ import annotations

import os
import weakref
from pathlib import Path

import pytest
from PyQt6.QtCore import QCoreApplication

from album_builder.domain.lyrics import Lyrics
from album_builder.services.alignment_worker import AlignmentWorker


class _FakeModel:
    """Stands in for a WhisperX model. The self-reference makes a cycle, as
    real torch models have, so only a garbage collection frees it."""

    def __init__(self) -> None:
        self.me = self

    def transcribe(self, audio, batch_size):
        return {"segments": [], "language": "en"}


class _FakeWhisperX:
    """The four WhisperX calls the worker makes; `align` returns `aligned`."""

    def __init__(self, aligned: dict) -> None:
        self.aligned = aligned
        self.models: list[weakref.ref] = []

    def _model(self) -> _FakeModel:
        m = _FakeModel()
        self.models.append(weakref.ref(m))
        return m

    def load_model(self, size, device, compute_type):
        return self._model()

    def load_audio(self, path):
        return [0.0]

    def load_align_model(self, language_code, device):
        return self._model(), {}

    def align(self, segments, model, metadata, audio, device, return_char_alignments):
        return self.aligned


def _run_worker(monkeypatch, tmp_path, text: str, aligned: dict):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    fake = _FakeWhisperX(aligned)
    monkeypatch.setattr(
        "album_builder.services.alignment_worker._load_whisperx", lambda: fake,
    )
    worker = AlignmentWorker(audio, text)
    done: list[Lyrics] = []
    failures: list[str] = []
    worker.finished_ok.connect(done.append)
    worker.failed.connect(failures.append)
    worker.run()
    return audio, fake, done, failures


# Spec: TC-07-18 - the worker times each line from the heard words, so a
# transcript segment holding two sung lines no longer shifts later lines.
def test_worker_times_lines_from_heard_words(qtbot, tmp_path, monkeypatch):
    aligned = {"segments": [
        {"start": 1.0, "end": 6.0, "words": [
            {"word": "walking", "start": 1.0, "end": 1.3},
            {"word": "the", "start": 1.3, "end": 1.5},
            {"word": "line", "start": 1.5, "end": 2.0},
            {"word": "feeling", "start": 4.5, "end": 4.8},
            {"word": "the", "start": 4.8, "end": 5.0},
            {"word": "weight", "start": 5.0, "end": 6.0},
        ]},
        {"start": 8.0, "end": 9.0, "words": [
            {"word": "more", "start": 8.0, "end": 9.0},
        ]},
    ]}
    text = "walking the line\n\nfeeling the weight\nsearching for more"
    audio, _fake, done, failures = _run_worker(monkeypatch, tmp_path, text, aligned)
    assert failures == []
    assert [ln.text for ln in done[0].lines] == [
        "walking the line", "feeling the weight", "searching for more",
    ]
    assert [ln.time_seconds for ln in done[0].lines] == pytest.approx([1.0, 4.5, 8.0])
    assert audio.with_suffix(".lrc").exists()


# Spec: TC-07-19 - nothing heard is a failure, not READY with every line at 0:00.
def test_worker_fails_when_nothing_heard(qtbot, tmp_path, monkeypatch):
    audio, _fake, done, failures = _run_worker(
        monkeypatch, tmp_path, "a\nb", {"segments": []},
    )
    assert done == []
    assert len(failures) == 1
    assert not audio.with_suffix(".lrc").exists()


# Spec: TC-07-19 - both models are freed once the song is done (owner
# decision 2026-11-05: free the memory after each song).
def test_worker_frees_models_after_use(qtbot, tmp_path, monkeypatch):
    aligned = {"segments": [{"start": 1.0, "end": 2.0, "text": "a"}]}
    _audio, fake, done, _failures = _run_worker(monkeypatch, tmp_path, "a", aligned)
    assert done
    assert len(fake.models) == 2
    assert all(ref() is None for ref in fake.models)


# Spec: TC-07-08 - a cancel during the last step leaves no `.lrc` (LY-A6).
# The thread must really run: QThread.start() clears an interruption
# requested before it, so the request is made from inside run().
def test_cancel_during_last_step_writes_no_lrc(qtbot, tmp_path, monkeypatch):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    aligned = {"segments": [{"start": 1.0, "end": 2.0, "text": "a"}]}
    fake = _FakeWhisperX(aligned)
    worker = AlignmentWorker(audio, "a")
    real_align = fake.align

    def align_then_cancel(*args, **kwargs):
        worker.requestInterruption()
        return real_align(*args, **kwargs)

    fake.align = align_then_cancel
    monkeypatch.setattr(
        "album_builder.services.alignment_worker._load_whisperx", lambda: fake,
    )
    done: list = []
    worker.finished_ok.connect(done.append)
    worker.start()
    assert worker.wait(5000)
    QCoreApplication.processEvents()
    assert done == []
    assert not audio.with_suffix(".lrc").exists()


# Spec: L4-L5 (Tier 1 indie-review 2026-04-30)
def test_worker_emits_install_hint_when_whisperx_missing(qtbot, tmp_path, monkeypatch):
    """When whisperx isn't installed, run() must emit a copy/paste-able
    install hint that anchors at the running interpreter's pip — bare
    `pip install` would target whatever pip is on PATH (typically the
    system Python on PEP 668 distros), which doesn't help when the app
    runs from its own venv."""
    import sys as _sys

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
    # The hint must use `<sys.executable> -m pip install whisperx` so it
    # lands in the running interpreter's site-packages, not the bare
    # `pip install whisperx` that would silently target system Python.
    assert f"{_sys.executable} -m pip install whisperx" in failures[0]
    # The bare ImportError text must NOT have leaked through.
    assert "No module named" not in failures[0]


# Spec: TC-07-09 — generic runtime exception path
def test_worker_emits_failure_on_unexpected_runtime_error(qtbot, tmp_path, monkeypatch):
    """If a non-ImportError exception escapes the alignment pipeline (e.g.
    GPU OOM, torch device error), the worker must convert it into a
    `failed` signal rather than crashing the QThread."""
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    worker = AlignmentWorker(audio, "lyrics text")

    def _boom():
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(
        "album_builder.services.alignment_worker._load_whisperx", _boom,
    )
    failures: list[str] = []
    worker.failed.connect(failures.append)
    worker.run()
    assert len(failures) == 1
    assert "CUDA out of memory" in failures[0]


# Note: QThread.isInterruptionRequested() only returns True for a thread
# that is running, so a cancel test must start the thread and request the
# interruption from inside run() (test_cancel_during_last_step_writes_no_lrc).
# A pre-start cancel cannot be tested: start() clears it.


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
