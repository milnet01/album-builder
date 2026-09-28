"""TC-07-17 - a missing WhisperX runtime is a signal, not a sentence.

MUSI-0370: MainWindow used to decide whether to show the install dialog by
matching English words in the alignment error, so that error could not be
translated. The worker now emits `runtime_missing`, AlignmentService forwards
it with the track path, and MainWindow shows the dialog from that signal
alone - once per session.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.services.alignment_service import AlignmentService
from album_builder.services.alignment_worker import AlignmentWorker


def test_TC_07_17_worker_emits_runtime_missing(qtbot, tmp_path, monkeypatch) -> None:
    # Spec: TC-07-17
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"a")
    worker = AlignmentWorker(audio, "lyrics text")

    def _raise():
        raise ImportError("No module named 'whisperx'")

    monkeypatch.setattr("album_builder.services.alignment_worker._load_whisperx", _raise)
    missing: list[bool] = []
    failures: list[str] = []
    worker.runtime_missing.connect(lambda: missing.append(True))
    worker.failed.connect(failures.append)
    worker.run()
    assert missing == [True]
    assert len(failures) == 1


class _FakeWorker(QObject):
    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)
    runtime_missing = pyqtSignal()
    finished = pyqtSignal()

    def start(self) -> None:
        pass


def test_TC_07_17_service_forwards_runtime_missing_with_path(qapp, tmp_path) -> None:
    # Spec: TC-07-17
    fake = _FakeWorker()
    service = AlignmentService(
        settings=SimpleNamespace(model_size="tiny", auto_align_on_play=False),
        worker_factory=lambda path, text, size: fake,
    )
    track = SimpleNamespace(path=tmp_path / "song.mp3", lyrics_text="la la", duration_seconds=120.0)
    got: list[Path] = []
    service.runtime_missing.connect(got.append)
    service.start_alignment(track)
    fake.runtime_missing.emit()
    assert got == [track.path]


def test_TC_07_17_dialog_follows_the_signal_not_the_text(main_window, monkeypatch) -> None:
    # Spec: TC-07-17
    win = main_window
    shown: list[str] = []
    monkeypatch.setattr(
        "album_builder.ui.main_window.QMessageBox.warning",
        lambda parent, title, text: shown.append(title),
    )
    path = Path("/abs/song.mp3")
    # An error whose words match the old English heuristic no longer opens it.
    win._alignment.error.emit(path, "WhisperX not installed. Install via: x")
    assert shown == []
    win._alignment.runtime_missing.emit(path)
    win._alignment.runtime_missing.emit(path)
    assert len(shown) == 1, "install dialog must appear once per session"
