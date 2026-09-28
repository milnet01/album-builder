"""View > Language - Spec 25 §Public API `ui/main_window.py`, TC-25-09."""

from __future__ import annotations

from album_builder import i18n
from album_builder.persistence.settings import read_ui
from album_builder.ui.toast import Toast


def _language_menu(win):
    view = next(a.menu() for a in win.menuBar().actions() if a.text() == "View")
    return next(a.menu() for a in view.actions() if a.menu() and a.text() == "Language")


# Spec: TC-25-09
def test_language_menu_lists_system_then_supported(main_window) -> None:
    labels = [a.text() for a in _language_menu(main_window).actions() if not a.isSeparator()]
    assert labels == ["System default"] + [i18n.language_name(c) for c in i18n.SUPPORTED]


# Spec: TC-25-09
def test_picking_a_language_saves_it_and_asks_for_restart(main_window) -> None:
    win = main_window
    actions = {a.text(): a for a in _language_menu(win).actions()}
    assert actions["System default"].isChecked()
    actions["Deutsch"].trigger()
    assert read_ui().language == "de"
    toast = win.findChild(Toast).message_label.text()
    assert "Restart Album Builder" in toast and "Deutsch" in toast

    # Theme switch keeps the language; language pick keeps the theme.
    other = next(t for t in win._theme_actions if t != win._current_theme)
    win._theme_actions[other].trigger()
    assert read_ui().language == "de"
    actions["English"].trigger()
    assert read_ui().theme == other
    assert read_ui().language == "en"


# Spec: TC-25-09
def test_picking_the_checked_language_writes_nothing(main_window, monkeypatch) -> None:
    writes: list = []
    monkeypatch.setattr("album_builder.ui.main_window.write_ui", lambda ui: writes.append(ui))
    actions = {a.text(): a for a in _language_menu(main_window).actions()}
    actions["System default"].trigger()
    assert writes == []
