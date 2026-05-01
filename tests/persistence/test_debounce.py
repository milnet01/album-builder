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


# Spec: L5-M3 (Tier 1 indie-review 2026-04-30)
def test_cancel_drops_pending_callback_without_firing(app, qtbot) -> None:
    """cancel() removes the queued callback for a key. The next idle-window
    expiry must NOT fire it. Used by AlbumStore.delete()/rename() to prevent
    a queued save from writing into a folder that's been moved or trashed."""
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    w.schedule("k", lambda: calls.append("would-have-fired"))
    w.cancel("k")
    qtbot.wait(80)
    assert calls == []


def test_cancel_unknown_key_is_safe(app, qtbot) -> None:
    """cancel() of a key that was never scheduled is a no-op, not an error."""
    w = DebouncedWriter(idle_ms=20)
    w.cancel("never-scheduled")  # must not raise


def test_schedule_after_cancel_works(app, qtbot) -> None:
    """A cancel() does not poison the key. A subsequent schedule() with the
    same key fires normally."""
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    w.schedule("k", lambda: calls.append("first"))
    w.cancel("k")
    w.schedule("k", lambda: calls.append("second"))
    qtbot.wait(80)
    assert calls == ["second"]


# Spec: L3-M4 (indie-review 2026-04-30, Phase 3B Tier 3 deferral closed v0.5.3)
def test_fire_garbage_collects_timer_entry(app, qtbot) -> None:
    """After a scheduled callback fires, the QTimer is dropped from `_timers`
    instead of leaking. Bounds the dict to active-burst keys regardless of
    key cardinality (today: album UUID + literal "state"; tomorrow: any
    high-cardinality scheme that lands)."""
    w = DebouncedWriter(idle_ms=20)
    w.schedule("k", lambda: None)
    assert "k" in w._timers
    qtbot.wait(80)
    assert "k" not in w._timers


# Spec: L3-M4 (indie-review 2026-04-30, Phase 3B Tier 3 deferral closed v0.5.3)
def test_flush_all_garbage_collects_timer_entries(app, qtbot) -> None:
    """flush_all() also drops timer entries: after one flush, schedule for the
    same key reconstructs a fresh QTimer rather than reusing a stale one."""
    w = DebouncedWriter(idle_ms=10_000)
    w.schedule("a", lambda: None)
    w.schedule("b", lambda: None)
    assert {"a", "b"} <= set(w._timers)
    w.flush_all()
    assert "a" not in w._timers
    assert "b" not in w._timers


# Indie-review L3-H4: a raising callback must not escape into Qt's slot
# dispatcher (which silently drops the write per Spec 10 §Errors). The
# writer must keep accepting subsequent schedules.
def test_callback_exception_logged_and_suppressed(app, qtbot, caplog) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)

    def boom() -> None:
        raise OSError("simulated disk full")
    w.schedule("k", boom)
    w.schedule("k2", lambda: calls.append("survivor"))
    qtbot.wait(80)
    # boom raised; survivor still ran:
    assert calls == ["survivor"]
    # And the failure was logged via DebouncedWriter's logger.exception:
    assert any("DebouncedWriter callback failed" in rec.message for rec in caplog.records)
