# 25 — Languages, including right-to-left (i18n)

**Status:** draft · **Last updated:** 2026-09-28 · **Roadmap:** MUSI-0368 · **Depends on:** 00, 09, 10, 11, 16, 19 · **Amends:** 09, 10, 16, 23, 24

> **Cold-eyes loop log:** none yet.

To be implemented in a new `src/album_builder/i18n.py`, a new
`src/album_builder/translations/` directory of JSON catalogs, the language resolution
in `src/album_builder/app.py`, a *View > Language* menu in `ui/main_window.py`, a
`ui.language` key in `persistence/settings.py`, and the report template
`services/templates/report.html.j2` with `services/report.py`. Every module under
`ui/` that shows text wraps it. Tests in `tests/` (a new `tests/test_TC_25_*.py` family).

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) · [Public API](#public-api) ·
[Behavior rules](#behavior-rules) · [UI surface](#ui-surface) · [Inputs](#inputs) ·
[Outputs](#outputs) · [Errors & edge cases](#errors--edge-cases) ·
[Cross-spec amendments](#cross-spec-amendments) · [Test contract](#test-contract) ·
[Out of scope](#out-of-scope)

## Purpose

The app shows English only. The user asked (2026-09-28) for multiple languages
"including RTL languages", and chose the first set: **Afrikaans, Arabic, Hebrew,
Spanish, French, German and Portuguese**, with English kept. Arabic and Hebrew read
right to left, so the layout must mirror for them, not only the words.

The design keeps the moving parts few: one Python helper, one JSON file per language,
and a language that takes effect on the next start. It adds no build step, so the
AppImage and the Windows bundle carry translations the same way they carry the report
template.

## Concepts

- **Source string** — the English text as written in the code, e.g. `"New Album"`. It
  is also the lookup key. English needs no catalog.
- **Catalog** — `translations/<code>.json`, a flat JSON object mapping each source
  string to its translation. One per supported language. The reserved key
  `"@language_name"` holds the language's name in its own script ("Deutsch",
  "العربية"), used by the menu.
- **Language code** — one of `en`, `af`, `ar`, `he`, `es`, `fr`, `de`, `pt`. The
  supported set is exactly the codes with a catalog, plus `en`.
- **Active language** — resolved once at startup, before any widget is built, and fixed
  for the life of the process.
- **RTL language** — `ar` and `he`. For these the application's layout direction is
  right to left.
- **Placeholder** — a `str.format` field such as `{name}` or `{count}`. A translation
  carries exactly the placeholders its source string carries.

## Public API

### `i18n.py` — the helper (new, no Qt import)

- `SUPPORTED: tuple[str, ...]` — `("en", "af", "ar", "he", "es", "fr", "de", "pt")`.
- `RTL: frozenset[str]` — `{"ar", "he"}`.
- `set_language(code: str) -> None` — loads `translations/<code>.json` (nothing for
  `en`) into the module's active catalog. An unsupported code, or a catalog that is
  missing or unreadable, leaves English active and logs a warning; it never raises.
- `current_language() -> str` — the active code.
- `tr(source: str, /, **fields) -> str` — returns the active catalog's translation of
  `source`, or `source` itself when the catalog has no entry, then applies
  `str.format(**fields)` when `fields` are given. Code calls it with a string literal
  as the first argument, so the catalog-coverage test can find every call.
- `language_name(code: str) -> str` — the catalog's `"@language_name"`, `"English"`
  for `en`.
- `resolve(setting: str, system_code: str) -> str` — the code to activate:
  `setting` when it is in `SUPPORTED`; else `system_code` when it is in `SUPPORTED`;
  else `"en"`. `setting == "system"` takes the second branch.

`tr` is the one name every module imports (`from album_builder.i18n import tr`). A
module-level constant that holds display text (a column header list, for instance) is
translated where it is shown, not where it is defined, because module constants are
built at import time, before `set_language` runs.

### `translations/*.json` (new)

One file per non-English code in `SUPPORTED`. UTF-8, a flat object, keys sorted. Every
key is a source string the code passes to `tr` (or the report template passes to its
`_`), plus `"@language_name"`. The catalogs shipped by this spec are machine-drafted;
see §Out of scope.

### `persistence/settings.py` — `ui.language`

`UiSettings` gains `language: str = "system"`. `read_ui` accepts `"system"` or a code
in an `ALLOWED_LANGUAGES` whitelist, listed literally for the same layering reason as
`ALLOWED_THEMES`; anything else reads as `"system"`. `write_ui` writes it back beside
`theme`.

### `app.py` — resolution at startup

After `QApplication` is constructed and before the single-instance lock hands off or
any window is built:

1. `code = i18n.resolve(read_ui().language, QLocale.system().name().split("_")[0])`.
2. `i18n.set_language(code)`.
3. Install a `QTranslator` for Qt's own strings (dialog buttons such as Yes / No /
   Cancel) from `QLibraryInfo.path(TranslationsPath)`, file `qtbase_<code>`, except
   `pt`, which loads `qtbase_pt_BR`. Measured 2026-09-28 in the venv: `de`, `pt_BR`
   and `he` load and translate `"&Yes"`; Qt ships no `qtbase_af`. When no file loads,
   Qt's buttons stay English and nothing is reported.
4. `app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)` when `code in i18n.RTL`.

### `services/report.py` + `report.html.j2`

The Jinja environment gets `_ = i18n.tr` as a global, and every piece of fixed text in
the template becomes `{{ _("...") }}`. The root element becomes
`<html lang="{{ lang }}" dir="{{ dir }}">`, with `lang` the active code and `dir`
`"rtl"` or `"ltr"`. `approved_date_human` comes from
`QLocale(code).toString(date, QLocale.FormatType.LongFormat)`, which names the month in
the active language (measured: `ar` gives Arabic month and digits, `de` gives
"Montag, 28. September 2026"). The report's file name keeps its ISO date and is not
translated (Spec 10 §Atomic pair keys on it).

### `ui/main_window.py` — *View > Language*

A **Language** submenu under **View**, after **Theme**: "System default", then one
checkable action per code, each labelled with `language_name(code)`, in an exclusive
`QActionGroup`. The action matching the stored setting is checked. Choosing one writes
`ui.language` and shows a toast, in the language currently active: "Restart Album
Builder to use {language}." Choosing the stored value again does nothing.

## Behavior rules

- **What is translated.** Every piece of text the app itself writes for a person to
  read: window and dialog titles, menus, buttons, labels, tab names, placeholders,
  tooltips, toasts, message-box text, column headers, status pills, accessible names
  and descriptions, and the report's fixed text.
- **What is not.** Track metadata, album and playlist names, file and folder names,
  lyrics, log messages, the text of an exception appended to a message, command-line
  output (`--version`, `--selftest`), M3U contents, and `settings.json` / `state.json`
  keys and values.
- **Composed messages** use placeholders, never concatenation, so a translation can put
  the name where its grammar needs it: `tr("Restored '{name}'.", name=album.name)`.
- **Counts.** A message whose wording depends on a count uses one source string per
  wording the English needs ("1 other approved album" / "{count} other approved
  albums"). Languages with more plural forms (Arabic has six) use the nearest of those
  two. This is a known limitation, not a defect.
- **Digits and durations** keep the forms the code already produces (`3:07`, `12`),
  in every language. Only the report's long date is localised.
- **RTL mirroring.** Under an RTL language Qt mirrors layouts: panes, splitters,
  menus, table columns and text alignment follow the application direction. One widget
  is pinned left to right, the way media apps keep playback controls unmirrored: the
  `TransportBar` (its button order, and its scrubber, which moves with time). It sets
  `setLayoutDirection(Qt.LayoutDirection.LeftToRight)` on itself.
- **Glyphs** from `theme.Glyphs` are not translated and not mirrored.

## UI surface

```
View
 ├─ Theme          ▸ ...
 └─ Language       ▸ ● System default
                     ○ English
                     ○ Afrikaans
                     ○ العربية
                     ○ Deutsch
                     ○ Español
                     ○ Français
                     ○ עברית
                     ○ Português
```

The order is `SUPPORTED` order with "System default" first. The native names come from
the catalogs, so the menu reads correctly whatever language is active.

## Inputs

- `settings.json` → `ui.language` (Spec 10).
- The system locale, via `QLocale.system()`.
- `translations/<code>.json`.

## Outputs

- Every widget's text, as listed in §Behavior rules.
- The application layout direction.
- The report's fixed text, `lang` and `dir` attributes and long date.
- `settings.json` → `ui.language`, written when the user picks a language.

## Errors & edge cases

| Case | Behaviour |
|---|---|
| `ui.language` holds an unknown value | Read as `"system"` (§Public API → settings). |
| System locale not in `SUPPORTED` (e.g. `ja`) | English. |
| A catalog file is missing or not valid JSON | English, one logged warning; the app starts. |
| A catalog lacks a key | That string shows in English. The coverage test (TC-25-03) keeps shipped catalogs complete. |
| A translation's placeholders differ from its source's | Caught by TC-25-04; at runtime `str.format` would raise, so shipped catalogs must pass it. |
| No `qtbase_<code>` file (`af`) | Qt's own buttons stay English. |
| RTL text inside an LTR widget (an Arabic track title in the transport) | Shown as the platform's bidi rules draw it; not special-cased. |

## Cross-spec amendments

Each is edited in the same change set as this spec's implementation.

- **Spec 10** §`settings.json` schema: add the `ui.language` row — `"system"` or a code
  in `SUPPORTED`; unknown values read as `"system"`.
- **Spec 09**: the report's fixed text is translated and its root element carries
  `lang` / `dir`; `approved_date_human` is locale-formatted; the file name is unchanged.
- **Spec 16**: the `TransportBar` is pinned left to right under an RTL language.
- **Spec 19**: the *View* menu gains *Language* after *Theme*.
- **Specs 23 and 24** (AppImage, Windows bundle): the `translations/` directory ships
  with the package, as `services/templates/` does. The PyInstaller spec must list it
  as data; the AppImage copies the package tree and needs no change beyond a check.

## Test contract

Each clause is a testable assertion; tests reference its TC ID via a `# Spec: TC-25-NN`
marker.

- **TC-25-01** — With no language set, `tr("New Album") == "New Album"`, and
  `tr("Restored '{name}'.", name="X") == "Restored 'X'."`.
- **TC-25-02** — `set_language("de")` makes `tr` return the German entry for a key the
  `de` catalog holds; `set_language("xx")` and a catalog path that does not exist both
  leave English active without raising.
- **TC-25-03** — Coverage: the set of string literals passed as the first argument to
  `tr(...)` anywhere under `src/album_builder/` (found by walking the AST) plus every
  `_("...")` in `report.html.j2`, **equals** each catalog's key set minus
  `"@language_name"` — no missing key and no stale one. A call whose first argument is
  not a literal fails the test.
- **TC-25-04** — For every catalog entry, the set of `str.format` field names in the
  translation equals the set in its source string.
- **TC-25-05** — `resolve`: `("system", "de") -> "de"`, `("system", "ja") -> "en"`,
  `("fr", "de") -> "fr"`, `("klingon", "de") -> "de"`.
- **TC-25-06** — Settings: `ui.language` round-trips through `write_ui` / `read_ui`;
  `"klingon"` reads as `"system"`; a settings file without the key reads as `"system"`.
- **TC-25-07** — Coverage of built widgets: with a pseudo catalog installed that maps
  every key to `"⟦" + key + "⟧"`, a `MainWindow` over the test library shows no English
  UI text. Walk every `QLabel`, `QAbstractButton`, `QAction`, `QTabBar` tab,
  `QHeaderView` section, `QLineEdit` placeholder, tooltip and accessible name and
  description; each non-empty value either contains `⟦` or is on an allow-list of
  non-translatable forms (glyph-only text, digits and `:`, track metadata from the test
  library). *Breaks if:* a new label is added without `tr`.
- **TC-25-08** — RTL: after the startup sequence with `ar`,
  `QApplication.layoutDirection() == RightToLeft`, and the `TransportBar`'s own
  `layoutDirection() == LeftToRight`. With `de` the application is left to right.
- **TC-25-09** — Menu: *View > Language* lists "System default" then one action per
  `SUPPORTED` code labelled with `language_name`; triggering "Deutsch" writes
  `ui.language == "de"` and shows the restart toast; triggering the checked action
  writes nothing.
- **TC-25-10** — Report: rendered with `he` active, the HTML root carries `lang="he"`
  and `dir="rtl"`, a fixed heading appears in Hebrew, and the PDF renders to a
  non-empty file.
- **TC-25-11** — Qt's own strings: with `de` active, a `qtbase_de` translator is
  installed (`QApplication` translation of `"&Yes"` in context `QPlatformTheme` is not
  `"&Yes"`); with `af` active startup completes and no translator is installed.

## Out of scope

- **Checked translations.** The shipped catalogs are machine-drafted. A native-speaker
  review of each is a separate item; until then the README says so.
- **Switching language without a restart.** Every widget would need to rebuild its
  text on a signal; the restart toast avoids that.
- **Arabic's full plural rules**, and localised digits in the UI (§Behavior rules).
- **More languages.** Adding one is a new catalog plus a code in `SUPPORTED` and
  `ALLOWED_LANGUAGES`; TC-25-03 then demands the catalog be complete.
- Translating track metadata, file names or log output.
