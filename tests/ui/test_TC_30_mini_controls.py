"""Spec 30 §4.2 - the mini player drives the shared pipeline (TC-30-04..06)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QColor, QImage

from album_builder.domain.library import Library
from album_builder.domain.track import Track
from album_builder.services.play_history import PlayHistory
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player
from album_builder.ui.mini_player import MiniPlayer
from album_builder.ui.theme import Glyphs


def _png() -> bytes:
    img = QImage(8, 8, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def _track(path: Path, *, cover: bytes | None = None) -> Track:
    return Track(
        path=path, title=f"Title {path.stem}", artist=f"Artist {path.stem}",
        album_artist="", composer="", album="", comment="", lyrics_text=None,
        cover_data=cover, cover_mime="image/png" if cover else None,
        duration_seconds=100.0, file_size_bytes=1, is_missing=False,
    )


@pytest.fixture
def rig(qtbot, tmp_path: Path):
    music = tmp_path / "music"
    one, two = _track(music / "one.mp3", cover=_png()), _track(music / "two.mp3")
    lib = Library(folder=music, tracks=[one, two])
    player = Player()
    controller = PlaybackController(player)
    history = PlayHistory(tmp_path / "root", player, SimpleNamespace(library=lambda: lib))
    mini = MiniPlayer(player, controller, history)
    qtbot.addWidget(mini)
    return SimpleNamespace(
        mini=mini, player=player, controller=controller, history=history, one=one, two=two,
    )


# Spec: TC-30-04
def test_buttons_drive_the_shared_controller(rig, monkeypatch) -> None:
    calls: list[str] = []
    for name in ("previous", "toggle", "next"):
        monkeypatch.setattr(rig.controller, name, lambda n=name: calls.append(n))
    rig.mini.btn_prev.click()
    rig.mini.btn_play.click()
    rig.mini.btn_next.click()
    assert calls == ["previous", "toggle", "next"]


# Spec: TC-30-04
def test_progress_and_volume(rig, monkeypatch) -> None:
    seeks: list[float] = []
    volumes: list[int] = []
    monkeypatch.setattr(rig.player, "seek", seeks.append)
    real_set_volume = rig.player.set_volume
    monkeypatch.setattr(rig.player, "set_volume",
                        lambda v: (volumes.append(v), real_set_volume(v)))

    # A change from elsewhere moves the progress bar and its range.
    rig.player.duration_changed.emit(200.0)
    rig.player.position_changed.emit(42.0)
    assert rig.mini.progress.maximum() == 200
    assert rig.mini.progress.value() == 42

    # Releasing the bar seeks to its value.
    rig.mini.progress.setValue(120)
    rig.mini.progress.sliderReleased.emit()
    assert seeks == [120.0]

    # Moving the volume slider sets the player's volume.
    rig.mini.volume.setValue(33)
    assert volumes[-1] == 33

    # A volume change from elsewhere moves the slider.
    real_set_volume(71)
    assert rig.mini.volume.value() == 71


# Spec: TC-30-04
def test_controls_stay_left_to_right(rig) -> None:
    assert rig.mini.controls.layoutDirection() == Qt.LayoutDirection.LeftToRight


# Spec: TC-30-05
def test_track_display(rig) -> None:
    rig.controller.current_changed.emit(rig.one)
    assert rig.mini.title_label.text() == "Title one"
    assert rig.mini.artist_label.text() == "Artist one"
    pix = rig.mini.cover_label.pixmap()
    assert pix is not None and not pix.isNull() and pix.height() == 64

    rig.controller.current_changed.emit(rig.two)  # no cover: none left over
    assert rig.mini.title_label.text() == "Title two"
    pix = rig.mini.cover_label.pixmap()
    assert pix is None or pix.isNull()

    rig.controller.current_changed.emit(None)
    assert rig.mini.title_label.text() == ""
    assert rig.mini.artist_label.text() == ""
    assert not rig.mini.heart.isEnabled()
    assert not rig.mini.heart.isChecked()


# Spec: TC-30-06
def test_heart(rig, monkeypatch) -> None:
    heart = rig.mini.heart
    assert not heart.isEnabled()  # nothing loaded

    rig.controller.current_changed.emit(rig.one)
    assert heart.isEnabled() and not heart.isChecked()
    assert heart.text() == Glyphs.HEART_OUTLINE

    heart.click()
    assert rig.history.stats_for(rig.one).favourited is not None
    assert heart.isChecked() and heart.text() == Glyphs.HEART

    # A change from another surface shows here without re-toggling.
    calls: list[tuple] = []
    real = rig.history.set_favourite
    monkeypatch.setattr(rig.history, "set_favourite",
                        lambda t, on: (calls.append((t, on)), real(t, on)))
    real(rig.one, False)
    assert not heart.isChecked()
    assert calls == []
