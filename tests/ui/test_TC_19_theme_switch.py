"""Spec 19 - live theme switching: menu, apply path, persistence, crash-safety.

The `main_window` fixture (tests/ui/conftest.py) isolates XDG_CONFIG_HOME, so
`write_ui` / `read_ui` here hit a per-test settings.json, not the user's real one.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor

import album_builder.ui.main_window as mw
from album_builder.domain.lyrics import LyricLine, Lyrics
from album_builder.persistence.settings import (
    ALLOWED_THEMES,
    UiSettings,
    read_ui,
    write_ui,
)
from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.library_pane import LibraryPane
from album_builder.ui.lyrics_panel import LyricsPanel
from album_builder.ui.main_window import MainWindow
from album_builder.ui.theme import THEMES, Palette, palette_for, qt_stylesheet


def _lyrics(*texts: str) -> Lyrics:
    return Lyrics(
        lines=tuple(
            LyricLine(time_seconds=float(i), text=t) for i, t in enumerate(texts)
        )
    )


def _theme_submenu_actions(win):
    menus = {a.text(): a.menu() for a in win.menuBar().actions()}
    view_items = {a.text(): a for a in menus["View"].actions()}
    return list(view_items["Theme"].menu().actions())


# Spec: TC-19-05
def test_allowed_themes_matches_registry() -> None:
    assert ALLOWED_THEMES == set(THEMES)


# Spec: TC-19-06
def test_lyrics_panel_set_palette_recolours_now_line(qtbot) -> None:
    panel = LyricsPanel()
    qtbot.addWidget(panel)
    panel.set_lyrics(_lyrics("one", "two", "three"))
    panel.set_current_line(0)  # line 0 becomes the "now" line -> accent_warm
    panel.set_palette(Palette.light())
    now_colour = panel.list.item(0).foreground().color()
    assert now_colour == QColor(Palette.light().accent_warm)
    assert now_colour != QColor(Palette.dark_colourful().accent_warm)


# Spec: TC-19-07
def test_library_pane_set_palette_updates_delegate(qtbot) -> None:
    pane = LibraryPane()
    qtbot.addWidget(pane)
    light = Palette.light()
    pane.set_palette(light)
    assert pane._usage_delegate._palette is light


# Spec: TC-19-08
def test_menu_bar_structure(main_window) -> None:
    top = [a.text() for a in main_window.menuBar().actions()]
    assert top == ["File", "View", "Help"]
    actions = _theme_submenu_actions(main_window)
    assert [a.text() for a in actions] == [name for name, _ in THEMES.values()]
    assert all(a.isCheckable() for a in actions)
    assert sum(a.isChecked() for a in actions) == 1


# Spec: TC-19-09
def test_live_switch_applies_persists_and_preserves_flag(main_window, monkeypatch) -> None:
    win = main_window
    # Start with the open-report flag False, to prove the theme write preserves it.
    win._ui_settings = UiSettings(
        open_report_folder_on_approve=False, theme=win._current_theme
    )
    panel = win.now_playing_pane.lyrics_panel
    seen: list = []
    orig = panel.set_palette
    monkeypatch.setattr(panel, "set_palette", lambda p: (seen.append(p), orig(p)))

    win._theme_actions["light"].trigger()

    light = palette_for("light")
    assert win.styleSheet() == qt_stylesheet(light)
    assert win._current_theme == "light"
    assert win._theme_actions["light"].isChecked()
    assert seen and seen[-1] == light
    persisted = read_ui()
    assert persisted.theme == "light"
    assert persisted.open_report_folder_on_approve is False  # preserved


# Spec: TC-19-10
def test_startup_applies_persisted_theme(qtbot, tracks_dir, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    write_ui(UiSettings(open_report_folder_on_approve=True, theme="dark-ocean"))
    win = MainWindow(
        AlbumStore(tmp_path / "Albums"),
        LibraryWatcher(tracks_dir),
        AppState(),
        tmp_path,
    )
    qtbot.addWidget(win)
    assert win._current_theme == "dark-ocean"
    assert win.styleSheet() == qt_stylesheet(palette_for("dark-ocean"))
    assert win._theme_actions["dark-ocean"].isChecked()


# Spec: TC-19-11
def test_reselecting_current_theme_is_idempotent(main_window) -> None:
    win = main_window
    win._apply_theme("light", persist=True)
    win._theme_actions["light"].trigger()  # re-select the already-current theme
    assert win._current_theme == "light"
    assert sum(a.isChecked() for a in win._theme_actions.values()) == 1


# Spec: TC-19-12
def test_menu_items_wrap_existing_handlers(main_window, monkeypatch) -> None:
    win = main_window
    fired: list[str] = []
    monkeypatch.setattr(win, "_on_new_album", lambda: fired.append("new"))
    monkeypatch.setattr(win, "close", lambda: fired.append("quit"))
    monkeypatch.setattr(win, "_show_help", lambda: fired.append("help"))
    menus = {a.text(): a.menu() for a in win.menuBar().actions()}
    file_items = {a.text(): a for a in menus["File"].actions() if a.text()}
    help_items = {a.text(): a for a in menus["Help"].actions() if a.text()}
    file_items["New Album"].trigger()
    file_items["Quit"].trigger()
    help_items["Keyboard shortcuts"].trigger()
    assert fired == ["new", "quit", "help"]


# Spec: TC-19-13
def test_write_ui_failure_does_not_crash(main_window, monkeypatch) -> None:
    win = main_window

    def boom(_settings):
        raise OSError("disk full")

    monkeypatch.setattr(mw, "write_ui", boom)
    toasts: list[str] = []
    monkeypatch.setattr(win, "_show_toast", lambda msg: toasts.append(msg))

    win._theme_actions["dark-ember"].trigger()  # persist=True -> write_ui raises

    assert win.styleSheet() == qt_stylesheet(palette_for("dark-ember"))
    assert win._current_theme == "dark-ember"
    assert toasts  # user was told persistence failed; no crash
