"""Tests for album_builder.ui.target_counter - Spec 04 TC-04-10..13."""

from __future__ import annotations

import pytest

from album_builder.ui.target_counter import TargetCounter


@pytest.fixture
def counter(qtbot) -> TargetCounter:
    w = TargetCounter()
    qtbot.addWidget(w)
    w.set_state(target=12, selected=0, draft=True)
    return w


# Spec: TC-04-10
def test_down_disabled_at_target(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=12, draft=True)
    assert not counter.btn_down.isEnabled()
    counter.set_state(target=12, selected=11, draft=True)
    assert counter.btn_down.isEnabled()


# Spec: TC-04-11
def test_up_disabled_at_99(counter: TargetCounter) -> None:
    counter.set_state(target=99, selected=10, draft=True)
    assert not counter.btn_up.isEnabled()
    counter.set_state(target=98, selected=10, draft=True)
    assert counter.btn_up.isEnabled()


# Spec: TC-04-12
def test_typing_zero_snaps_to_one(counter: TargetCounter, qtbot) -> None:
    received: list[int] = []
    counter.target_changed.connect(received.append)
    counter.field.setText("0")
    counter.field.editingFinished.emit()
    assert counter.field.text() == "1"
    assert received and received[-1] == 1


# Spec: TC-04-12
def test_typing_over_99_snaps_to_99(counter: TargetCounter) -> None:
    received: list[int] = []
    counter.target_changed.connect(received.append)
    counter.field.setText("250")
    counter.field.editingFinished.emit()
    assert counter.field.text() == "99"
    assert received and received[-1] == 99


# Spec: TC-04-13
def test_typing_non_integer_reverts(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=0, draft=True)
    counter.field.setText("abc")
    counter.field.editingFinished.emit()
    assert counter.field.text() == "12"


def test_readout_shows_selected_over_target(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=8, draft=True)
    assert "8" in counter.readout.text() and "12" in counter.readout.text()


# Spec: TC-04 Target counter typing-vs-commit timing
def test_readout_tracks_committed_target_not_in_progress_text(
    counter: TargetCounter,
) -> None:
    """Spec 04 Target counter pinned: typing immediately updates the
    DISPLAYED value in the field, but the live readout's `target` half
    follows the COMMITTED target - only updates on Enter / blur. This
    test asserts the readout doesn't follow keystrokes."""
    counter.set_state(target=12, selected=3, draft=True)
    assert "3 / 12" in counter.readout.text()
    counter.field.setText("8")
    assert counter.field.text() == "8"
    assert "3 / 12" in counter.readout.text()
    counter.field.editingFinished.emit()
    assert "3 / 8" in counter.readout.text()


# Spec: TC-04-16 (counter side - approve disables the up arrow too)
def test_approved_album_disables_all_controls(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=8, draft=False)
    assert not counter.btn_up.isEnabled()
    assert not counter.btn_down.isEnabled()
    assert not counter.field.isEnabled()
