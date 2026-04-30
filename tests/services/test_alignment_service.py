"""AlignmentService tests — Spec 07."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from album_builder.domain.lyrics import LyricLine, Lyrics
from album_builder.domain.track import Track
from album_builder.persistence.settings import AlignmentSettings
from album_builder.services.alignment_service import AlignmentService
from album_builder.services.alignment_status import AlignmentStatus


class FakeWorker(QThread):
    """Stand-in for `AlignmentWorker` — same signal shape; never imports
    whisperx. Tests inject this via the AlignmentService worker_factory."""

    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, track_path: Path, lyrics_text: str, model_size: str = "medium.en"):
        super().__init__()
        self.track_path = track_path
        self.lyrics_text = lyrics_text
        self.model_size = model_size
        self.behavior = "succeed"  # or "fail" / "interrupt"

    def run(self) -> None:
        if self.isInterruptionRequested() or self.behavior == "interrupt":
            return
        if self.behavior == "fail":
            self.failed.emit("synthetic failure")
            return
        self.progress.emit(50)
        lyrics = Lyrics(
            lines=(
                LyricLine(time_seconds=0.0, text=self.lyrics_text.splitlines()[0]),
            ),
            track_path=self.track_path,
        )
        self.finished_ok.emit(lyrics)


def _make_track(path: Path, lyrics: str | None, duration: float = 180.0) -> Track:
    return Track(
        path=path,
        title="t", album="a", artist="x",
        album_artist="x", composer="", comment="",
        lyrics_text=lyrics,
        cover_data=None, cover_mime=None,
        duration_seconds=duration,
        file_size_bytes=1024,
        is_missing=False,
    )


def _service(tmp_path: Path, settings: AlignmentSettings | None = None) -> AlignmentService:
    factory = lambda p, t, m: FakeWorker(p, t, m)  # noqa: E731
    return AlignmentService(
        settings=settings or AlignmentSettings(),
        worker_factory=factory,
    )


# Spec: TC-07-06
def test_start_alignment_rejects_empty_lyrics(qtbot, tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    service = _service(tmp_path)
    statuses: list = []
    service.status_changed.connect(lambda p, s: statuses.append((p, s)))
    track = _make_track(audio, lyrics=None)
    service.start_alignment(track)
    assert statuses == [(audio, AlignmentStatus.NO_LYRICS_TEXT)]
    assert not service.is_running(audio)


# Spec: TC-07-07
def test_start_alignment_rejects_short_audio(qtbot, tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    service = _service(tmp_path)
    statuses: list = []
    service.status_changed.connect(lambda p, s: statuses.append((p, s)))
    track = _make_track(audio, lyrics="hi", duration=1.5)
    service.start_alignment(track)
    assert (audio, AlignmentStatus.AUDIO_TOO_SHORT) in statuses
    assert not service.is_running(audio)


# Spec: TC-07-14
def test_start_alignment_skips_when_lrc_fresh(qtbot, tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    lrc = tmp_path / "song.lrc"
    lrc.write_text("[00:00.00]hi\n", encoding="utf-8")
    import os as _os
    _os.utime(audio, (audio.stat().st_atime, lrc.stat().st_mtime - 10))

    service = _service(tmp_path)
    statuses: list = []
    service.status_changed.connect(lambda p, s: statuses.append((p, s)))
    track = _make_track(audio, lyrics="hi")
    service.start_alignment(track)
    assert (audio, AlignmentStatus.READY) in statuses
    assert not service.is_running(audio)


def test_start_alignment_idempotent_for_same_path(qtbot, tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    workers: list[FakeWorker] = []

    def factory(p, t, m):
        # Worker that hangs around — never finishes — so we can observe
        # the second start being rejected.
        w = FakeWorker(p, t, m)
        w.behavior = "interrupt"  # never emits finished
        workers.append(w)
        return w

    service = AlignmentService(
        settings=AlignmentSettings(), worker_factory=factory,
    )
    track = _make_track(audio, lyrics="hi")
    service.start_alignment(track)
    service.start_alignment(track)
    # Service constructed only one worker
    assert len(workers) == 1


# Spec: TC-07-13
def test_auto_align_on_play_off_by_default(qtbot, tmp_path):
    """Default settings: auto_align_on_play=False ⇒ no worker started."""
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    workers: list[FakeWorker] = []

    def factory(p, t, m):
        w = FakeWorker(p, t, m)
        workers.append(w)
        return w

    service = AlignmentService(
        settings=AlignmentSettings(), worker_factory=factory,
    )
    track = _make_track(audio, lyrics="hi")
    service.auto_align_on_play(track)
    assert workers == []
    assert not service.is_running(audio)


# Spec: TC-07-13
def test_auto_align_on_play_on_starts_worker(qtbot, tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    workers: list[FakeWorker] = []

    def factory(p, t, m):
        w = FakeWorker(p, t, m)
        workers.append(w)
        return w

    service = AlignmentService(
        settings=AlignmentSettings(auto_align_on_play=True),
        worker_factory=factory,
    )
    track = _make_track(audio, lyrics="hi\nthere")
    statuses: list = []
    service.status_changed.connect(lambda p, s: statuses.append((p, s)))
    service.auto_align_on_play(track)
    assert len(workers) == 1
    assert (audio, AlignmentStatus.ALIGNING) in statuses
    # Wait for synchronous fake worker run() to deliver finished_ok
    qtbot.waitUntil(lambda: (audio, AlignmentStatus.READY) in statuses, timeout=2000)


# Spec: TC-07-08
def test_cancel_no_lrc_written(qtbot, tmp_path):
    """Worker requested-to-interrupt before run() completes leaves no LRC."""
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    lrc = tmp_path / "song.lrc"

    def factory(p, t, m):
        w = FakeWorker(p, t, m)
        w.behavior = "interrupt"
        return w

    service = AlignmentService(
        settings=AlignmentSettings(), worker_factory=factory,
    )
    track = _make_track(audio, lyrics="hi")
    service.start_alignment(track)
    service.cancel(audio)
    qtbot.wait(50)  # let the QThread finish
    assert not lrc.exists()


def test_failed_emits_failed_status_and_error(qtbot, tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")

    def factory(p, t, m):
        w = FakeWorker(p, t, m)
        w.behavior = "fail"
        return w

    service = AlignmentService(
        settings=AlignmentSettings(), worker_factory=factory,
    )
    track = _make_track(audio, lyrics="hi")
    statuses: list = []
    errors: list = []
    service.status_changed.connect(lambda p, s: statuses.append((p, s)))
    service.error.connect(lambda p, msg: errors.append((p, msg)))
    service.start_alignment(track)
    qtbot.waitUntil(lambda: (audio, AlignmentStatus.FAILED) in statuses, timeout=2000)
    assert errors and errors[0][0] == audio


def test_lyrics_ready_emitted_on_success(qtbot, tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    service = _service(tmp_path)
    track = _make_track(audio, lyrics="walking the line")
    received: list = []
    service.lyrics_ready.connect(lambda p, lr: received.append((p, lr)))
    service.start_alignment(track)
    qtbot.waitUntil(lambda: bool(received), timeout=2000)
    assert received[0][0] == audio
    assert isinstance(received[0][1], Lyrics)
