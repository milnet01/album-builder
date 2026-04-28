"""Tests for album_builder.persistence.debounce."""

from __future__ import annotations

import pytest

from album_builder.persistence.debounce import DebouncedWriter


@pytest.fixture
def app(qapp):
    return qapp


def test_debounce_collapses_rapid_calls(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    for _ in range(5):
        w.schedule("k", lambda: calls.append("write"))
    qtbot.wait(80)
    assert calls == ["write"]


def test_debounce_independent_keys(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    w.schedule("a", lambda: calls.append("a"))
    w.schedule("b", lambda: calls.append("b"))
    qtbot.wait(80)
    assert sorted(calls) == ["a", "b"]


def test_flush_all_runs_pending_synchronously(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=10_000)  # large window - would not fire in test
    w.schedule("k", lambda: calls.append("write"))
    assert calls == []
    w.flush_all()
    assert calls == ["write"]
    # And a second flush_all is a no-op
    w.flush_all()
    assert calls == ["write"]


def test_schedule_after_flush_still_works(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    w.schedule("k", lambda: calls.append("first"))
    w.flush_all()
    w.schedule("k", lambda: calls.append("second"))
    qtbot.wait(80)
    assert calls == ["first", "second"]
