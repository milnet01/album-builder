# 19 — Multiple themes + live theme switcher (ui)

**Status:** Reviewed - ready to implement · **Last updated:** 2026-07-04 · **Depends on:** 00, 03, 07, 10, 11, 12, 13 · **Blocks:** none

> **Cold-eyes loop log (2026-07-04):** 4 loops, 2-3 cold reviewers per loop (theme/
> accessibility, UI-wiring, cross-spec lenses), briefed cold each pass. Severity decayed
> strictly. **Loop 1 (HIGH):** the Spec 11 amendment was incomplete (it left "dark-only
> in v1" / "one fixed theme" / "Light theme out of scope" statements that the feature
> falsifies); the `UsageBadgeDelegate` is constructed inline with its reference discarded,
> so `set_palette` had nothing to reach; `ALLOWED_THEMES = frozenset(THEMES)` was a
> persistence->ui layer inversion. **Loop 2 (HIGH):** the `accent_warm` / `text_tertiary`
> 3:1 threshold was wrong — those render as *small* text (9pt / 11.5px), so WCAG AA needs
> 4.5:1; and an uncaught `write_ui` `OSError` in the `triggered` slot would `qFatal` the
> app (needs try/except). **Loop 3 (MEDIUM):** `text_secondary` also renders on the
> lighter `bg_elevated` (table headers) and `accent_warm` on `bg_base` — both needed
> asserting; `Depends-on` slip (02 -> 03/12); the crash-safety and settings-preservation
> paths lacked TCs. **Loop 4 (clean-ish):** 0 CRITICAL/HIGH — annotate the computed
> `text_secondary`/`bg_elevated` ratio, pin TC-19-06's line state, drop an unused
> `LibraryPane(palette=)` arg (YAGNI). All findings verified against source and fixed each
> pass. The `dark_colourful` `text_tertiary` de-emphasized-text gap (~3.5:1, pre-existing)
> is grandfathered — documented in §Accessibility, out of scope to retune here.

To be implemented across `src/album_builder/ui/theme.py` (four new `Palette` factories +
a theme registry), `src/album_builder/persistence/settings.py` (expand
`ALLOWED_THEMES`), `src/album_builder/ui/lyrics_panel.py` and
`src/album_builder/ui/library_pane.py` (a `set_palette` refresh for the two
imperative-styled widgets), and `src/album_builder/ui/main_window.py` (a menu bar with
`View -> Theme`, and a single `_apply_theme` path shared by startup and live switching).
Tests in `tests/ui/` and `tests/persistence/`.

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) · [Public API](#public-api) ·
[Behavior rules](#behavior-rules) · [UI surface](#ui-surface) ·
[Accessibility](#accessibility) · [Inputs](#inputs) · [Outputs](#outputs) ·
[Errors & edge cases](#errors--edge-cases) ·
[Cross-spec amendments](#cross-spec-amendments) · [Test contract](#test-contract) ·
[Out of scope](#out-of-scope)

## Purpose

The app ships one look — `Palette.dark_colourful()` — hardcoded at
`MainWindow.__init__` (`self.setStyleSheet(qt_stylesheet(Palette.dark_colourful()))`).
This phase adds **four** more themes (a Light theme and three dark variants) and a
**live** in-app picker (a `View -> Theme` menu) that re-styles the running window
instantly and persists the choice, so the app reopens in the last-chosen theme.

The groundwork already exists and is reused (reuse-before-rewrite): `settings.json`
carries a `ui.theme` field with an `ALLOWED_THEMES` whitelist and read/write helpers
(`read_ui` / `write_ui`, Spec 10); `qt_stylesheet(palette)` already renders the entire
app from any `Palette`; and the two widgets that paint colours *imperatively* rather
than through the global stylesheet — `LyricsPanel` (per-line lyric colours) and
`LibraryPane`'s `UsageBadgeDelegate` (usage-badge fill) — already accept an optional
`palette` at construction (the "construct-with-optional-palette" idiom). This phase adds
the missing pieces: the extra palettes, a registry, a `set_palette` refresh on the two
imperative widgets, and the menu + apply/persist path.

## Concepts

- **Palette** — the existing frozen 17-token colour dataclass (`theme.py`). A *theme* is
  one `Palette` instance produced by a factory classmethod.
- **Theme id** — the stable string persisted in `settings.json` `ui.theme` and used as
  the registry key: `dark-colourful` (existing), `light`, `dark-ocean`, `dark-ember`,
  `dark-slate`. Kebab-case, matching the existing `dark-colourful` id.
- **Theme registry** — an **ordered** mapping in `theme.py` from theme id to
  `(display_name, factory)`, the single source of truth for "what themes exist, in what
  menu order, with what human label". Both the menu builder and the settings whitelist
  derive from it (no second hand-maintained list).
- **Global-QSS widget vs imperative widget** — most widgets are styled entirely by the
  app-level stylesheet (`qt_stylesheet`), so re-applying it re-styles them with no
  per-widget work. The two *imperative* widgets (`LyricsPanel`, `LibraryPane`'s badge
  delegate) compute `QColor`s from a cached `Palette` in `paint()` / `_restyle_*`, so
  they must be handed the new palette and told to repaint. The set of imperative widgets
  is closed and enumerated (§Public API -> main_window); any *future* palette-caching
  widget must be added to the `_apply_theme` refresh list (a maintenance note, not code
  here).
- **Single apply path** — startup and live switching call the **same**
  `MainWindow._apply_theme(theme_id, *, persist)` method, so there is exactly one place
  that resolves a palette, re-styles, refreshes the imperative widgets, checks the menu
  radio, and (optionally) persists. Startup calls it with `persist=False` (the value is
  already the stored one); a menu selection calls it with `persist=True`.

## Public API

### `ui/theme.py` — palettes + registry

Four new `Palette` classmethods alongside `dark_colourful()`, each returning a fully
populated 17-token `Palette` that satisfies §Accessibility:

- `light()` — a light theme: near-white `bg_base` / `bg_pane`, dark `text_*`, the
  accent hues retuned for contrast on light surfaces.
- `dark_ocean()` — deep blue-grey backgrounds, cool cyan/teal accents.
- `dark_ember()` — warm charcoal/brown backgrounds, amber/orange accents.
- `dark_slate()` — neutral desaturated grey backgrounds, muted accents.

Exact token hex values live in code (they are tuning, not contract); the **contract** is
the §Accessibility contrast thresholds, gated by the TC-19 contrast tests. The design
direction above fixes each theme's identity.

A registry and two helpers (the single source of truth for the theme set):

```
# Ordered: dict preserves insertion order (Python 3.7+); this is the menu order.
THEMES: dict[str, tuple[str, Callable[[], Palette]]] = {
    "dark-colourful": ("Dark Colourful", Palette.dark_colourful),
    "light":          ("Light",          Palette.light),
    "dark-ocean":     ("Dark Ocean",     Palette.dark_ocean),
    "dark-ember":     ("Dark Ember",     Palette.dark_ember),
    "dark-slate":     ("Dark Slate",     Palette.dark_slate),
}

def palette_for(theme_id: str) -> Palette:
    """Resolve a theme id to its Palette; unknown id falls back to dark-colourful."""
    name_factory = THEMES.get(theme_id) or THEMES["dark-colourful"]
    return name_factory[1]()
```

(The `THEMES` annotation needs `from collections.abc import Callable` at the top of
`theme.py`, which currently imports only `dataclass`.)

`palette_for` never raises on an unknown id — it falls back to `dark-colourful` (the same
degradation `read_ui` already applies), so a corrupt/hand-edited setting can't crash the
UI. `qt_stylesheet(p: Palette)` is unchanged (it already renders any palette).

### `persistence/settings.py` — whitelist expansion

`ALLOWED_THEMES` expands from `frozenset({"dark-colourful"})` to the five theme ids,
listed **literally** in `settings.py` (**not** imported from `ui.theme`): the 4-layer
model (`CLAUDE.md` — "writes down") forbids `persistence/` importing from `ui/`, so even
though `ui.theme` is Qt-free the upward import is disallowed on layering grounds, not
Qt-freeness. A comment points at `theme.THEMES` as the canonical set, and **TC-19-05
asserts `ALLOWED_THEMES` equals the `THEMES` ids** so the two lists cannot drift silently
(the test may cross layers; production code must not). `read_ui` / `write_ui` are
otherwise unchanged — they already read/write `ui.theme` and fall back to
`dark-colourful` on an unknown value.

### `ui/lyrics_panel.py` — `LyricsPanel.set_palette`

`set_palette(self, palette: Palette) -> None` — assign `self._palette = palette` and
re-run the per-line restyle (`_restyle_items()`, which repaints every line via
`_restyle_at`, the method that writes each line's foreground brush from `self._palette`)
so the current/past/future line colours repaint in the new palette. The existing
optional-palette constructor is unchanged.

### `ui/library_pane.py` — `LibraryPane.set_palette`

The `UsageBadgeDelegate` is today constructed inline and its reference discarded
(`self.table.setItemDelegateForColumn(used_col, UsageBadgeDelegate(self.table))`); promote
it to a stored attribute `self._usage_delegate` so `set_palette` can reach it.
`set_palette(self, palette: Palette) -> None` — set `self._usage_delegate._palette =
palette` (the delegate paints the badge fill from `palette.accent_primary_1`) and repaint
via `self.table.viewport().update()`, so usage badges recolour. `LibraryPane` keeps its
bare constructor (it builds the delegate with the default palette); `MainWindow`'s startup
`_apply_theme` immediately calls `set_palette` before first paint, so the `set_palette`
path already covers a non-default startup theme — no palette constructor arg is added
(YAGNI).

### `ui/main_window.py` — menu bar + apply path

- **Menu bar** (`self.menuBar()`): three menus.
  - **File** — "New Album" (`_on_new_album`), "Quit" (`self.close`). These wrap the
    *existing* handlers/shortcuts (Ctrl+N already maps to new-album; Ctrl+Q to quit);
    the menu adds discoverable entry points, no new behavior.
  - **View -> Theme** — a submenu with one **checkable** `QAction` per registry entry
    (label = display name), all in a single `QActionGroup` (exclusive, so exactly one is
    checked = the radio look). Triggering an action calls
    `_apply_theme(theme_id, persist=True)`.
  - **Help** — "Keyboard shortcuts" (`_show_help`, the existing F1 handler).
- **`_apply_theme(self, theme_id: str, *, persist: bool) -> None`** — the single apply
  path:
  1. `palette = palette_for(theme_id)`.
  2. `self.setStyleSheet(qt_stylesheet(palette))` — re-styles every global-QSS widget.
  3. Refresh the enumerated imperative widgets:
     `self.now_playing_pane.lyrics_panel.set_palette(palette)` and
     `self.library_pane.set_palette(palette)`.
  4. Store `self._current_theme = theme_id` and `setChecked(True)` the matching menu
     action. Because the actions wire `triggered` (fires on user activation only, **not**
     on programmatic `setChecked`), this programmatic check cannot re-enter `_apply_theme`
     — no guard flag is needed.
  5. If `persist`: write the choice **wrapped in try/except**. `_apply_theme` runs inside
     a `triggered` slot, and PyQt6 escalates an uncaught slot exception to `qFatal`
     (aborting the app — the codebase's approve path already documents this and uses a
     catch-all). `write_ui`'s only realistic failure is `OSError` from the atomic write,
     so a narrow `except OSError` suffices (the qFatal risk is that *any* uncaught slot
     exception aborts; catching the one that can occur here is enough). It must be caught
     and toasted (via `MainWindow._show_toast`), not allowed to propagate. On the happy
     path:
     `write_ui(UiSettings(open_report_folder_on_approve=<current from self._ui_settings>,
     theme=theme_id))`, then update `self._ui_settings` so a later approve reads the
     current value. Steps 1-4 (the visual switch) have already applied regardless; only
     persistence is best-effort.
- **Construction change** — the hardcoded
  `self.setStyleSheet(qt_stylesheet(Palette.dark_colourful()))` is removed; after the
  menu bar and the palette-caching widgets exist, `MainWindow.__init__` calls
  `self._apply_theme(self._ui_settings.theme, persist=False)` once, so the persisted
  theme is applied on launch through the same path as a live switch.

## Behavior rules

- **Live switch.** Selecting a theme in `View -> Theme` re-styles the whole window
  immediately (no restart): the stylesheet re-applies to every global-QSS widget, and the
  two imperative widgets recolour via `set_palette`. The choice is written to
  `settings.json` so the next launch restores it.
- **Startup.** `MainWindow` reads `ui.theme` (via the already-cached `self._ui_settings`)
  and applies it once at the end of construction. An unknown/absent value has already
  degraded to `dark-colourful` in `read_ui`; `palette_for` degrades again as a
  belt-and-braces guard.
- **Persistence is one field.** Only `ui.theme` changes; `write_ui` preserves
  `open_report_folder_on_approve`. Writing is a normal atomic settings write (Spec 10);
  no debounce is needed (theme changes are rare, user-initiated).
- **Menu reflects state.** After any apply (startup or switch) exactly one theme action
  is checked — the current theme. Re-selecting the already-current theme re-applies
  harmlessly (idempotent) and re-persists the same value.
- **No per-widget palette drift.** Because startup and switch share `_apply_theme`, a new
  imperative widget added later cannot be styled-correctly-at-startup-but-stale-on-switch
  (or vice versa) — it is added to the one refresh list and both paths cover it.

## UI surface

```
+-----------------------------------------------------------+
| File            View            Help                      |   <- new QMenuBar
|                  +-- Theme >                               |
|                        (*) Dark Colourful                  |   <- QActionGroup,
|                        ( ) Light                           |      exactly one checked
|                        ( ) Dark Ocean                      |
|                        ( ) Dark Ember                      |
|                        ( ) Dark Slate                      |
+-----------------------------------------------------------+
| (existing TopBar + tabs unchanged)                        |
```

- The menu bar sits above the existing central widget (TopBar + tabs); the existing
  layout, shortcuts, and tabs are unchanged.
- Theme actions are labelled with their registry display names, listed in registry
  order, with `dark-colourful` first (the current default).
- **Accessibility:** the menu bar and actions are keyboard-navigable (Qt default: Alt to
  focus the menu bar, arrows to move, Enter to activate). Each theme action carries its
  display name as its text (screen-reader-announced). No new global shortcut is added.

## Accessibility

Every theme's `Palette` must meet WCAG 2.2 AA contrast (SC 1.4.3; the 4.5:1 / 3:1
thresholds match the "WCAG 2.2 AA" label already on the shipped palette and Spec 11) on
the colour pairs the UI renders. The tokens' actual render sizes were checked against
`theme.py` / `lyrics_panel.py`: `PaneTitle` is **9pt** and the lyric lines are **11.5px**
— none are WCAG "large text" (>= 18pt / 14pt-bold), so text pairs take the **4.5:1**
normal-text bar. The hard contract (each a TC-19 assertion computing the ratio from the
two hex values via the WCAG relative-luminance formula):

**Body-text pairs — 4.5:1, all five themes** (dark-colourful already satisfies these).
The background in each pair is the surface the token actually paints on (checked against
`theme.py`), not just `bg_pane` — a mid-grey on the *lighter* `bg_elevated` is the harder
case for a dark theme, so it is asserted explicitly:
- `text_primary` on `bg_pane` and on `bg_base`.
- `text_secondary` on `bg_pane` (metadata) **and on `bg_elevated`** (`QHeaderView::section`
  table headers paint `text_secondary` on the lighter `bg_elevated`; dark-colourful is
  ~4.9:1 here — its tightest passing pair).
- `text_placeholder` on `bg_pane` — this is **Spec 11's TC-11-04** contract
  (dark-colourful 6.4:1), generalised to every theme.
- `accent_warm` on `bg_pane` **and on `bg_base`** — `accent_warm` renders small text in
  several places (`QLabel#PaneTitle` 9pt headers; the bold now-lyric line at 11.5px;
  `QLabel#TransportBuffering` on `bg_base`; among others), so it takes the 4.5:1 bar (not
  3:1). dark-colourful's bright gold passes easily; a light theme must pick a **deeper
  amber**.

**De-emphasized text — 4.5:1 for the four new themes; dark-colourful grandfathered:**
- `text_tertiary` on `bg_pane` — used for small, still-readable de-emphasized text
  (upcoming lyric lines at 11.5px, `NowPlayingMetaSecondary` at 9pt), so it needs 4.5:1.
  The **four new** themes are designed to meet it. The **existing** dark-colourful ships
  `text_tertiary` below the 4.5:1 bar (the `theme.py` code comment flags it as failing
  accessibility for subtle copy); Spec 19 does **not** retune the shipped palette —
  that would alter the established look and break Spec 11's byte-for-byte TC-11-01 — so
  dark-colourful is a documented **pre-existing exception** (a dedicated accessibility
  pass, out of scope here, could close it). TC-19-04 asserts 4.5:1 for the four new
  themes and pins dark-colourful at its current ratio.

**Status/indicator colours rendered as glyph/text — 3:1, the four new themes:**
- `success` (the at-target check glyph), `warning` (alignment-failed status), `danger`
  (validation errors) render as small coloured glyphs/status text (Spec 11), so each new
  theme keeps them **>= 3:1** on `bg_pane` (indicators, not body copy — 3:1 is the
  applicable floor). dark-colourful's are unchanged.

**Exempt:** `text_disabled` (the deliberately faded *past* lyric lines — inactive/
disabled text is WCAG-exempt) and accent/border colours that never render text (focus
rings, gradient stops) — kept visually distinct, not asserted numerically.

## Inputs

- User: selecting a theme action in `View -> Theme`; using File/Help menu items (wrapping
  existing actions).
- `settings.json` `ui.theme` at startup (via `read_ui` -> `self._ui_settings`).

## Outputs

- The re-applied application stylesheet (all global-QSS widgets recolour) and the two
  imperative widgets' repaint.
- A `settings.json` write of `ui.theme` on a live switch (persisted choice).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `ui.theme` is an unknown/removed id at startup | `read_ui` already degrades to `dark-colourful`; `palette_for` degrades again. App launches in `dark-colourful`; no crash. |
| `settings.json` hand-edited to a valid non-default theme | `read_ui` returns it (now in the expanded whitelist); startup applies it. |
| Re-selecting the current theme | `_apply_theme` re-applies idempotently and re-persists the same id; the menu radio stays on it. |
| `write_ui` fails (disk error, `OSError`) | `_apply_theme` catches it (step 5) and toasts; the app does **not** crash (an uncaught slot exception would `qFatal`). The visual switch already applied; the choice just may not persist to the next launch. |
| A future palette-caching widget is added but not registered in `_apply_theme` | It would style correctly at startup only if it reads the palette itself; the §Concepts maintenance note flags that every imperative widget must join the refresh list. Not a runtime error, a maintenance contract. |
| Programmatic `setChecked` on the menu radio during `_apply_theme` | The actions wire `triggered` (not `toggled`), which does **not** fire on programmatic `setChecked` — so the startup/programmatic check never re-enters `_apply_theme`. No guard flag needed. |

## Cross-spec amendments

- **Spec 10 (`10-persistence.md`)** — the `settings.json` `ui.theme` schema row currently
  states `dark-colourful` is the only valid value in v1 (mirrored by the
  `ALLOWED_THEMES` docstring in `settings.py`). Update it to list the five valid ids (or
  reference the `theme.THEMES` registry as canonical), keeping the unknown-value ->
  `dark-colourful` fallback rule.
- **Spec 11 (`11-theme-icon.md`)** — currently describes a single dark palette and
  explicitly scopes multi-theme *out*. Add: `theme.py` exposes multiple `Palette`
  factories via the `THEMES` registry, selectable live through `View -> Theme`, persisted
  in `ui.theme`; the two imperative-styled widgets refresh via `set_palette`. Then amend
  the now-false statements **precisely — reword, do not blanket-delete** (some rows also
  encode still-true behaviour):
  - §Purpose (11:7) "the dark + colourful + professional visual language" — reword so
    dark-colourful reads as one of several themes.
  - §Errors row 11:165 ("Our app stays dark" under a light *system* theme) and 11:166
    ("dark-only in v1 ... light-theme support is roadmap") — reword: the **still-true**
    part is "Album Builder does not auto-follow the OS/Plasma theme" (Spec 19
    §Out-of-scope keeps OS-follow out); the **false** part ("dark-only" / "roadmap") goes.
    Leave 11:167 ("Icon not found at runtime") untouched.
  - §Errors row 11:168 — drop "v1 is one fixed theme"; the row's user-authored-palette-JSON
    roadmap sentence stays (user-customisation is still out of scope), but the picker is
    now `View -> Theme` for the five built-ins, not a future roadmap item.
  - §Out-of-scope 11:192 "Light theme" -> **delivered by Spec 19**. 11:193 "High-contrast
    / accessibility theme" and 11:194 "User-customisable themes" **stay** out of scope
    (Spec 19 ships five fixed WCAG-AA themes, not a dedicated high-contrast mode or
    user-authored palettes).
  Spec 11's TC-11-04 placeholder-contrast contract and its icon content are unaffected.
- **Spec 00 index** gains the Spec 19 row (and the Spec 18 row, whose doc exists but was
  not yet indexed).

No `domain/` change. `settings.py` (persistence) gains only the whitelist expansion.

## Test contract

Tests reference each clause via `# Spec: TC-19-NN`. Palette/registry/contrast tests live
in `tests/ui/` (they need only `Palette`, no QApplication); settings-whitelist tests in
`tests/persistence/`; menu + apply-path tests in `tests/ui/` against a real `MainWindow`.

- **TC-19-01** — `THEMES` contains exactly the five ids `dark-colourful`, `light`,
  `dark-ocean`, `dark-ember`, `dark-slate`, in that insertion order, each mapping to a
  `(display_name: str, factory)` whose factory returns a `Palette`.
- **TC-19-02** — `palette_for(id)` returns the registry palette for each known id, and
  returns the `dark-colourful` palette for an unknown id (e.g. `palette_for("nope")`)
  **without raising**.
- **TC-19-03** — Each of the five themes is a fully-populated `Palette` (all 17 fields
  non-empty valid hex strings) — a parametrised test over `THEMES`.
- **TC-19-04** — WCAG contrast, computed from the hex pair via the WCAG
  relative-luminance formula (a small test helper), parametrised over themes:
  - **All five themes, >= 4.5:1:** `text_primary` vs `bg_pane` and vs `bg_base`;
    `text_secondary` vs `bg_pane` **and vs `bg_elevated`**; `text_placeholder` vs
    `bg_pane`; `accent_warm` vs `bg_pane` **and vs `bg_base`**.
  - **Four new themes (`light`, `dark-ocean`, `dark-ember`, `dark-slate`), >= 4.5:1:**
    `text_tertiary` vs `bg_pane`. `dark-colourful` is asserted at its current
    (pre-existing, documented) ratio, **not** 4.5:1 — a grandfathered exception (§Accessibility).
  - **Four new themes, >= 3:1:** `success` / `warning` / `danger` vs `bg_pane`
    (status-glyph indicators).
  Every pair `dark-colourful` is asserted on must keep passing (it satisfies all except
  the grandfathered `text_tertiary`).
- **TC-19-05** — `ALLOWED_THEMES` equals the set of `THEMES` ids (all five); `read_ui`
  returns a hand-set valid non-default theme (e.g. `light`) unchanged, and degrades an
  unknown value to `dark-colourful` (extends the existing Spec 10 whitelist test).
- **TC-19-06** — `LyricsPanel.set_palette(p)` updates `palette_for_lyrics()` to `p`;
  after a set_palette to a different theme, a re-styled line's foreground reflects the new
  palette's colour — assert via the list item's foreground brush
  (`item.foreground().color()`), where `_restyle_at` writes the palette colour. Pin a
  definite line state first — `set_current_line(0)` so line 0 is the "now" line coloured
  `accent_warm` — and pick two themes whose `accent_warm` differs, so the assertion cannot
  pass vacuously (with no current line, every line is "future"/`text_tertiary`).
  (`line_state` is palette-independent — it returns past/now/future from the line index —
  so it cannot verify a colour change.)
- **TC-19-07** — `LibraryPane.set_palette(p)` updates the `UsageBadgeDelegate`'s cached
  palette to `p` (assert the delegate's `_palette is p` or its `accent_primary_1`
  source), so subsequent badge paints use the new accent.
- **TC-19-08** — In a constructed `MainWindow`, the menu bar has `File`, `View`, `Help`
  menus; `View` has a `Theme` submenu with exactly five checkable actions in registry
  order, in one exclusive `QActionGroup`, with exactly one checked.
- **TC-19-09** — Triggering the `Light` theme action calls `_apply_theme("light",
  persist=True)`: the window stylesheet equals `qt_stylesheet(palette_for("light"))`
  (assert `self.styleSheet() == qt_stylesheet(palette_for("light"))` — robust and
  hex-agnostic); both imperative widgets now hold the light palette (spy `set_palette` or
  assert `now_playing_pane.lyrics_panel.palette_for_lyrics()` / the delegate `_palette`);
  the `Light` action is now the checked one; and `write_ui` persisted `theme="light"`
  **while preserving `open_report_folder_on_approve`** — set that flag `False` first, switch
  theme, and assert the persisted flag is still `False` (guards against a hardcoded `True`
  silently re-enabling it). Spy `write_ui` or read the settings back.
- **TC-19-10** — Startup applies the persisted theme: a `MainWindow` built with
  `read_ui` returning `theme="dark-ocean"` ends with the `Dark Ocean` action checked and
  `self.styleSheet()` equal to `qt_stylesheet(palette_for("dark-ocean"))`, via the single
  `_apply_theme(..., persist=False)` call — and **no** `write_ui` occurs at startup
  (persist=False).
- **TC-19-11** — Re-selecting the current theme is idempotent: triggering the
  already-checked action re-applies without error and re-persists the same id; exactly
  one action remains checked.
- **TC-19-12** — Menu items wrap existing handlers (spy each): `File -> New Album`
  invokes `_on_new_album` (same as Ctrl+N), `File -> Quit` invokes `self.close` (same as
  Ctrl+Q), and `Help -> Keyboard shortcuts` invokes `_show_help` (F1). These menus add
  discoverable entry points, not new behavior.
- **TC-19-13** — Crash-safety: with `write_ui` monkeypatched to raise `OSError`,
  triggering a theme switch does **not** propagate/crash (an uncaught slot exception would
  `qFatal`), surfaces a toast (`_show_toast`), and the visual switch still applied
  (`self.styleSheet()` == the new theme's stylesheet). The persisted value simply did not
  update.

## Out of scope

- Per-widget / per-tab theme overrides; a theme applies app-wide.
- Custom user-authored palettes or a colour-editor UI (only the five built-in themes).
- System-theme following (auto light/dark from the OS) — could be a later increment; this
  phase is an explicit user choice only.
- Threading the palette into Phase E's future `PlayerPane` / second `LyricsPanel` /
  `NowPlayingCard` widgets — those do not exist yet (Spec 18 is unimplemented). When
  Phase E lands, its palette-caching widgets (a second `LyricsPanel`) must be added to
  the `_apply_theme` refresh list; `NowPlayingCard` is global-QSS-styled (its transparent
  background + the `NowPlaying*` label rules recolour automatically) and needs no
  set_palette. Recorded here so the Phase E implementer wires it.
- Animating the theme transition; the switch is instantaneous.
- Changing the app *icon* per theme (Spec 11 icon content is untouched).
