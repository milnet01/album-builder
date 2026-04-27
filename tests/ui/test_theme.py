from album_builder.ui.theme import Palette, qt_stylesheet


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
