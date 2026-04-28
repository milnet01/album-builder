"""Dark + colourful theme — palette and Qt stylesheet."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg_base: str
    bg_pane: str
    bg_elevated: str
    border: str
    border_strong: str
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_placeholder: str
    text_disabled: str
    accent_primary_1: str
    accent_primary_2: str
    accent_warm: str
    success: str
    success_dark: str
    warning: str
    danger: str

    @classmethod
    def dark_colourful(cls) -> Palette:
        return cls(
            bg_base="#15161c",
            bg_pane="#1a1b22",
            bg_elevated="#1f2029",
            border="#262830",
            border_strong="#383a47",
            text_primary="#e8e9ee",
            text_secondary="#8a8d9a",
            text_tertiary="#6e717c",
            # WCAG 2.2 AA-compliant placeholder colour: 6.4:1 vs bg_pane.
            # Don't replace with text_tertiary (3.2:1) for "subtle" copy on
            # bg_pane — that fails accessibility.
            text_placeholder="#9a9da8",
            text_disabled="#4a4d5a",
            accent_primary_1="#6e3df0",
            accent_primary_2="#c635a6",
            accent_warm="#f6c343",
            success="#10b981",
            success_dark="#059669",
            warning="#f97316",
            danger="#ef4444",
        )


def qt_stylesheet(p: Palette) -> str:
    return f"""
    QMainWindow, QWidget {{
        background-color: {p.bg_base};
        color: {p.text_primary};
        font-family: "Inter", "Cantarell", "Segoe UI", system-ui, sans-serif;
        font-size: 11pt;
    }}
    QFrame#Pane {{
        background-color: {p.bg_pane};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    QFrame#TopBar {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    QLabel#PaneTitle {{
        color: {p.accent_warm};
        font-size: 9pt;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding-bottom: 6px;
        border-bottom: 1px solid {p.border};
    }}
    QLabel#PlaceholderText {{
        color: {p.text_placeholder};
    }}
    QLineEdit {{
        background-color: {p.bg_base};
        border: 1px solid {p.border_strong};
        border-radius: 5px;
        padding: 4px 8px;
        color: {p.text_primary};
        selection-background-color: {p.accent_primary_1};
    }}
    QLineEdit:focus {{
        border-color: {p.accent_primary_1};
    }}
    QHeaderView::section {{
        background-color: {p.bg_elevated};
        color: {p.text_secondary};
        padding: 6px 8px;
        border: none;
        border-right: 1px solid {p.border};
    }}
    QTableView {{
        background-color: {p.bg_pane};
        alternate-background-color: {p.bg_elevated};
        gridline-color: {p.border};
        selection-background-color: {p.accent_primary_1};
        selection-color: {p.text_primary};
    }}
    QTableView::item {{
        padding: 6px;
        border: none;
    }}
    QTableView::item[accent="primary"] {{
        border-left: 3px solid {p.accent_primary_1};
        background: rgba(124, 92, 255, 0.08);
    }}
    QTableView::item[accent="warning"] {{
        border-left: 3px solid {p.warning};
        background: rgba(232, 158, 81, 0.08);
    }}
    QSplitter::handle {{
        background-color: {p.border};
    }}
    QSplitter::handle:horizontal {{
        width: 2px;
    }}
    QPushButton {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border_strong};
        border-radius: 6px;
        padding: 5px 12px;
        color: {p.text_primary};
    }}
    QPushButton:hover {{
        background-color: {p.bg_pane};
    }}
    QPushButton:disabled {{
        color: {p.text_disabled};
        border-color: {p.border};
    }}
    /* Spec 11 §Gradients (TC-11-08): approve button uses success ->
       success-dark. Qt QSS spells the linear-gradient(135deg, ...) form
       as qlineargradient with normalised endpoint coordinates - 135deg
       maps to top-left -> bottom-right. */
    QPushButton#ApproveButton {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 {p.success}, stop:1 {p.success_dark}
        );
        border: 1px solid {p.success_dark};
        color: {p.text_primary};
        font-weight: 600;
    }}
    QPushButton#ApproveButton:disabled {{
        background: {p.bg_elevated};
        border-color: {p.border};
        color: {p.text_disabled};
    }}
    /* Spec 03 §Visual rules: pill gradient is accent-primary-1 ->
       accent-primary-2. The approved-album variant (success gradient) is
       not encoded here because QSS attribute selectors don't see album
       state without a custom Q_PROPERTY; the existing pill widget is
       always shown over a draft-style background and approval is
       conveyed by the in-row `lock` glyph and the disabled toolbar. */
    QPushButton#AlbumPill {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 {p.accent_primary_1}, stop:1 {p.accent_primary_2}
        );
        border: none;
        color: {p.text_primary};
        font-weight: 600;
        padding: 5px 14px;
    }}
    QPushButton#AlbumPill:hover {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 {p.accent_primary_2}, stop:1 {p.accent_primary_1}
        );
    }}
    /* Spec 11 focus ring: 2 px outline at accent_primary_1. Qt QSS does not
       support outline-offset, so we widen the existing border and shrink
       padding by the same amount to avoid layout shift on focus. */
    QPushButton:focus {{
        border: 2px solid {p.accent_primary_1};
        padding: 4px 11px;
    }}
    QTableView:focus {{
        border: 2px solid {p.accent_primary_1};
    }}
    QLineEdit:focus {{
        border: 2px solid {p.accent_primary_1};
        padding: 3px 7px;
    }}
    QScrollBar:vertical {{
        background-color: {p.bg_pane};
        width: 10px;
        margin: 0;
    }}
    QScrollBar:horizontal {{
        background-color: {p.bg_pane};
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background-color: {p.border_strong};
        border-radius: 5px;
        min-height: 24px;
        min-width: 24px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background-color: {p.text_tertiary};
    }}
    QScrollBar::sub-line, QScrollBar::add-line {{
        height: 0;
        width: 0;
    }}
    QScrollBar::sub-page, QScrollBar::add-page {{
        background: none;
    }}
    """.strip()


class Glyphs:
    """Single source of truth for symbolic glyphs used by widgets.
    Mirror of Spec 11 Glyphs - every widget that uses a glyph imports from here."""

    # Spec 11 §Glyphs documents the drag handle as a vertical-stacked
    # double-ellipsis. We use two adjacent U+22EE ("⋮") because there is
    # no single Unicode code point for the stacked form; horizontal
    # neighbouring approximates the visual at the available font sizes
    # (Inter / Cantarell render the pair side-by-side, which a designer
    # could mistake for a horizontal-2x3 dot grid). If a true vertical
    # stack is wanted later, swap to a custom-painted QStyledItemDelegate
    # rather than a heavier glyph - DejaVu's stacked variants are not
    # ubiquitous on user systems.
    DRAG_HANDLE = "⋮⋮"  # U+22EE x2 - Spec 05 middle pane
    UP = "▲"                  # black up-pointing triangle - Spec 04 target counter
    DOWN = "▼"                # black down-pointing triangle - Spec 04 target counter
    TOGGLE_ON = "●"           # black circle - Spec 04 selection
    TOGGLE_OFF = "○"          # white circle - Spec 04 selection
    LOCK = "\U0001f512"            # lock - Spec 03 approved-album prefix
    CHECK = "✓"               # check mark - Spec 03 active-album prefix, Spec 04 at-target
    CARET = "▾"               # black down-pointing small triangle - Spec 03 pill dropdown indicator
    SEARCH = "\U0001f50d"          # left-pointing magnifying glass - Spec 01 library search box
    PLAY = "▶"                # black right-pointing triangle - Spec 06 transport
    PAUSE = "⏸"               # double vertical bar - Spec 06 transport
    MUTE = "\U0001f507"            # speaker with cancellation stroke - Spec 06 mute
    UNMUTE = "\U0001f50a"          # speaker with three sound waves - Spec 06 unmute
