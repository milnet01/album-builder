# 09 — Approval & Report

**Status:** Draft · **Last updated:** 2026-04-30 · **Depends on:** 00, 01, 02, 04, 05, 08, 10, 11 · **Lifecycle:** triggered by Spec 02's approve transition

## Purpose

Generate an artist-facing deliverable (PDF + HTML) at the moment an album is approved, and lock the album in place until explicitly reopened.

## Canonical approve sequence

This is the *single* ordered transaction for an approve. Specs 02, 08, and 10 describe their own slices; this section is the authoritative composition of all of them. A crash at any **named** step has a defined recovery rule. **No other spec may redefine these steps.**

Step names are stable anchors; future edits that insert or reorder steps must keep the names. The crash-recovery table cites step *names*, not numbers, so renumbering never silently invalidates the recovery contract.

```
step:verify-paths
    Verify all album.track_paths exist on disk (single check).
    On any missing → raise FileNotFoundError, abort. (Spec 02 §approve preconditions.)

step:export-staging
    Build Albums/<slug>/.export.new staging folder with new symlinks + playlist.m3u8
    via Spec 08 regenerate_album_exports(album, library, strict=True). Strict mode
    converts Spec 08's skip-with-warning into FileNotFoundError; a track deleted
    in the race window between step:verify-paths and step:export-staging aborts
    the sequence here.

step:export-commit
    Spec 08 _commit_export promotes staging into the live folder.
    Then shutil.rmtree(.export.new).

step:render-tmp
    Render Jinja2 template once → one in-memory HTML string (assets inlined as data: URIs).
    Write reports/<album> - YYYY-MM-DD.html.tmp via Spec 10 atomic_write_text.
    Render WeasyPrint(html_string) into reports/<album> - YYYY-MM-DD.pdf.tmp.
    Both .tmp files are now on disk. Status still draft. (Atomic-pair invariant
    per Spec 10 §Atomic pair (multi-file transactions): both .tmp written before
    either rename is attempted.)

step:render-rename-html
    os.replace(report.html.tmp, reports/<album> - YYYY-MM-DD.html). POSIX-atomic.

step:render-rename-pdf
    os.replace(report.pdf.tmp, reports/<album> - YYYY-MM-DD.pdf). POSIX-atomic.
    The pair is now committed; both finals exist on disk.

step:write-marker
    Touch the zero-byte .approved marker file. (Spec 02.)

step:flip-status
    Update album.json: status="approved", approved_at=now (Spec 10 atomic write).

step:ui-relock (UI side, not part of the on-disk transaction)
    Re-render top bar, library pane, album-order pane to reflect locked state.
```

**Crash recovery by named step:**

| Crash after | On-disk state | Recovery on next launch |
|---|---|---|
| `step:verify-paths` | Pre-approve; nothing written. | None needed. |
| `step:export-staging` | `.export.new/` present + live folder unchanged. | Spec 08 §Robustness — `AlbumStore.load()` wipes `.export.new/` and flags `needs_regen`. |
| `step:export-commit` | Live folder may hold a partial commit; M3U may or may not have been swapped; reports not yet rendered; status still draft. | Spec 08 drift-detection invariant: `AlbumStore.load()` detects symlink-count mismatch and flags `needs_regen`; next mutation re-runs the export. The user can re-approve cleanly afterward. |
| `step:render-tmp` | One or both `.tmp` files in `reports/`. Status still draft, no `.approved`. | Spec 10 §Atomic pair (multi-file transactions): the load-time scan deletes any `.tmp` in `reports/`. User can re-approve. |
| `step:render-rename-html` | HTML renamed; PDF still `.tmp`. Status still draft. | **Atomic-pair rule** (Spec 10 §Atomic pair): if exactly one of `(html, pdf)` for a given date stem exists, both members are removed (the renamed file + the `.tmp`). User must re-approve. |
| `step:render-rename-pdf` | Both report files renamed (no `.tmp`); status still draft, marker not yet written. | No self-heal needed — the `.approved` marker is the source of truth (Spec 02 §Errors). Reports without a marker do not auto-promote the album to approved; the user re-approves to advance state, which idempotently overwrites the existing reports. |
| `step:write-marker` | Marker present, status still draft, reports present. | Spec 10 self-heal: marker presence wins → flip status to approved, write back. |
| `step:flip-status` | Status flipped on disk, but UI hadn't updated when killed. | UI re-renders correct state on next load — no recovery needed. |

The mirror sequence for **unapprove** is owned by Spec 02 §unapprove.

## User-visible behavior

### The approve flow

1. User clicks the approve button (label: `Glyphs.CHECK + " Approve…"` per Spec 11 §Glyphs) in the top bar.
2. Pre-flight dialog appears with the album summary, listing:
   - Album name, target count, current selection count
   - The 8 / 12 / etc. status with colour
   - Any warnings (selected count ≠ target, missing tracks, broken symlinks)
3. User clicks "Approve and generate report" or "Cancel". The progress dialog (step 4) is **non-cancellable** once started; the approve button is **disabled for the duration** of the in-flight render — a queued click while a previous approve is still running is dropped (no queueing).
4. A modal progress dialog runs the work: `Exporting symlinks… → Rendering PDF… → Rendering HTML… → Writing .approved`. Typical total: <2 s for a 12-track album.
5. On success: dialog closes, top bar shows the album name prefixed with `Glyphs.LOCK` (Spec 11 §Glyphs) and a "Reopen for editing" button replaces the approve button. A success toast: `"Approved · report at <abs-path-to-pdf>"`.
6. The `reports/` folder is opened in the file manager (KDE: `xdg-open` the folder), gated on `settings.ui.open_report_folder_on_approve` (Spec 10 §`settings.json` schema; default `true`).

### The reopen flow (unapprove)

1. User clicks **Reopen for editing**.
2. Confirm dialog body text (verbatim): `"Reopening will delete the approved report (<file>.pdf + <file>.html). The symlink folder and playlist are kept. Continue?"`. Default-button: **Cancel**. The "Continue" button has destructive-action styling.
3. On confirm: per Spec 02 §unapprove step 2.{i,ii,iii} — (i) delete `reports/` recursively, (ii) delete the `.approved` marker, (iii) atomic-write `album.json` with `status = "draft"`, `approved_at = null`. Strict order; mirrors approve in reverse so a crash at any sub-step leaves a recoverable on-disk state. UI re-enables edits.

The symlink folder + `playlist.m3u8` are intentionally **kept** on unapprove — they reflect current selection, not approval state, and Spec 08 regenerates them on the next mutation. (Approve regenerates them via `step:export-commit`; unapprove keeps them. Symmetric design.)

## Report contents (PDF and HTML — single template, two outputs)

The PDF and HTML are rendered from a **single Jinja2 + CSS template** via WeasyPrint. The HTML is the same template rendered to HTML directly; the PDF is the same HTML rendered to PDF by WeasyPrint.

### Cover page

- Top: large album cover (square, ~60% of page width). Source: `cover_override` if set, otherwise the embedded cover from the first selected track, otherwise a theme placeholder.
- Below: album name (large, bold display typeface).
- Below: artist name (medium).
- Below: a status row: `Approved 27 April 2026 · 12 of 12 tracks · 47:13 total runtime`.
- Footer: small "Generated by Album Builder · v{__version__}", where `__version__` is read from `src/album_builder/version.py` at render time (not baked in at template compile time). When the app is bumped, the next-rendered report shows the new version automatically.

### Track listing page(s)

A table:

| # | Title | Composer | Duration |
|---|---|---|---|
| 1 | memoirs intro | Charl Jordaan | 2:17 |
| 2 | something more (calm) | Charl Jordaan | 4:41 |
| … | | | |
| | **Total** | | **47:13** |

Visual style: dark background of the report, but with high-contrast text that prints well to b/w too.

**Composer column elision (three-state rule):**

- *All tracks share a composer* — drop the composer column; render the line `"All tracks composed by <name>"` above the table.
- *Some tracks have a composer, some don't* — keep the composer column; tracks without a composer render an em-dash (`—`) in the cell.
- *No track has a composer* — drop the column; no above-table line.

The same three-state rule applies to artist.

### Per-track sections

For each selected track, in order, a card containing:

- The track's own embedded cover (top-left, ~120 px square; falls back to a tinted placeholder when mutagen returns `None` or raises).
- Track number, title, composer, duration (top-right block).
- Comment field (e.g., the `Copyright 2026 Charl Jordaan` line) on its own line if present.
- Lyrics text in full (block-quoted, monospace optional, falls back gracefully if track has no lyrics — shows "No lyrics provided"). **Lyrics body cap: 32 KB rendered per track**; longer bodies truncate with `\n(... truncated)` suffix appended in italics. The full text remains in the source LRC (Spec 07).

Per-track sections use CSS `break-inside: avoid` so a card never splits across a PDF page boundary; if a card doesn't fit in the remaining page, a `break-before: page` is inserted. In HTML they flow naturally.

Long lyric lines (>500 chars) wrap via CSS `overflow-wrap: anywhere` so a single unbroken word cannot overflow the column.

### Footer

- Generated timestamp (local time, ISO format)
- Source M3U path: `Albums/<slug>/playlist.m3u8`
- Album Builder version
- A "this report was generated automatically" disclaimer

## Technology

- **Template engine:** Jinja2.
- **PDF rendering:** WeasyPrint. Fully CSS-driven; supports gradients, custom fonts, page-break controls.
- **HTML output:** the same Jinja2 render, served as standalone HTML (assets inlined as base64 data URIs so the file is single-file portable for emailing).
- **Fonts:** the report uses theme-matched fonts. Since Linux availability varies, we either bundle a free-licensed font (e.g., Inter, SIL OFL) or fall back to system sans/serif via CSS `font-family` stack. Glyphs missing from the chosen font (rare Unicode in lyrics) fall back via the CSS stack to `Noto Sans` / `system-ui`; tofu (`?` boxes) is acceptable as last resort, not an error.
- **Images:** all cover images embedded in the HTML as data URIs to keep the file single-file. PDF embeds them natively.
- **Helper — `version_string() -> str`:** returns `src.album_builder.version.__version__` at call time. On `ImportError` (frozen-app or test-isolation context), returns `"unknown"` and logs a warning; never aborts the render. Used in §Cover page footer + §Footer.

**Single-template, two-output rendering rule.** The Jinja2 template is rendered **once** per approve, producing one in-memory HTML string. The HTML output is that string written to disk verbatim; the PDF output is WeasyPrint's render of the same string. **Both outputs share the same byte-identical input HTML.** Print-only formatting (page breaks, `@page` rules) lives inside `@media print { … }` blocks so the HTML displays correctly in a browser and the PDF picks up the print styles automatically. No second Jinja render is performed.

The two file writes are an atomic pair (see §Canonical approve sequence `step:render-tmp` through `step:render-rename-pdf`) but they share a single template execution.

## File naming

Report filenames embed the album name, which is user-supplied free text and may legitimately contain `/`, `:`, etc. They must be filesystem-safe.

- The album name is sanitised through the **same `sanitise_title` helper Spec 08 uses for symlink filenames** (canonical helper — see Spec 08 §Symlink filenames for the full rule, including the trim-until-stable + UTF-8 byte-length safety net). If the result is empty, fall back to `album`.
- PDF: `<sanitised-album-name> - YYYY-MM-DD.pdf`
- HTML: `<sanitised-album-name> - YYYY-MM-DD.html`
- The `YYYY-MM-DD` date is the local date at approve time (not UTC, since the user reads it).
- **No `_vN` suffix.** Re-approving the same album on the same day overwrites the previous PDF + HTML in place via the canonical approve sequence (Spec 02 §unapprove already deletes `reports/` recursively, so re-approve always lands in an empty `reports/` dir; there is no surviving prior report to bump). Earlier drafts of this spec defined a `_vN` rule; it was removed in the v0.5.0 prep sweep because the unapprove-deletes-reports invariant makes the suffix unreachable.

Examples: `Memoirs of a Sinner - 2026-04-27.pdf`. An album named "Hits / Volume I" would produce `Hits _ Volume I - 2026-04-27.pdf`.

## Inputs

- Approved `Album` (name, ordered `track_paths`, target_count, approved_at).
- Library tracks for each path — full metadata + cover bytes + duration.
- App version string (read from `src/album_builder/version.py: __version__` at render time).
- Theme assets (font files, palette).

## Outputs

- `<settings.albums_folder>/<slug>/reports/<sanitised-album-name> - YYYY-MM-DD.pdf`
- `<settings.albums_folder>/<slug>/reports/<sanitised-album-name> - YYYY-MM-DD.html`
- `<settings.albums_folder>/<slug>/.approved` (empty marker file)
- Mutation: `album.json.status = "approved"`, `approved_at = now`.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| WeasyPrint not installed correctly (missing system libs like Pango) | Show a friendly install instruction at first failure. |
| Cover image source-file >10 MB OR dimensions >800×800 | Resize to 800×800 max for embedding (Pillow). The threshold is OR, not AND — small dimensions but large file size (e.g., 8000-byte PNG with 600×600 pixels is fine; 1.2 MB JPEG at 600×600 still resizes via the file-size gate). Original file is untouched. |
| Cover image bytes unextractable (mutagen raises, file truncated, decoder fails) | Fall back to the per-track tinted placeholder (cover-page falls back to the §Cover page placeholder gradient). Logged as a warning; render does not abort. |
| Track has no embedded cover and no override | Use a theme-coloured placeholder (the §Album cover placeholder gradient from Spec 11). |
| Approve clicked while a previous approve is still rendering | The approve button is disabled for the duration of the in-flight render (§The approve flow step 3); a queued click is dropped. There is no queueing — the user can re-click after the previous run completes. |
| Approve while a draft live re-export is running | Approve waits (joins the in-flight worker), then runs its own export pass in `strict=True` mode. |
| `version_string()` `ImportError` (frozen app, broken venv, test isolation) | Return `"unknown"` and log a warning; render does not abort. |
| Lyrics body exceeds 32 KB | Truncate to 32 KB rendered, append `\n(... truncated)` in italics; full text remains in the source LRC. |
| Lyrics line >500 chars | CSS `overflow-wrap: anywhere` wraps within the column; no overflow into other cells. |
| Glyph not in chosen font | CSS font stack falls back to `Noto Sans` / `system-ui`; tofu (`?` boxes) is acceptable as last resort, not an error. |
| Composer / artist columns: some tracks have one, some don't | Three-state rule (§Track listing): all-share → drop column + above-table line; mixed → keep column with em-dash for missing; none → drop column with no line. |
| Disk full at PDF write time | Toast error; `.approved` not written; album stays in draft state. Symlink folder is untouched (export is a separate step that already succeeded). Stale `.tmp` siblings in `reports/` are wiped per the §canonical approve sequence recovery table. |
| Half-PDF / half-HTML written (one of HTML/PDF renamed, the other still `.tmp` or zero-byte) | The §canonical approve sequence atomic-pair invariant (`step:render-tmp` writes BOTH `.tmp` files before either rename is attempted; `step:render-rename-html` then `step:render-rename-pdf` rename them). Mid-step crash leaves either both `.tmp` files OR exactly-one renamed final + one `.tmp`. Spec 10 §Atomic pair (multi-file transactions) handles cleanup on next load. **`reports/` is never left in a half-good state visible to the user.** |
| Ordering changed between export and approve (impossible — approve is atomic in the UI) | Approve dialog snapshots the album state on open; the snapshot is what gets rendered. |

## Performance budget

The Jinja render is one pass; the two outputs split as: HTML write is the same render piped to disk (~0.3 s for a 12-track album); PDF write is WeasyPrint compiling that HTML to PDF (~1.5 s for the same album, dominated by font subset + image encoding).

- 12-track album with ~3 KB lyrics each: total approve ≤ 2 s on a modern CPU.
- 50-track album: total approve <5 s. Above that, we add a "rendering may take a moment" hint in the progress dialog.

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-09-NN` marker.

**Phase status — every TC below is Phase 4** (full report pipeline + canonical approve sequence). Phase 2 covers domain-level approve/unapprove transitions only (TC-02-12, TC-02-14); no `tests/` file matches TC-09 IDs until the Phase 4 plan executes.

- **TC-09-01** — Jinja2 template renders with a synthetic Album fixture; the resulting HTML contains every field listed in §Cover page + §Track listing + §Per-track sections.
- **TC-09-02** — `version_string()` returns `src.album_builder.version.__version__` at render time; mocking `__version__ = "9.9.9"` renders `Generated by Album Builder · v9.9.9` in the cover footer. On simulated `ImportError` of `src.album_builder.version`, returns `"unknown"`, logs a warning, and the render completes (no abort).
- **TC-09-03** — Report filename uses `sanitise_title(album.name)` (the same helper Spec 08 uses for symlinks); an album named `"Hits / Vol I"` produces `Hits _ Vol I - YYYY-MM-DD.pdf`.
- **TC-09-04** — *(removed in Phase 4 prep sweep — `_vN` rule is unreachable; same-day re-approve overwrites in place; see §File naming)*
- **TC-09-05** — Approve produces all three artefacts: `.pdf`, `.html`, `.approved`, all non-zero size after `Album.approve()` returns. Unapprove removes the PDF + HTML + `reports/` directory and the `.approved` marker; symlinks + M3U are kept.
- **TC-09-06** — Composer column three-state rule: (a) all tracks share a composer → column dropped + "All tracks composed by …" above table; (b) some have / some don't → column kept, em-dash in missing cells; (c) none have → column dropped, no above-table line. Same rule asserted for artist column.
- **TC-09-07** — Cover-page artwork sourcing: `cover_override` (if set) wins; else first selected track's embedded cover; else the theme placeholder gradient (Spec 11 §Album cover placeholder). When mutagen raises while extracting the embedded cover, fall through to the placeholder (no abort).
- **TC-09-08** — Cover image source-file ≤ 10 MB AND dimensions ≤ 800×800 is embedded as-is. Source-file > 10 MB OR dimensions > 800×800 triggers Pillow resize to 800×800 before embedding; original file is not modified.
- **TC-09-09** — Track without lyrics renders the "No lyrics provided" placeholder, not an empty block.
- **TC-09-09a** — Track with non-empty lyrics renders the full text inside a `<pre>` / quoted block in both HTML and PDF; no truncation up to the 32 KB cap; no escaping artefacts (`<`, `&` rendered literally, not as entities-of-entities).
- **TC-09-09b** — Lyrics body > 32 KB is truncated at the cap; `\n(... truncated)` appended in italics; the rendered HTML doesn't contain content past the cap. The source LRC remains untouched.
- **TC-09-10** — Atomic-pair: PDF + HTML are written as `.tmp` siblings (both writes complete before either rename) and renamed via two `os.replace` calls (`step:render-rename-html` then `step:render-rename-pdf`). A simulated crash between the two renames (mock the second `os.replace` to raise) leaves one renamed file + one `.tmp`; the Spec 10 §Atomic pair load-time scan removes both members.
- **TC-09-11** — *(removed in Phase 4 prep sweep — replaced by atomic-pair scan in TC-10-21; see Spec 10)*
- **TC-09-12** — Canonical approve sequence `step:verify-paths` runs *before* any disk side-effects. A missing track aborts with `FileNotFoundError`; no symlinks, M3U, or report files are written.
- **TC-09-12a** — `step:export-staging` calls Spec 08 `regenerate_album_exports` with `strict=True`; a track deleted in the race window between `step:verify-paths` and `step:export-staging` raises `FileNotFoundError` and aborts the sequence; live folder unchanged from pre-approve.
- **TC-09-13** — Self-heal: after a `step:render-tmp` mid-render crash the next launch finds stale `.tmp` siblings in `reports/`, deletes them via the Spec 10 §Atomic pair scan, and the album loads in pre-approve (draft) state.
- **TC-09-14** — Self-heal: after a `step:render-rename-pdf`-end crash (both reports renamed, status still draft, marker not yet written) the next launch leaves the album in draft and does **not** auto-promote to approved (marker is the source of truth, per Spec 02).
- **TC-09-15** — Disk-full mid-PDF: `.approved` not written; album stays draft; toast surfaces the error; subsequent retry succeeds without manual cleanup (load-time `.tmp` scan removes the leftover sibling).
- **TC-09-16** — Performance: 12-track album with 3 KB lyrics each renders PDF in <1.5 s, HTML in <0.3 s on the project's reference hardware.
- **TC-09-16a** — Performance: 50-track album with 3 KB lyrics each renders end-to-end (PDF + HTML) in <5 s. When `len(album.track_paths) > 50`, the progress dialog body includes the literal hint string `"rendering may take a moment"`.
- **TC-09-17** — HTML output is single-file portable: all images embedded as `data:` URIs; no external `<link>` or `<img src=…>` to filesystem paths.
- **TC-09-18** — `xdg-open <reports_folder>` is invoked exactly once after a successful approve, gated on `settings.ui.open_report_folder_on_approve`. Setting `false` suppresses the call; `true` (default) invokes it. Failure of `xdg-open` (no DE registered) is logged and silently ignored — the approve is still successful.
- **TC-09-19** — Success toast text is exactly `"Approved · report at <abs-path-to-pdf>"` where `<abs-path-to-pdf>` is the absolute path to the just-rendered `.pdf`.
- **TC-09-20** — Reopen confirm dialog body matches the §The reopen flow step 2 string verbatim. Default-button is **Cancel**; only "Continue" proceeds with deletion. The "Continue" button has destructive-action styling (red / danger palette per Spec 11).
- **TC-09-21** — Cover-page footer renders the literal string `"Generated by Album Builder · v<version>"` inside the cover-page `<footer>` element (placement, not just substring presence).
- **TC-09-22** — Per-track section CSS includes `break-inside: avoid` (`page-break-inside: avoid` for legacy compat) so a card never splits across a PDF page boundary; if a card doesn't fit in the remaining page, `break-before: page` is inserted and the card starts on a new page.
- **TC-09-23** — *(removed — folded into TC-09-09a)*
- **TC-09-24** — Lyrics line of 1000 chars renders inside the per-track block; the rendered HTML element width does not exceed parent column width — verified via WeasyPrint's layout report or a `<canvas>`-measure shim. CSS asserted to contain `overflow-wrap: anywhere` (or equivalent).
- **TC-09-25** — In-flight serialisation: when `Album.approve()` is called while a draft `regenerate_album_exports` worker is still running, the approve waits (joins the worker) then runs its own export in `strict=True` mode. When `Album.approve()` is called while another `Album.approve()` is in flight, the approve button is disabled and the second click is dropped (no queueing).
- **TC-09-26** — Approve button is wired to `Glyphs.CHECK + " Approve…"` per Spec 11 §Constants exposed in `theme.Glyphs`, not a hardcoded `✓` literal. Lock-prefix on the album-name display in the top bar uses `Glyphs.LOCK`, not a hardcoded `\U0001F512` literal.

(Visual regression — pixel-diff PDF vs golden — stays manual / opt-in. Not part of the TC contract because pixel-exact comparison is brittle.)

## Out of scope (v1)

- Email-the-report directly from the app.
- Editable report (e.g., add custom artist notes that flow into the report). v2 with an album notes field.
- Audio previews embedded in HTML (would inflate file size and complicate single-file portability).
- Multi-language reports.
- Custom report templates / themes.
