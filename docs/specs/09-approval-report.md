# 09 — Approval & Report

**Status:** Draft · **Last updated:** 2026-04-28 · **Depends on:** 00, 01, 02, 04, 05, 08, 10, 11 · **Lifecycle:** triggered by Spec 02's approve transition

## Purpose

Generate an artist-facing deliverable (PDF + HTML) at the moment an album is approved, and lock the album in place until explicitly reopened.

## Canonical approve sequence

This is the *single* ordered transaction for an approve. Specs 02, 08, and 10 describe their own slices; this section is the authoritative composition of all of them. A crash at any numbered step has a defined recovery rule. **No other spec may redefine these steps.**

```
1. Verify all album.track_paths exist on disk.
   On any missing → raise FileNotFoundError, abort. (Spec 02 §approve preconditions.)

2. Run export pipeline (Spec 08):
   a. Build .export.new staging folder with new symlinks + playlist.m3u8.
   b. Atomic _commit_export: replace symlinks + m3u in the live folder.
   c. shutil.rmtree(.export.new).

3. Render the report into reports/ — TWO files written as an atomic pair:
   a. Render Jinja2 template to a single in-memory HTML string (assets inlined).
   b. Write report.html.tmp via Spec 10 atomic_write_text.
   c. Render WeasyPrint output (HTML → PDF) into report.pdf.tmp.
   d. os.replace(report.html.tmp, reports/<album> - YYYY-MM-DD[_vN].html).
   e. os.replace(report.pdf.tmp, reports/<album> - YYYY-MM-DD[_vN].pdf).

4. Write the .approved marker file (zero-byte touch). (Spec 02.)

5. Update album.json: status="approved", approved_at=now (Spec 10 atomic write).

6. (UI side, not part of the on-disk transaction): re-render top bar, library
   pane, album-order pane to reflect locked state.
```

**Crash recovery by step:**

| Crash after step | On-disk state | Recovery on next launch |
|---|---|---|
| 1 | Pre-approve; nothing written. | None needed. |
| 2a | `.export.new/` present + live folder unchanged. | Wipe `.export.new/` on next export pass (Spec 08). |
| 2b/2c | Live folder has new symlinks + new M3U; report not yet rendered; status still draft. | Spec 02 self-heal: load detects export-fresh + status-draft, leaves the state alone. The user can re-approve cleanly. |
| 3a/3b | `report.html.tmp` (and possibly `report.pdf.tmp`) present in `reports/`. Status still draft, no `.approved`. | On next launch, `.tmp` siblings in `reports/` are deleted (stale-tmp cleanup per Spec 10). User can re-approve. |
| 3c/3d | One of HTML or PDF renamed; the other still `.tmp`. Status still draft. | **Atomic-pair rule:** on next launch, if exactly one of `(html, pdf)` for a given date exists, treat the report as broken and remove both (the renamed file + the `.tmp`). User must re-approve. |
| 3e | Both report files present, status still draft, marker not yet written. | Spec 02 self-heal: if reports exist but status=draft and no marker, *do not* auto-promote — the user reapproves to advance state. (Don't trust reports without an explicit marker.) |
| 4 | Marker present, status still draft, reports present. | Spec 10 self-heal: marker presence wins → flip status to approved, write back. |
| 5 | Status flipped on disk, but UI hadn't updated when killed. | UI re-renders correct state on next load — no recovery needed. |

The mirror sequence for **unapprove** is owned by Spec 02 §unapprove.

## User-visible behavior

### The approve flow

1. User clicks **✓ Approve…** in the top bar.
2. Pre-flight dialog appears with the album summary, listing:
   - Album name, target count, current selection count
   - The 8 / 12 / etc. status with colour
   - Any warnings (selected count ≠ target, missing tracks, broken symlinks)
3. User clicks "Approve and generate report" or "Cancel".
4. A modal progress dialog runs the work: `Exporting symlinks… → Rendering PDF… → Rendering HTML… → Writing .approved`. Typical total: <2 s for a 12-track album.
5. On success: dialog closes, top bar shows the album name with a small lock icon and a "Reopen for editing" button replaces "✓ Approve…". A success toast: "Approved · report at `Albums/<slug>/reports/<file>.pdf`".
6. The `reports/` folder is opened in the file manager (KDE: `xdg-open` the folder), unless the user disabled that in Settings.

### The reopen flow (unapprove)

1. User clicks **Reopen for editing**.
2. Confirm dialog: "Reopening will delete the approved report (`<file>.pdf` + `<file>.html`). The symlink folder and playlist are kept. Continue?"
3. On confirm: delete `reports/`, delete `.approved`, set `album.json.status = "draft"`. UI re-enables edits.

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

Visual style: dark background of the report, but with high-contrast text that prints well to b/w too. Composer column omitted if all tracks share the same composer (then noted at the top: "All tracks composed by Charl Jordaan"). Same for artist.

### Per-track sections

For each selected track, in order, a card containing:

- The track's own embedded cover (top-left, ~120 px square; falls back to a tinted placeholder).
- Track number, title, composer, duration (top-right block).
- Comment field (e.g., the `Copyright 2026 Charl Jordaan` line) on its own line if present.
- Lyrics text in full (block-quoted, monospace optional, falls back gracefully if track has no lyrics — shows "No lyrics provided").

Per-track sections start on a new page in the PDF when the previous section overflows; in HTML they flow naturally.

### Footer

- Generated timestamp (local time, ISO format)
- Source M3U path: `Albums/<slug>/playlist.m3u8`
- Album Builder version
- A "this report was generated automatically" disclaimer

## Technology

- **Template engine:** Jinja2.
- **PDF rendering:** WeasyPrint. Fully CSS-driven; supports gradients, custom fonts, page-break controls.
- **HTML output:** the same Jinja2 render, served as standalone HTML (assets inlined as base64 data URIs so the file is single-file portable for emailing).
- **Fonts:** the report uses theme-matched fonts. Since Linux availability varies, we either bundle a free-licensed font (e.g., Inter, SIL OFL) or fall back to system sans/serif via CSS `font-family` stack.
- **Images:** all cover images embedded in the HTML as data URIs to keep the file single-file. PDF embeds them natively.
- **Helper — `version_string() -> str`:** returns `src.album_builder.version.__version__` at call time. Used in §Cover page footer + §Footer. Read at *render* time so a version bump propagates without a template edit.

The Jinja2 template is rendered **once** per approve (producing one HTML string in memory). The HTML output is that string written to disk; the PDF output is WeasyPrint's render of the same string. The two file writes are an atomic pair (see §Canonical approve sequence step 3) but they share a single template execution.

## File naming

Report filenames embed the album name, which is user-supplied free text and may legitimately contain `/`, `:`, etc. They must be filesystem-safe.

- The album name is sanitised through the **same rule Spec 08 uses for symlink filenames** — `sanitise_title`: replace `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` with `_`; trim leading/trailing whitespace and dots; truncate to 100 chars; if empty, fall back to `album`.
- PDF: `<sanitised-album-name> - YYYY-MM-DD.pdf`
- HTML: `<sanitised-album-name> - YYYY-MM-DD.html`
- The `YYYY-MM-DD` date is the local date at approve time (not UTC, since the user reads it).
- If a report with the same date already exists (re-approve same day after reopen), append `_v2`, `_v3`, etc.

Examples: `Memoirs of a Sinner - 2026-04-27.pdf`, `Memoirs of a Sinner - 2026-04-27_v2.pdf`. An album named "Hits / Volume I" would produce `Hits _ Volume I - 2026-04-27.pdf`.

## Inputs

- Approved `Album` (name, ordered `track_paths`, target_count, approved_at).
- Library tracks for each path — full metadata + cover bytes + duration.
- App version string (read from `src/album_builder/version.py: __version__` at render time).
- Theme assets (font files, palette).

## Outputs

- `Albums/<slug>/reports/<album-name> - YYYY-MM-DD[_vN].pdf`
- `Albums/<slug>/reports/<album-name> - YYYY-MM-DD[_vN].html`
- `Albums/<slug>/.approved` (empty marker file)
- Mutation: `album.json.status = "approved"`, `approved_at = now`.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| WeasyPrint not installed correctly (missing system libs like Pango) | Show a friendly install instruction at first failure. |
| Cover image is huge (>10 MB) | Resize to 800×800 max for embedding (Pillow). Original file is untouched. |
| Track has no embedded cover and no override | Use a theme-coloured placeholder (the gradient cover from the mockup). |
| Approve while another export is running (impossible single-threaded UI, but worker overlap) | Approve waits for in-flight export to complete, then runs its own export pass. |
| Disk full at PDF write time | Toast error; `.approved` not written; album stays in draft state. Symlink folder is untouched (export is a separate step that already succeeded). Stale `.tmp` siblings in `reports/` are wiped per the §canonical approve sequence recovery table. |
| Half-PDF / half-HTML written (one of HTML/PDF renamed, the other still `.tmp` or zero-byte) | The §canonical approve sequence step 3 enforces atomic-pair semantics: both rename succeed, or neither lands. Mid-step crash leaves `.tmp` siblings; on next launch both the renamed file (if present) and the `.tmp` are removed and the user must re-approve. **Reports/ is never left in a half-good state visible to the user.** |
| Lyrics contain very long lines (>500 chars) | CSS word-wrap; no overflow into other cells. |
| Ordering changed between export and approve (impossible — approve is atomic in the UI) | Approve dialog snapshots the album state on open; the snapshot is what gets rendered. |

## Performance budget

The Jinja render is one pass; the two outputs split as: HTML write is the same render piped to disk (~0.3 s for a 12-track album); PDF write is WeasyPrint compiling that HTML to PDF (~1.5 s for the same album, dominated by font subset + image encoding).

- 12-track album with ~3 KB lyrics each: total approve ≤ 2 s on a modern CPU.
- 50-track album: total approve <5 s. Above that, we add a "rendering may take a moment" hint in the progress dialog.

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-09-NN` marker.

**Phase status — every TC below is Phase 4** (full report pipeline + canonical approve sequence). Phase 2 covers domain-level approve/unapprove transitions only (TC-02-12, TC-02-14); no `tests/` file matches TC-09 IDs until the Phase 4 plan executes.

- **TC-09-01** — Jinja2 template renders with a synthetic Album fixture; the resulting HTML contains every field listed in §Cover page + §Track listing + §Per-track sections.
- **TC-09-02** — `version_string()` returns `src.album_builder.version.__version__` at render time; mocking `__version__ = "9.9.9"` renders `Generated by Album Builder · v9.9.9` in the footer.
- **TC-09-03** — Report filename uses `sanitise_title(album.name)` (the same helper Spec 08 uses for symlinks); an album named `"Hits / Vol I"` produces `Hits _ Vol I - YYYY-MM-DD.pdf`.
- **TC-09-04** — Same-day re-approve produces `_v2`, then `_v3`. Different-day approve does not bump the suffix.
- **TC-09-05** — Approve produces all three artefacts: `.pdf`, `.html`, `.approved`. Unapprove removes the PDF + HTML + `reports/` directory and the `.approved` marker; symlinks + M3U are kept.
- **TC-09-06** — Composer column elides correctly: when all selected tracks share a composer, the column is dropped from the table and a "All tracks composed by …" line is added at the top of the table.
- **TC-09-07** — Cover-page artwork sourcing: `cover_override` (if set) wins; else first selected track's embedded cover; else the theme placeholder gradient (Spec 11 §Album cover placeholder).
- **TC-09-08** — Cover image larger than 800×800 is resized via Pillow before embedding; original file is not modified.
- **TC-09-09** — Track without lyrics renders the "No lyrics provided" placeholder, not an empty block.
- **TC-09-10** — Atomic-pair: PDF + HTML are renamed via `os.replace` after both render to `.tmp` siblings. A simulated crash between the two renames (mock the second `os.replace` to raise) leaves the un-renamed `.tmp` on disk; on next launch the cleanup step removes both the renamed file and the `.tmp`.
- **TC-09-11** — `_v2` collision detection scans the directory for both PDF and HTML siblings — bumping suffix only if either exists.
- **TC-09-12** — Canonical approve sequence step 1 (path verification) runs *before* any disk side-effects. A missing track aborts with `FileNotFoundError`; no symlinks, M3U, or report files are written.
- **TC-09-13** — Self-heal: after a step-3-mid-render crash the next launch finds stale `.tmp` siblings, deletes them, and the album loads in pre-approve (draft) state.
- **TC-09-14** — Self-heal: after a step-3-end crash (both reports renamed, status still draft) the next launch leaves the album in draft and does **not** auto-promote to approved (marker is the source of truth, per Spec 02).
- **TC-09-15** — Disk-full mid-PDF: `.approved` not written; album stays draft; toast surfaces the error; subsequent retry succeeds without manual cleanup.
- **TC-09-16** — Performance: 12-track album with 3 KB lyrics each renders PDF in <1.5 s, HTML in <0.3 s on the project's reference hardware.
- **TC-09-17** — HTML output is single-file portable: all images embedded as `data:` URIs; no external `<link>` or `<img src=…>` to filesystem paths.

(Visual regression — pixel-diff PDF vs golden — stays manual / opt-in. Not part of the TC contract because pixel-exact comparison is brittle.)

## Out of scope (v1)

- Email-the-report directly from the app.
- Editable report (e.g., add custom artist notes that flow into the report). v2 with an album notes field.
- Audio previews embedded in HTML (would inflate file size and complicate single-file portability).
- Multi-language reports.
- Custom report templates / themes.
