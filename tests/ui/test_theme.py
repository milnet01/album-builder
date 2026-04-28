from album_builder.ui.theme import Palette, qt_stylesheet


def _wcag_luminance(hex_color: str) -> float:
    """Per WCAG 2.2 §1.4.3: relative luminance of an sRGB colour."""
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _wcag_luminance(fg), _wcag_luminance(bg)
    light, dark = max(l1, l2), min(l1, l2)
    return (light + 0.05) / (dark + 0.05)


def test_palette_has_required_tokens() -> None:
    p = Palette.dark_colourful()
    # Spot-check tokens defined in spec 11
    assert p.bg_base == "#15161c"
    assert p.bg_pane == "#1a1b22"
    assert p.accent_primary_1 == "#6e3df0"
    assert p.accent_primary_2 == "#c635a6"
    assert p.success == "#10b981"
    assert p.danger == "#ef4444"


def test_palette_tokens_are_valid_hex() -> None:
    p = Palette.dark_colourful()
    for name, value in vars(p).items():
        assert isinstance(value, str), name
        assert value.startswith("#") and len(value) == 7, f"{name}={value}"


def test_qt_stylesheet_returns_non_empty_string() -> None:
    qss = qt_stylesheet(Palette.dark_colourful())
    assert isinstance(qss, str)
    assert len(qss) > 100
    # The window background must be set
    assert "#15161c" in qss


def test_placeholder_text_meets_wcag_aa_contrast() -> None:
    """Spec 11 + WCAG 2.2 §1.4.3: regular-size text needs 4.5:1 against its
    background. Placeholder copy in the empty Phase-2 panes lives on bg_pane,
    so the placeholder colour token must clear that bar."""
    p = Palette.dark_colourful()
    ratio = _contrast_ratio(p.text_placeholder, p.bg_pane)
    assert ratio >= 4.5, f"text_placeholder/bg_pane contrast {ratio:.2f} fails WCAG AA"


def test_qt_stylesheet_includes_placeholder_text_rule() -> None:
    """The QSS must carry a QLabel#PlaceholderText rule so widgets opt in via
    objectName instead of inline setStyleSheet (which bypasses the palette)."""
    qss = qt_stylesheet(Palette.dark_colourful())
    assert "QLabel#PlaceholderText" in qss
