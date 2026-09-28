"""Every theme styles the tab bars itself - MUSI-0382.

Contract (this file's own; no spec clause carries it): the theme stylesheet
has QTabBar::tab and QTabWidget::pane rules drawn from the theme's palette,
so no platform's native tab look shows through. Found 2026-09-28 on
Windows, where the main tabs drew white with nearly invisible labels. Linux
cannot show that failure, so this locks the rule's presence and colours;
the Windows test machine is the visual check.
"""

from __future__ import annotations

import pytest

from album_builder.ui.theme import THEMES, qt_stylesheet


@pytest.mark.parametrize("theme_id", list(THEMES))
def test_theme_styles_tab_bar_and_pane_from_its_palette(theme_id: str) -> None:
    # Spec: MUSI-0382
    palette = THEMES[theme_id][1]()
    qss = qt_stylesheet(palette)
    for selector in ("QTabWidget::pane", "QTabBar::tab", "QTabBar::tab:selected"):
        assert selector + " {" in qss, f"{theme_id}: no {selector} rule"
    tab_rule = qss.split("QTabBar::tab {", 1)[1].split("}", 1)[0]
    assert palette.text_secondary in tab_rule and palette.bg_elevated in tab_rule
    selected_rule = qss.split("QTabBar::tab:selected {", 1)[1].split("}", 1)[0]
    assert palette.text_primary in selected_rule
