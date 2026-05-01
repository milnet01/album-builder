# 11 — Theme & Icon Assets

**Status:** Draft · **Last updated:** 2026-04-30 · **Depends on:** 00 · **Used by:** 03, 04, 05, 06, 07, 09, 12 (every UI-bearing spec)

## Purpose

Define the dark + colourful + professional visual language of the app, and the licensing + sourcing of the application icon.

## Visual language

### Palette

| Role | Hex | Usage |
|---|---|---|
| `bg-base` | `#15161c` | Window background |
| `bg-pane` | `#1a1b22` | Pane background (library, middle, now-playing) |
| `bg-elevated` | `#1f2029` | Top bar, cards |
| `border` | `#262830` | Separators, pane borders |
| `border-strong` | `#383a47` | Button borders, inputs |
| `text-primary` | `#e8e9ee` | Body text |
| `text-secondary` | `#8a8d9a` | Labels, secondary info |
| `text-tertiary` | `#6e717c` | Hints |
| `text-placeholder` | `#9a9da8` | Empty-state placeholder text (WCAG 2.2 §1.4.3 contrast 6.4:1 vs `bg-pane`) |
| `text-disabled` | `#4a4d5a` | Disabled state. **Also the canonical "locked-grey" the album switcher uses for approved albums** (Spec 03 §Visual rules) — there is no separate `locked-grey` token; this one. |
| `accent-primary-1` | `#6e3df0` | Theme primary (purple) — gradients, focus rings |
| `accent-primary-2` | `#c635a6` | Theme primary 2 (magenta) — gradient endpoint, "in album" accent strip |
| `accent-warm` | `#f6c343` | "Now" highlight (current lyric line, at-target ✓ glyph). Also: under-target draft swatch in the album switcher (Spec 03). |
| `success` | `#10b981` | At-target draft swatch (Spec 03), in-album indicators, approve button gradient start. |
| `success-dark` | `#059669` | Gradient endpoint of success (approve button). |
| `warning` | `#f97316` | Missing tracks (Spec 04 amber accent strip), alignment failed |
| `danger` | `#ef4444` | Destructive actions, validation errors |

The "colourful" character comes from gradients between `accent-primary-1 → accent-primary-2` (used on the album-name pill, the now-playing scrubber fill, and the approve button uses `success → success-dark`).

### Gradients

- **Primary:** `linear-gradient(135deg, #6e3df0 0%, #c635a6 100%)` — used on the album pill and active states.
- **Approve:** `linear-gradient(135deg, #10b981 0%, #059669 100%)` — used on the approve button.
- **Album cover placeholder (no embedded cover):** `linear-gradient(135deg, #6e3df0 0%, #c635a6 50%, #f6c343 100%)` — three-stop, generates a recognisable placeholder.
- **Selected row "in album" strip:** 2 px left border `#c635a6` + a 90deg fade `rgba(110,61,240,0.15) → transparent`.

### Typography

- **UI font:** system sans (`"Inter", "SF Pro Text", "Segoe UI", "Cantarell", system-ui, sans-serif`). On Plasma + most modern Linux setups Cantarell or Inter are present.
- **Monospace:** for LRC editor / timestamps (`"JetBrains Mono", "Fira Code", monospace`).
- **Type scale:** 11.5 px body, 13 px section headings, 18 px page title, 24 px display (album name in the now-playing pane).
- **Weights:** 400 body, 600 emphasis, 700 display.

### Glyphs

Single-source the symbolic glyphs that other UI specs reference. These are Unicode characters (not raster icons) so they inherit the current text colour and avoid bundling additional assets.

| Glyph | Codepoint | Used by | Visual |
|---|---|---|---|
| `⋮⋮` | `U+22EE U+22EE` (two stacked vertical-ellipsis) | Spec 05 drag handle | 14 px font-size, `text-tertiary`, hover → `text-secondary` |
| `▲` / `▼` | `U+25B2` / `U+25BC` | Spec 04 target counter up/down | 12 px, `text-primary`; disabled → `text-disabled`; 28 × 28 px button hit target |
| `●` / `○` | `U+25CF` / `U+25CB` | Spec 04 selection toggle | 14 px; ON → `accent-primary-2`; OFF → `text-tertiary`; ON+missing → `warning` |
| `🔒` | `U+1F512` | Spec 03 approved album prefix, Spec 09 lock state | 13 px inline with album name |
| `✓` | `U+2713` | Spec 03 active-album prefix, Spec 04 at-target indicator, Spec 09 approve button | 13 px inline; in `success` colour for at-target, `text-primary` for active prefix |
| `▾` | `U+25BE` | Spec 03 album-switcher pill dropdown indicator | 13 px, `text-secondary` |
| `🔍` | `U+1F50D` | Library pane search box placeholder | 13 px, `text-placeholder` |
| `▶` | `U+25B6` | Spec 06 transport play button (state: paused/stopped) | 18 px, `text-primary` |
| `⏸` | `U+23F8` | Spec 06 transport pause button (state: playing) | 18 px, `text-primary` |
| `🔇` / `🔊` | `U+1F507` / `U+1F50A` | Spec 06 mute / unmute glyphs (mute toggle, also keyboard shortcut M visualiser) | 14 px, `text-primary`; muted state uses `text-secondary` |
| `x` | `U+0078` | Toast close affordance — ASCII letter `x` rendered as `×`-like via QSS context (Spec 11 implementation) | 12 px, `text-secondary`; hover → `text-primary` |
| `·` | `U+00B7` (middle dot) | Spec 09 §The approve flow step 5 success-toast separator (`Approved · report at <path>`); Spec 13 tooltip per-line bullet for usage-indicator album-name list | 11–13 px inline, `text-secondary` |

The choice of Unicode (over icon fonts or SVG) keeps the app dependency-free for these UI affordances. The `🔒` and `🔍` glyphs require a font with emoji coverage; on openSUSE Plasma the default `Noto Color Emoji` provides this; the QSS `font-family` stack falls back gracefully.

#### Constants exposed in `theme.Glyphs`

The single-source `theme.Glyphs` namespace publishes one named constant per row of the table above. Specs 03–09 reference these names (e.g. `Glyphs.CHECK`, `Glyphs.LOCK`) rather than embedding literal codepoints. Per the project's ASCII-source convention (see CLAUDE.md), the Python source uses `\Uxxxxxxxx` escapes for emoji and literal codepoints for arrows/dots.

| Name | Codepoint | Source convention |
|---|---|---|
| `Glyphs.DRAG_HANDLE` | `U+22EE U+22EE` (`⋮⋮`) | literal codepoints |
| `Glyphs.UP` | `U+25B2` (`▲`) | literal codepoint |
| `Glyphs.DOWN` | `U+25BC` (`▼`) | literal codepoint |
| `Glyphs.TOGGLE_ON` | `U+25CF` (`●`) | literal codepoint |
| `Glyphs.TOGGLE_OFF` | `U+25CB` (`○`) | literal codepoint |
| `Glyphs.LOCK` | `U+1F512` | `"\U0001F512"` escape |
| `Glyphs.CHECK` | `U+2713` (`✓`) | literal codepoint |
| `Glyphs.CARET` | `U+25BE` (`▾`) | literal codepoint |
| `Glyphs.SEARCH` | `U+1F50D` | `"\U0001F50D"` escape |
| `Glyphs.PLAY` | `U+25B6` (`▶`) | literal codepoint |
| `Glyphs.PAUSE` | `U+23F8` (`⏸`) | literal codepoint |
| `Glyphs.MUTE` | `U+1F507` | `"\U0001F507"` escape |
| `Glyphs.UNMUTE` | `U+1F50A` | `"\U0001F50A"` escape |
| `Glyphs.CLOSE` | `U+0078` (`x`) | literal ASCII letter (toast close — pragma: existing `theme.Glyphs.CLOSE = "x"` was kept rather than churning the prior Theme J closure for cosmetic perfection. The visual `×` rendering is achieved via QSS font-size + the close-button context, which most users read as a multiplication sign anyway.) |
| `Glyphs.MIDDOT` | `U+00B7` (`·`) | literal codepoint (BMP, ASCII-source convention applies) |

A consumer that wants the codepoint imports the name; a consumer that wants the rendered glyph reads the same name via the `theme.Glyphs` namespace. There is no other source of truth for these symbols anywhere in the codebase. (Names match the existing `theme.Glyphs` class verbatim — forward-only convention per CLAUDE.md, no retroactive rename.)

### Spacing & shape

- 4 px base unit. Pane padding 12 px. Row padding 8 px vertical, 10 px horizontal.
- Border radius: 4 px on rows, 6 px on inputs/transport, 8 px on panes/cards, 12 px on the window outer.
- Shadows: subtle, `0 2px 6px rgba(0,0,0,0.25)` on cards; `0 0 24px rgba(110,61,240,0.3)` glow on the now-playing cover.

### State styling

| State | Visual rule |
|---|---|
| Focus ring | 2 px outline at `accent-primary-1` with 2 px offset |
| Disabled | 50% opacity, no hover effect, `cursor: not-allowed` |
| Hover (interactive elements) | Background `bg-elevated` lighten by ~6%, transition 100 ms |
| Active (mousedown) | Background lighten by ~10% |

### Implementation

Centralised in `src/album_builder/ui/theme.py`:

- A single `Palette` dataclass with the colour tokens above.
- A `qt_stylesheet()` function returning the application-wide `QSS` string.
- Helper widgets that need bespoke painting (gradients, focus rings) override `paintEvent`.

## Icon

### Requirements (from the user)

- Free-licensed (no royalty, no attribution required ideally).
- Transparent background where applicable.
- Recognisable as a music / album / record icon.

### Sourcing strategy

In priority order, evaluated during implementation:

1. **Tabler Icons** ([github.com/tabler/tabler-icons](https://github.com/tabler/tabler-icons)) — MIT, vector, no attribution required. Candidates: `vinyl`, `disc`, `playlist`, `album`. Already SVG with transparent background.
2. **Iconoir** ([iconoir.com](https://iconoir.com)) — MIT, vector. Candidates: `music-vinyl`, `multiple-pages`.
3. **Phosphor Icons** ([phosphoricons.com](https://phosphoricons.com)) — MIT, vector, multi-weight (we'd use "duotone" for the colourful character).
4. **openclipart.org** — CC0. Used as a last-resort fallback if vector icon sets don't have a fitting design.

We do **not** use Material Icons (Apache 2 — fine for code but Google brand pressure makes them feel default-y) and we do **not** use Font Awesome (free tier requires attribution).

### Selection criteria

The icon must:
- Read clearly at 22 px (Plasma panel size) and 256 px (app drawer size).
- Have a distinctive silhouette (round disc + something extra to disambiguate from generic media-player apps).
- Be tintable to fit the theme accent (we'll likely apply a subtle gradient overlay matching the primary gradient).

### Output formats

We ship two files into `~/.local/share/icons/hicolor/`:

- `scalable/apps/album-builder.svg` — the vector source.
- `256x256/apps/album-builder.png` — a high-resolution raster, generated from the SVG with `inkscape --export-type=png --export-width=256` during install.

The `.desktop` file (Spec 12) references `album-builder` (without extension or path); KDE's icon theme machinery picks the right size.

### Branding within the app

The same icon is used in two places:

1. App taskbar / launcher icon.
2. Window title-bar icon (set via `QApplication.setWindowIcon`).

The cover-page footer of the report (Spec 09 §Cover page) reads `"Generated by Album Builder · v{__version__}"` — **without** the launcher icon inline. The icon is implicit (the report header may use it elsewhere as a small mark — see Spec 09 §Cover page); the footer is text-only so it remains legible in monochrome print. The version string is read from `src/album_builder/version.py: __version__` at *render* time, not at build / template-compile time, so a version bump propagates without a template edit.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| User runs Plasma with a light-theme system | Our app stays dark. The KDE per-app theme override is intentional. |
| Plasma's "follow system theme" setting | Ignored — Album Builder is dark-only in v1 (light-theme support is roadmap). |
| Icon not found at runtime (broken install) | Fallback to a Qt-shipped generic icon; window still opens. |
| User wants a different colour scheme | Roadmap: themable palette JSON in `~/.config/album-builder/themes/` that the Settings menu can pick. v1 is one fixed theme. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-11-NN` marker.

**Phase status — Phase 1 has implemented TC-11-01 + TC-11-02 + TC-11-04 (palette + stylesheet + placeholder contrast — see `tests/ui/test_theme.py`).** TC-11-03, TC-11-05..09 are Phase 2 (most reference UI surfaces that don't exist until Phase 2). TC-11-10..11 are Phase 4 (report integration).

- **TC-11-01** — `Palette.dark_colourful()` returns a `Palette` whose token values match the §Palette table byte-for-byte. Phase 1 ✓.
- **TC-11-02** — `qt_stylesheet(palette)` returns a non-empty string. Phase 1 ✓.
- **TC-11-03** — Stylesheet applied to the `MainWindow` produces no `QSS` parse warnings on stderr. Phase 1 ✓ (test passes implicitly; explicit assertion lands in Phase 2).
- **TC-11-04** — `text-placeholder` (`#9a9da8`) yields a contrast ratio ≥ 4.5:1 against `bg-pane` (`#1a1b22`). Verified via the WCAG luminance formula. Phase 1 ✓.
- **TC-11-05** — Focus ring: a focused `QPushButton`, `QTableView`, or `QLineEdit` renders a 2 px outline at `accent-primary-1` with 2 px offset (per §State styling).
- **TC-11-06** — Selected-row strip: a `QTableView` row with the `accent="primary"` data role renders a 2 px left border in `accent-primary-2` and the gradient background per §Gradients.
- **TC-11-07** — Missing-row strip: same row with `accent="warning"` renders the 2 px border in `warning` (`#f97316`) instead.
- **TC-11-08** — Top-bar approve button uses the `success → success-dark` gradient (`background: qlineargradient(...)`).
- **TC-11-09** — Album-cover placeholder: a track with `cover_data is None` renders a three-stop gradient (`accent-primary-1`, `accent-primary-2`, `accent-warm`) in the now-playing pane.
- **TC-11-10** — Report footer reads `__version__` at render time: mocking `__version__ = "9.9.9"` produces `Generated by Album Builder · v9.9.9` in the footer (mirrors TC-09-02).
- **TC-11-11** — Glyph table: every glyph in §Glyphs is reachable via `chr(codepoint)` and renders without `?` fallback in the chosen font stack.

(Visual regression — pixel-diff vs golden screenshots — stays manual.)

## Out of scope (v1)

- Light theme.
- High-contrast / accessibility theme.
- User-customisable themes.
- Animated icon (e.g., spinning vinyl when playing).
