"""Symbolic glyphs used by widgets - Spec 11, Glyphs section.

Lives outside ui/ so services can use it too (docs/design.md, MUSI-0383).
ui.theme re-exports it, so `from album_builder.ui.theme import Glyphs` still works.
No Qt import.
"""

from __future__ import annotations


class Glyphs:
    """Single source of truth for symbolic glyphs used by widgets.
    Mirror of Spec 11 Glyphs - widgets import it via ui.theme, services from here."""

    # Spec 11 §Glyphs documents the drag handle as a vertical-stacked
    # double-ellipsis. We use two adjacent U+22EE ("⋮") because there is
    # no single Unicode code point for the stacked form; horizontal
    # neighbouring approximates the visual at the available font sizes
    # (Inter / Cantarell render the pair side-by-side, which a designer
    # could mistake for a horizontal-2x3 dot grid). If a true vertical
    # stack is wanted later, swap to a custom-painted QStyledItemDelegate
    # rather than a heavier glyph - DejaVu's stacked variants are not
    # ubiquitous on user systems.
    # Convention (CLAUDE.md ASCII-only source rule):
    #   - BMP codepoints (U+0000..U+FFFF) live as literal characters; ruff's
    #     RUF001/002/003 confusable rules cover the punctuation traps.
    #   - Astral / emoji-range codepoints (U+1Fxxx) use \Uxxxxxxxx escapes
    #     so the source remains 7-bit ASCII even when an editor or hook
    #     can't render the emoji glyph.
    DRAG_HANDLE = "⋮⋮"          # U+22EE x2 - Spec 05 middle pane drag handle
    UP = "▲"                    # U+25B2 - Spec 04 target counter up
    DOWN = "▼"                  # U+25BC - Spec 04 target counter down
    TOGGLE_ON = "●"             # U+25CF - Spec 04 selection toggle (on)
    TOGGLE_OFF = "○"            # U+25CB - Spec 04 selection toggle (off)
    LOCK = "\U0001f512"         # U+1F512 - Spec 03 approved-album prefix
    CHECK = "✓"                 # U+2713 - Spec 03/04/07 (active prefix, at-target, LRC ready)
    CARET = "▾"                 # U+25BE - Spec 03 album-switcher dropdown indicator
    SEARCH = "\U0001f50d"       # U+1F50D - Spec 01 library search-box placeholder
    PLAY = "▶"                  # U+25B6 - Spec 06 transport play
    PAUSE = "⏸"                 # U+23F8 - Spec 06 transport pause
    MUTE = "\U0001f507"         # U+1F507 - Spec 06 mute
    UNMUTE = "\U0001f50a"       # U+1F50A - Spec 06 unmute
    # Spec 16 transport controls (Phase C). Arrows as literal codepoints
    # (like PLAY/PAUSE); shuffle/repeat as emoji \U escapes (like MUTE/UNMUTE).
    SKIP_PREV = "⏮"             # U+23EE - Spec 16 previous-track
    SKIP_NEXT = "⏭"             # U+23ED - Spec 16 next-track
    SHUFFLE = "\U0001f500"      # U+1F500 - Spec 16 shuffle toggle
    REPEAT_ALL = "\U0001f501"   # U+1F501 - Spec 16 repeat off/all
    REPEAT_ONE = "\U0001f502"   # U+1F502 - Spec 16 repeat one
    # Spec 11 doesn't enumerate a close glyph; ASCII "x" is the long-standing
    # convention for close-button affordances (matches macOS, GTK, web UIs)
    # and renders identically across all font stacks. (Theme J closure.)
    CLOSE = "x"                 # Spec 06 toast close button
    # Middle-dot separator (U+00B7) used in Spec 09 §The approve flow step 5
    # success toast format ("Approved · report at <path>") and similar
    # "key1 · key2" UI strings. Widely available in system fonts.
    MIDDOT = "·"
