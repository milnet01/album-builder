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
    """.strip()
