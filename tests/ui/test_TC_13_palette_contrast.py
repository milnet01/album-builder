"""WCAG 2.2 §1.4.3 AA contrast verification for the Used pill (Spec 13 TC-13-32).

Guards against future palette tuning silently regressing AA on the badge.
"""

from __future__ import annotations

from album_builder.ui.theme import Palette


def _relative_luminance(hex_colour: str) -> float:
    """sRGB relative luminance per WCAG 2.2 §1.4.3."""
    h = hex_colour.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0

    def _channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * _channel(r)
        + 0.7152 * _channel(g)
        + 0.0722 * _channel(b)
    )


def _contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.2 §1.4.3 contrast ratio."""
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = (l1, l2) if l1 > l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


# Spec: TC-13-32 - pill text-on-fill contrast >= 4.5:1 (AA, normal text).
def test_TC_13_32_pill_contrast_meets_aa() -> None:
    palette = Palette.dark_colourful()
    pill_fill = palette.accent_primary_1
    pill_text = "#ffffff"
    ratio = _contrast_ratio(pill_text, pill_fill)
    assert ratio >= 4.5, (
        f"Used pill contrast ratio {ratio:.2f}:1 fails WCAG 2.2 §1.4.3 AA "
        f"(needs >= 4.5:1). Palette tweak required: "
        f"either lighten {pill_text} or darken {pill_fill}."
    )
