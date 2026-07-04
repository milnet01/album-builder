"""Spec 19 - multiple themes + registry + WCAG contrast contract.

Palette / registry / contrast tests need no QApplication; the menu + apply-path
tests live in tests/ui/test_TC_19_theme_switch.py (they build a real MainWindow).
"""

from __future__ import annotations

import pytest

from album_builder.ui.theme import THEMES, Palette, palette_for, qt_stylesheet


def _wcag_luminance(hex_color: str) -> float:
    """Per WCAG 2.2 §1.4.3: relative luminance of an sRGB colour."""
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(fg: str, bg: str) -> float:
    light, dark = sorted((_wcag_luminance(fg), _wcag_luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


_NEW_THEMES = ["light", "dark-ocean", "dark-ember", "dark-slate"]
_ALL_THEMES = ["dark-colourful", *_NEW_THEMES]

_PALETTE_FIELDS = (
    "bg_base", "bg_pane", "bg_elevated", "border", "border_strong",
    "text_primary", "text_secondary", "text_tertiary", "text_placeholder",
    "text_disabled", "accent_primary_1", "accent_primary_2", "accent_warm",
    "success", "success_dark", "warning", "danger",
)


# Spec: TC-19-01
def test_registry_ids_order_and_shape() -> None:
    assert list(THEMES) == _ALL_THEMES
    for display_name, factory in THEMES.values():
        assert isinstance(display_name, str) and display_name
        assert isinstance(factory(), Palette)


# Spec: TC-19-02
def test_palette_for_resolves_and_falls_back() -> None:
    for theme_id in _ALL_THEMES:
        assert palette_for(theme_id) == THEMES[theme_id][1]()
    # Unknown id degrades to dark-colourful without raising.
    assert palette_for("nope") == Palette.dark_colourful()
    assert palette_for("") == Palette.dark_colourful()


# Spec: TC-19-03
@pytest.mark.parametrize("theme_id", _ALL_THEMES)
def test_palette_fully_populated(theme_id: str) -> None:
    p = palette_for(theme_id)
    for field in _PALETTE_FIELDS:
        value = getattr(p, field)
        assert isinstance(value, str) and len(value) == 7 and value.startswith("#")
        int(value[1:], 16)  # valid hex


# Spec: TC-19-04 - body-text pairs, all five themes >= 4.5:1
@pytest.mark.parametrize("theme_id", _ALL_THEMES)
def test_body_text_contrast_all_themes(theme_id: str) -> None:
    p = palette_for(theme_id)
    pairs = [
        (p.text_primary, p.bg_pane, "text_primary/bg_pane"),
        (p.text_primary, p.bg_base, "text_primary/bg_base"),
        (p.text_secondary, p.bg_pane, "text_secondary/bg_pane"),
        (p.text_secondary, p.bg_elevated, "text_secondary/bg_elevated"),
        (p.text_placeholder, p.bg_pane, "text_placeholder/bg_pane"),
        (p.accent_warm, p.bg_pane, "accent_warm/bg_pane"),
        (p.accent_warm, p.bg_base, "accent_warm/bg_base"),
    ]
    for fg, bg, label in pairs:
        ratio = _contrast(fg, bg)
        assert ratio >= 4.5, f"{theme_id}: {label} = {ratio:.2f} (need >= 4.5)"


# Spec: TC-19-04 - text_tertiary >= 4.5:1 for the four new themes (dark-colourful
# is grandfathered at its pre-existing ~3.5:1, per Spec 19 §Accessibility).
@pytest.mark.parametrize("theme_id", _NEW_THEMES)
def test_tertiary_text_contrast_new_themes(theme_id: str) -> None:
    p = palette_for(theme_id)
    ratio = _contrast(p.text_tertiary, p.bg_pane)
    assert ratio >= 4.5, f"{theme_id}: text_tertiary/bg_pane = {ratio:.2f} (need >= 4.5)"


def test_dark_colourful_tertiary_is_grandfathered() -> None:
    # Pin the documented pre-existing exception: below AA, above the 3:1 floor.
    p = Palette.dark_colourful()
    ratio = _contrast(p.text_tertiary, p.bg_pane)
    assert 3.0 <= ratio < 4.5


# Spec: TC-19-04 - status/indicator colours >= 3:1 for the four new themes.
@pytest.mark.parametrize("theme_id", _NEW_THEMES)
def test_status_colour_contrast_new_themes(theme_id: str) -> None:
    p = palette_for(theme_id)
    for token in ("success", "warning", "danger"):
        ratio = _contrast(getattr(p, token), p.bg_pane)
        assert ratio >= 3.0, f"{theme_id}: {token}/bg_pane = {ratio:.2f} (need >= 3.0)"


@pytest.mark.parametrize("theme_id", _ALL_THEMES)
def test_qt_stylesheet_renders_for_every_theme(theme_id: str) -> None:
    css = qt_stylesheet(palette_for(theme_id))
    assert isinstance(css, str) and css.strip()
