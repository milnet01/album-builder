"""Spec 30 §4.4 - which placement runs, and what reaches a KWin script
(TC-30-10, TC-30-11). No test here touches the real desktop or KWin."""

from __future__ import annotations

import subprocess

import pytest

from album_builder.services import window_placement as wp


class _App:
    def __init__(self, name: str) -> None:
        self._name = name

    def platformName(self) -> str:
        return self._name


def _kwin_asked(answer: bool):
    calls: list[int] = []

    def has_kwin() -> bool:
        calls.append(1)
        return answer

    return has_kwin, calls


# Spec: TC-30-10
@pytest.mark.parametrize("platform", ["windows", "xcb", "offscreen", "cocoa"])
def test_choice_qt_off_wayland(platform: str) -> None:
    has_kwin, calls = _kwin_asked(True)
    chosen = wp.placement_for(_App(platform), has_kwin=has_kwin)
    assert isinstance(chosen, wp.QtPlacement)
    assert chosen.supported
    assert calls == [], "the bus is not asked off Wayland"


# Spec: TC-30-10
def test_choice() -> None:
    has_kwin, _ = _kwin_asked(True)
    kwin = wp.placement_for(_App("wayland"), has_kwin=has_kwin)
    assert isinstance(kwin, wp.KWinPlacement)
    assert kwin.supported

    no_kwin, _ = _kwin_asked(False)
    none = wp.placement_for(_App("wayland"), has_kwin=no_kwin)
    assert isinstance(none, wp.NoPlacement)
    assert not none.supported
    assert none.read_position(object()) is None


# Spec: TC-30-11
def test_script_values() -> None:
    js = wp.move_script(pid=4242, x=-10, y=300, on_top=True)
    assert "4242" in js and "-10" in js and "300" in js
    assert "keepAbove = true" in js
    assert f'"{wp.CAPTION_PREFIX}"' in js
    off = wp.move_script(pid=4242, x=None, y=None, on_top=False)
    assert "keepAbove = false" in off
    assert "frameGeometry =" not in off

    read = wp.read_script(pid=4242, token=987654321)
    assert "987654321" in read and "print(" in read

    for bad in ("0); evil(); //", 1.5, True, None):
        with pytest.raises(ValueError):
            wp.move_script(pid=4242, x=bad, y=1, on_top=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        wp.move_script(pid="1); evil(", x=None, y=None, on_top=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        wp.read_script(pid=1, token="x); evil(")  # type: ignore[arg-type]


# Spec: TC-30-11
def test_bad_value_writes_no_script(tmp_path, monkeypatch) -> None:
    """A refused value stops before the temp directory or any D-Bus call."""
    ran: list[list[str]] = []
    made: list[str] = []
    monkeypatch.setattr(wp.tempfile, "mkdtemp", lambda **_k: made.append("dir") or str(tmp_path))

    def run(cmd, **_k):
        ran.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    placement = wp.KWinPlacement(run=run, delay_s=0.0)
    placement.apply(object(), x="0); evil(); //", y=1, on_top=True)  # type: ignore[arg-type]
    placement.wait_idle()
    assert ran == [] and made == []
