"""Spec 30 §4.3-4.4 - closing, relaunching, the pin and the saved spot
(TC-30-07, TC-30-08, TC-30-09)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication

from album_builder.persistence.state_io import AppState, MiniPlayerState, load_state
from tests.ui.test_TC_30_mini_swap import FakePlacement, make_window


class _ShowSpy(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.shows = 0

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Show:
            self.shows += 1
        return False


# Spec: TC-30-07
def test_close_and_relaunch(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    quits: list[bool] = []
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: quits.append(True)))
    win = make_window(qtbot, tracks_dir, tmp_path, AppState(), FakePlacement())
    win.show_initial()
    win.enter_mini()

    win._mini.close()  # the mini player's own close button
    assert quits == [True]
    assert not win._mini.isVisible()
    assert load_state(tmp_path).mini_player.active is True

    state = load_state(tmp_path)
    again = make_window(qtbot, tracks_dir, tmp_path, state, FakePlacement())
    spy = _ShowSpy()
    again.installEventFilter(spy)
    scheduled: list[int] = []
    monkeypatch.setattr(again._updates, "schedule_daily", lambda: scheduled.append(1))
    again.show_initial()
    assert again._mini.isVisible()
    assert not again.isVisible()
    assert spy.shows == 0, "the full window never flashes"
    assert scheduled == [1]

    # A full-window close saves active: false.
    again.leave_mini()
    again.close()
    assert load_state(tmp_path).mini_player.active is False


# Spec: TC-30-07
def test_full_window_launch_schedules_update_check_once(
    qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    win = make_window(qtbot, tracks_dir, tmp_path, AppState(), FakePlacement())
    scheduled: list[int] = []
    monkeypatch.setattr(win._updates, "schedule_daily", lambda: scheduled.append(1))
    win.show_initial()
    win.enter_mini()
    win.leave_mini()
    assert win.isVisible()
    assert scheduled == [1]


# Spec: TC-30-08
def test_pin(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    fake = FakePlacement()
    win = make_window(qtbot, tracks_dir, tmp_path, AppState(), fake)
    win.show_initial()
    win.enter_mini()
    assert fake.applied[-1][2] is True
    assert win._mini.pin.isChecked()
    assert win._mini.pin.isVisibleTo(win._mini)

    win._mini.pin.click()
    assert fake.applied[-1][2] is False
    assert load_state(tmp_path).mini_player.on_top is False

    win.leave_mini()
    win.enter_mini()
    assert fake.applied[-1][2] is False, "every show passes the saved pin"
    assert not win._mini.pin.isChecked()

    # Where on-top cannot work, the pin is hidden.
    other = make_window(
        qtbot, tracks_dir, tmp_path / "other", AppState(), FakePlacement(supported=False),
    )
    other.show_initial()
    other.enter_mini()
    assert not other._mini.pin.isVisibleTo(other._mini)


# Spec: TC-30-09
def test_position(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: None))
    fake = FakePlacement(answers=[(50, 60), None, (70, 80)])
    state = AppState(mini_player=MiniPlayerState(width=500))
    win = make_window(qtbot, tracks_dir, tmp_path, state, fake)
    win.show_initial()

    win.enter_mini()
    assert fake.applied[-1][:2] == (None, None)
    assert win._mini.width() == 500

    win.leave_mini()  # reads (50, 60)
    saved = load_state(tmp_path).mini_player
    assert (saved.x, saved.y) == (50, 60)

    win.enter_mini()
    assert fake.applied[-1][:2] == (50, 60)
    win.leave_mini()  # reads None: the saved spot stays
    saved = load_state(tmp_path).mini_player
    assert (saved.x, saved.y) == (50, 60)

    win.enter_mini()
    win._mini.close()  # reads (70, 80) on close
    saved = load_state(tmp_path).mini_player
    assert (saved.x, saved.y, saved.active) == (70, 80, True)
