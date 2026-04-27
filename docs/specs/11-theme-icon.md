# 11 — Theme & Icon Assets

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00 · **Used by:** all UI specs

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
| `text-tertiary` | `#6e717c` | Hints, placeholder |
| `text-disabled` | `#4a4d5a` | Disabled state |
| `accent-primary-1` | `#6e3df0` | Theme primary (purple) — gradients, focus |
| `accent-primary-2` | `#c635a6` | Theme primary 2 (magenta) — gradient endpoint |
| `accent-warm` | `#f6c343` | "Now" highlight (current lyric line, at-target ✓) |
| `success` | `#10b981` | Approved state, in-album indicators |
| `success-dark` | `#059669` | Gradient endpoint of success |
| `warning` | `#f97316` | Missing tracks, alignment failed |
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

The same icon is used in three places:

1. App taskbar / launcher icon.
2. Window title-bar icon (set via `QApplication.setWindowIcon`).
3. The cover-page header of the report (Spec 09), small at the bottom: "Generated by [icon] Album Builder".

## Errors & edge cases

| Condition | Behavior |
|---|---|
| User runs Plasma with a light-theme system | Our app stays dark. The KDE per-app theme override is intentional. |
| Plasma's "follow system theme" setting | Ignored — Album Builder is dark-only in v1 (light-theme support is roadmap). |
| Icon not found at runtime (broken install) | Fallback to a Qt-shipped generic icon; window still opens. |
| User wants a different colour scheme | Roadmap: themable palette JSON in `~/.config/album-builder/themes/` that the Settings menu can pick. v1 is one fixed theme. |

## Tests

- **Unit:** `Palette` token list matches the spec hex values exactly.
- **Unit:** `qt_stylesheet()` returns a non-empty string and parses without warnings.
- **Visual regression (manual):** screenshot the main window in a headless Qt run; compare to a baseline image; flag deltas above a threshold. (Optional, since pixel-exact regression is brittle.)

## Out of scope (v1)

- Light theme.
- High-contrast / accessibility theme.
- User-customisable themes.
- Animated icon (e.g., spinning vinyl when playing).
