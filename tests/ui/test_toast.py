"""Tests for album_builder.ui.toast - Spec 06 transient errors."""

from __future__ import annotations

from album_builder.ui.toast import Toast


# Spec: TC-06-06
def test_toast_initially_hidden(qtbot) -> None:
    t = Toast()
    qtbot.addWidget(t)
    assert not t.isVisible()


# Spec: TC-06-06
def test_toast_shows_message(qtbot) -> None:
    t = Toast()
    qtbot.addWidget(t)
    t.show_message("Track file not found: /a/b.mp3")
    assert t.isVisible()
    assert t.message_label.text() == "Track file not found: /a/b.mp3"


# Spec: TC-06-06
def test_toast_auto_dismisses(qtbot) -> None:
    t = Toast(auto_dismiss_ms=200)
    qtbot.addWidget(t)
    t.show_message("test")
    assert t.isVisible()
    qtbot.wait(400)
    assert not t.isVisible()


# Spec: TC-06-06
def test_toast_overwrites_previous(qtbot) -> None:
    t = Toast()
    qtbot.addWidget(t)
    t.show_message("first")
    t.show_message("second")
    assert t.message_label.text() == "second"


# Spec: TC-06-06
def test_toast_close_button_dismisses(qtbot) -> None:
    t = Toast()
    qtbot.addWidget(t)
    t.show_message("test")
    t.btn_close.click()
    assert not t.isVisible()


# Spec: TC-06-06
def test_toast_show_message_resets_timer(qtbot) -> None:
    """A new show_message call should reset the auto-dismiss timer so the
    user gets the full window for the new message, not a residual sliver
    from the prior one."""
    # 500 ms dismiss window with two 200 ms gaps: a working timer-reset
    # leaves 300 ms slack at the assertion. The prior 200/150/150 setup
    # produced only ~50 ms slack and flaked on loaded CI runners.
    t = Toast(auto_dismiss_ms=500)
    qtbot.addWidget(t)
    t.show_message("first")
    qtbot.wait(200)
    t.show_message("second")
    qtbot.wait(200)  # 400 ms since "first"; without reset, hidden by 500.
    assert t.isVisible()


# Indie-review L7-H2 (Theme F / WCAG 2.2 §4.1.3 Status Messages): the
# toast must surface an accessible description that AT can announce on
# the property-change. (PyQt6 doesn't bind QAccessible directly, so the
# canonical Alert-event fire is unavailable; setAccessibleDescription
# gives Orca / NVDA / VoiceOver a property-changed event on a named
# widget — the closest live-region announcement available.)
def test_toast_show_sets_accessible_description(qtbot) -> None:
    t = Toast()
    qtbot.addWidget(t)
    t.show_message("Track file not found: /a/b.mp3")
    assert t.accessibleName(), "toast must have an accessible name"
    assert "Track file not found" in t.accessibleDescription(), (
        "show_message must thread the message into accessibleDescription "
        "so AT announces the toast (WCAG 2.2 §4.1.3 Status Messages)"
    )
    # Sanity: a follow-up toast updates the description.
    t.show_message("Different problem")
    assert "Different problem" in t.accessibleDescription()
