# Album Builder — Roadmap

Working roadmap for the Album Builder app. Tracks completed phases, in-flight findings, and upcoming work.

- **Specs:** `docs/specs/` (one per feature)
- **Plans:** `docs/plans/` (one per phase)
- **Status markers:** 📋 pending · 🚧 in progress · ✅ done

---

## ✅ v0.5.2 — UX fix-pass: lyrics-pane fill + row-button play/pause toggle (2026-04-30)

User-reported UX gaps spotted on the v0.5.1 build:

1. **Lyrics pane was small.** `LyricsPanel` called `setFixedHeight(150)` and `NowPlayingPane` finished its `QVBoxLayout` with `addStretch(1)` after the panel — together those two pinned the lyrics block to ~150 px and let empty space accumulate underneath. On a tall window the lyrics area looked stranded in the upper third of the right pane.
2. **Per-row ▶ button was load-only.** Clicking the row's preview-play button on the *currently-playing* row reloaded the source from scratch (set_source + play), instead of toggling pause as the transport bar's main play/pause button does. The transport's play/pause button worked correctly — only the per-row button lacked the toggle.

**Spec amendments (signed off via 2-pass cold-eyes review, 7 → 0 findings):**

- **Spec 06 §user-visible-behavior** — per-row preview-play button is now a **load-or-toggle** control with explicit four-state glyph mapping (`PLAYING`-on-active-source → `Glyphs.PAUSE`; PAUSED / STOPPED / ERROR / non-active → `Glyphs.PLAY`). Adds an ERROR-state same-row-click bullet (re-runs `set_source` + `play()`) and an Errors-table row for "active source's file removed between load and a same-row click."
- **Spec 06 test contract** — TC-06-15 amended to flag that it supersedes the v0.4.0 signal-only assertion in `test_library_pane_emits_preview_play_request`; new TC-06-17 (active+playing → pause without reload), TC-06-18 (active+paused → resume), TC-06-19 (per-row glyph mapping with library-pane vs album-order-pane a11y bifurcation + dataChanged-row-range observable for the perf claim).
- **Spec 07 §Lyrics panel** — panel now **fills the available right-pane height** below now-playing metadata, with a 150 px minimum (the pre-amendment fixed value) enforced via `setMinimumHeight` instead of `setFixedHeight`. New TC-07-16 with a measurable `qtbot` assertion (`resize(420, 800)` → `lyrics_panel.height() >= 300`).

**Shipped:**

- ✅ Step 3 — failing tests for TC-06-17/18/19 + TC-07-16 (10 of 11 red on the implementation-side, 1 already passing as the existing cross-row case).
- ✅ Step 4 — implementation (lifted `setFixedHeight(150)` → `setMinimumHeight(150)`, dropped competing `addStretch` after the lyrics panel, added `LibraryPane.set_active_play_state` + `AlbumOrderPane.set_active_play_state`, routed `Player.state_changed` + source-swap into both panes from `MainWindow`, added load-or-toggle dispatch in `_on_preview_play`).
- ✅ Step 5/6 — `/audit` + `/indie-review` in parallel (1 audit + 5 review findings, all L). Round 1 folded inline: pyright `None`-guard on `album_order_pane.py:173`, spec-06 PAUSED-vs-STOPPED split (PAUSED→toggle, STOPPED→fresh-load+restart), TC-06-15 marker disambiguation on the v0.4.0 test, and 2 new TC-06-19 tests for the album-order pane (set_album re-render preservation + set_active call-count observable). Round 2 convergence confirmed clean.
- ✅ Step 8/9 — flipped status to ✅; commit pending; push pending user OK.

**Convergence trace:** spec amendments 1-pass cold-eyes review (7 → 0 findings), implementation, post-implementation `/audit` + `/indie-review` (6 → 0 findings). 471 → 484 passing tests (+13: 11 new TC-06-17/18/19 + TC-07-16 contracts and 2 round-1-fold-out additions). Ruff clean. Manual smoke-launch on the `Tracks/` corpus completed without error.

---

## ✅ v0.5.1 — Outstanding-roadmap sweep (2026-04-30)

Same-day follow-up to v0.5.0 closing every actionable `📋` item still surviving in `ROADMAP.md` after the v0.5.0 ship: audit-tooling configs (`pyrightconfig.json`, `.gitleaks.toml`), version-file drift, the long-deferred `ACCENT_ROLE` extraction, the `settings.json` `schema_version` stamp gap (final piece of Theme B recurrence), Phase-4-shipped README dependency note. Also flips every stale `📋` cross-cutting summary line to `✅` where the underlying themes had been closed in per-item Tier fixes but the high-level summary was never updated.

**Shipped (8 items):**

- **Audit tooling (2):** `pyrightconfig.json` pinned at repo root pointing pyright at `.venv` (recovers the 4 mutagen unresolved-import diagnostics that surfaced on every `/audit` run); `.gitleaks.toml` with `extend.useDefault = true` + path-regexp allowlist for `.venv/`, `__pycache__/`, generated icon assets, and the gitignored `Tracks/` + `Albums/` + `.album-builder/` folders so `gitleaks detect -c .gitleaks.toml` runs without a `/tmp` shim.
- **Version drift (1):** `pyproject.toml` + `src/album_builder/version.py` bumped 0.4.2 → 0.5.0 to match the Phase 4 ship (the v0.5.0 commit was a `feat:` not a `release:` so the bump step was skipped).
- **Code (2):** `ACCENT_ROLE = Qt.ItemDataRole.UserRole + 2` extracted as module-level constant in `library_pane.py` (closes v0.2.1 Tier 2 L6-M2 deferral; mirrors `MISSING_ROLE` / `TITLE_ROLE` in `album_order_pane.py`); `_write_settings(data)` helper in `persistence/settings.py` stamps `schema_version = SETTINGS_SCHEMA_VERSION` at every write site (closes the final Theme B recurrence gap — hand-rolled files lacking `schema_version` self-heal on next save).
- **Docs (3):** README §Status promoted from v0.2.0 to v0.5.0 prose; README §System dependencies adds WeasyPrint runtime-library install commands (Pango / Cairo / GDK-PixBuf for openSUSE + Debian/Ubuntu) — closes the "Phase-4-prep, add when requirements pulls it in" deferral; ROADMAP cross-cutting summary 📋 → ✅ flips for Themes A-H (2026-04-28 review) and Themes B/F/I/J/K/L recurrence (2026-04-30 review), each citing the per-item Tier fix that actually closed it.

**Test count:** 467 → 471 passing (+4 schema_version regression tests in `tests/persistence/test_settings.py`). Ruff clean.

---

## ✅ v0.5.0 — Phase 4: Export & Approval (2026-04-30)

M3U + symlink folder per album, hard-lock approval state, PDF + HTML report generation via WeasyPrint. Specs: 08, 09. Shipped on `main` (commits `9bd98de` + `feb49b5`).

Convergence trace: pre-implementation 4-round spec sweep (39 → 17 → 3 → 0 actionable findings); implementation; 3-round post-implementation `/audit` + `/indie-review` (40 → 3 → 0 findings); full-codebase audit clean. 415 → 467 passing tests (+52 TC-08/09/10 contracts).

#### ✅ Phase 4 prep — Round 1 spec sweep (2026-04-30)

Pre-implementation cold-eyes review of the Phase 4 surface (Specs 02 §approve/§unapprove, 08, 09, 10 §atomic-write/§schemas, 11 §Glyphs/§Branding). 4 parallel review lanes (Spec 08 deep-dive, Spec 09 deep-dive, cross-spec consistency, test-contract coverage) returned 60 raw findings → 39 unique actionable items below after dedup. Goal: every BLOCKER + HIGH closes by spec edit before Phase 4 implementation begins.

**Priority A — design / contract (BLOCKER + HIGH):**

- ✅ **A1 — `_commit_export` is not actually atomic at the per-symlink granularity.** Spec 08 §Generation algorithm L77 promises "the staging-then-replace sequence"; §`_commit_export` L115–118 wipes live symlinks then per-link-replaces from staging — a kill between step 1 (wipe) and step 2 (first move) leaves zero symlinks + a stale M3U. Fix: rewrite the §`_commit_export` contract as "eventually consistent within bounded time" — explicit recovery rule "on launch OR before next mutation, count(live symlinks where is_symlink) ≠ count(track_paths) ⇒ trigger regeneration." Document the kill-9 window as a known short-window race that the next pass repairs. (Lane A BLOCKER.)
- ✅ **A2 — Atomic-pair cleanup for half-rendered reports has no defined trigger.** Spec 09 §canonical approve sequence row "3c/3d" says half-pair → delete both on next launch, but no spec names *who* runs that scan. Spec 10 §Errors stale-`.tmp` rule covers JSON only. Fix: extend Spec 10 §Errors to walk `Albums/<slug>/reports/`, deleting both members of any pair where exactly one of `(html, pdf)` for a given date stem exists; cross-link from Spec 09. (Lanes B + C BLOCKER.)
- ✅ **A3 — `#EXTINF` artist-title rendering rule unspecified.** Spec 08 §Outputs L59 shows `#EXTINF:281,18 Down - something more (calm)` by example. Null-artist handling, embedded ` - ` in title, missing-duration fallback are silent. Fix: explicit format rule + null-artist path + duration fallback (0 if mutagen returns None). (Lane A HIGH.)
- ✅ **A4 — Symlink filename "100 chars" is codepoints vs bytes ambiguous.** Spec 08 §Symlink filenames L65. UTF-8 multi-byte titles will hit ext4 `NAME_MAX=255` at a different point than 100 codepoints. Fix: "100 Unicode codepoints, then verify UTF-8 byte length ≤ 255 and shorten further if needed." (Lane A HIGH.)
- ✅ **A5 — `track_path` str-vs-Path coercion ambiguous in algorithm body.** Spec 08 §Generation algorithm L97 calls `.suffix.lower()` on the loop var; `album.track_paths` are strings per Spec 10. Fix: explicit `Path(p)` coercion in the pseudocode. (Lane A HIGH.)
- ✅ **A6 — Stale `.export.new` on launch has no trigger.** Spec 08 §Behavior rules L128 says "wipe as the first step of the next export pass." Nothing triggers an export pass on launch if the user opens the app and quits without mutating. Fix: add `AlbumStore.load()`-time bullet "if `.export.new` exists, schedule a regeneration; if no mutation occurs, wipe `.export.new` unconditionally on the next clean shutdown." (Lane A HIGH.)
- ✅ **A7 — Cross-filesystem `os.replace` rule for staging missing.** Spec 08 §`_commit_export` L118: `os.replace(staging/"playlist.m3u8", folder/"playlist.m3u8")` is atomic only when source + dest share a filesystem. Fix: assert "staging MUST be a sibling under the same album folder" with a TC. (Lane A HIGH.)
- ✅ **A8 — Spec 10 atomic-write contract carve-out for staging not explicit on either side.** Spec 08 §Generation algorithm L104 uses bare `.write_text` for the staging M3U; Spec 10 §Atomic write protocol L37 is unconditional. Fix: add a `§Atomic write — staging-folder exception` paragraph to Spec 10 stating that writes inside a transactional staging dir that itself promotes atomically are exempt; cross-link from Spec 08. (Lane A HIGH.)
- ✅ **A9 — Empty album (`track_paths == []`) export behavior silent.** Spec 08 doesn't say whether export still generates an empty M3U + zero symlinks, or skips the regeneration entirely. Fix: explicit §Behavior rules clause — empty album writes a one-line `#EXTM3U` file and zero symlinks; no warnings. (Lane A HIGH.)
- ✅ **A10 — `>99` tracks numbering format silent.** Spec 08 §Symlink filenames says `{NN:02d}`. Spec 10 §`album.json` schema caps `target_count` at 99 (Spec 04 enforces UI), but `track_paths` self-heal can raise `target_count` above the cap. Fix: clamp at 99 with a warning, OR widen format to `{i:03d}` when `len > 99`. Pick one and add §Errors row + TC. (Lane A HIGH.)
- ✅ **A11 — `_v2` suffix path is unreachable as written.** Spec 09 §File naming L134 + TC-09-04/11 assume same-day re-approve finds prior reports. But Spec 02 §unapprove step 2.i deletes `reports/` recursively, so re-approve always finds an empty directory. Fix: drop the `_vN` rule + delete TC-09-04 and TC-09-11; document "re-approve overwrites within the empty reports/ dir; date-only filename." (Lane B HIGH.)
- ✅ **A12 — Approve race-window vs Spec 08 skip-with-warning contradiction.** Spec 02 §approve says missing tracks are an error, never a skip. Spec 09 step 2 calls Spec 08 export, which has a unconditional skip-with-warning rule. Fix: Spec 09 step 2 must call Spec 08 in *strict mode* (any missing path raises and aborts the sequence). Spec 08 §Errors row gets a one-line carve-out: "Approve gates this earlier; the skip path is for draft live re-export only." (Lanes B + C HIGH.)
- ✅ **A13 — Spec 02 §approve §Behavior step 1 wording suggests double-verification.** Step 1 reads "Re-verify all `track_paths` exist (race-window check)" implying preconditions ran a *prior* check. Spec 09 has only one verification (canonical step 1). Fix: align Spec 02 step 1 to "Verify all `track_paths` exist — single check, per Spec 09 §canonical approve sequence step 1; preconditions snapshot the count, this re-checks existence." (Lane C HIGH.)
- ✅ **A14 — Spec 09 hardcodes glyph codepoints inline (Theme J recurrence).** §The approve flow uses literal `✓` and prose "small lock icon"; Spec 11 §Glyphs canonicalises both as `Glyphs.CHECK` / `Glyphs.LOCK`. Fix: Spec 09 references `Glyphs.CHECK (Spec 11 §Glyphs)` and `Glyphs.LOCK (Spec 11 §Glyphs)` instead of literal codepoints. (Lane C HIGH.)
- ✅ **A15 — `Albums/<slug>/` source-of-truth not pinned in Spec 02 §create.** Step 3 uses relative `Albums/`; doesn't say "resolve against `settings.albums_folder`." A reader could implement against CWD. Fix: change to "the album folder is created at `<settings.albums_folder>/<slug>/` (Spec 10 §`settings.json`)." (Lane C HIGH.)

**Priority B — missing test contracts (HIGH):**

- ✅ **A16 — Split TC-08-10 into 10a (hardlink fallback) + 10b (copy fallback).** Different UX semantics (suppressed dialog vs required dialog with default-no). Currently one TC line conflates both. (Lane D HIGH.)
- ✅ **A17 — Add TC-08-14 — `library.refresh()` precedes every export pass.** Spec 08 §Disk-read checks line is prose-only. (Lane D HIGH.)
- ✅ **A18 — Add TC-08-15 — symlink 64-byte sanity check after creation.** Spec 08 §Disk-read checks line is prose-only. (Lane D HIGH.)
- ✅ **A19 — Add TC-08-16 — `.export-log` rotation (last 10 runs).** Spec 08 §Disk-read checks line is prose-only. (Lane D HIGH.)
- ✅ **A20 — Add TC-09-18 — `xdg-open reports/` is gated on `settings.ui.open_report_folder_on_approve`.** Spec 09 §approve flow step 6. (Lane D HIGH.)
- ✅ **A21 — Add TC-09-20 — Reopen confirm dialog text, default-button "Cancel."** Spec 09 §The reopen flow step 2. (Lane D HIGH.)
- ✅ **A22 — Add TC-09-22 — Per-track section page-break CSS (`break-inside: avoid`).** Spec 09 §Per-track sections. (Lane D HIGH.)
- ✅ **A23 — Add TC-09-24 — 50-track render <5 s + ">50 tracks: rendering may take a moment" hint.** Spec 09 §Performance budget. (Lane D HIGH.)
- ✅ **A24 — Add TC-09-26 — long-line lyrics word-wrap, no overflow.** Spec 09 §Errors row. (Lane D HIGH.)
- ✅ **A25 — Add TC-09-27 — approve serialises with in-flight export (queue or lock).** Spec 09 §Errors row. (Lane D HIGH.)

**Priority C — clarifications + edge cases (MEDIUM):**

- ✅ **A26 — Spec 08 §Symlink filenames trim order specified.** "Trim leading/trailing whitespace AND dots — repeat until stable." (Lane A MEDIUM.)
- ✅ **A27 — Spec 08 §Outputs `#PLAYLIST:` / `#EXTART:` emit predicate.** Emit `#PLAYLIST:` iff `album.name` non-empty; emit `#EXTART:` iff all tracks share an artist. (Lane A MEDIUM.)
- ✅ **A28 — Spec 08 §Robustness collision dedup placement.** `track A.mp3` vs `track A (2).mp3` — show explicit example with extension. (Lane A MEDIUM.)
- ✅ **A29 — Spec 08 §Errors no-mutagen-readable-title fallback.** Distinct from post-sanitisation empty (which uses `track-{NN}`). (Lane A MEDIUM.)
- ✅ **A30 — Spec 08 §Errors album-folder-deleted-mid-session.** `mkdir(exist_ok=True)` recreates silently — Spec 02's deletion semantics mean the folder is in `.trash/`; export should detect deletion and abort with a toast, not silently recreate. (Lane A MEDIUM.)
- ✅ **A31 — Spec 09 `version_string()` `ImportError` fallback.** Return `'unknown'` on import failure; never abort render. Tighten TC-09-02 accordingly. (Lane B MEDIUM.)
- ✅ **A32 — Spec 09 §Technology single-string-for-both-outputs claim clarified.** Confirm (or amend): rendered HTML string is identical for both writes; print-only CSS is gated behind `@media print` so HTML displays correctly in browsers. (Lane B MEDIUM.)
- ✅ **A33 — Spec 09 §Errors partial-composer-column case.** Some tracks have a composer, some don't — currently §Track listing only handles "all share." Fix: composer column shown in full when ≥1 track has a composer; missing entries render as em-dash. (Lane B MEDIUM.)
- ✅ **A34 — Spec 09 §Errors lyrics block size cap.** 100 KB single-track lyrics inflates the PDF. Fix: cap rendered block at e.g. 32 KB with "(... truncated)" suffix; full text remains in source LRC. (Lane B MEDIUM.)
- ✅ **A35 — Spec 09 §Errors re-entrant approve.** Approve clicked while a previous approve worker is still rendering. Fix: button disables for the duration; queued click is dropped. (Lane B MEDIUM.)
- ✅ **A36 — Spec 10 §Atomic write protocol gets a `§Atomic pair (multi-file transactions)` subsection.** Names the invariant Spec 09 step 3 enforces; recovery rule lives here, not buried in Spec 09 prose. (Lane C MEDIUM.)
- ✅ **A37 — Spec 09 §canonical approve sequence step references switch from numeric to named anchors.** `step:verify-paths`, `step:export-staging`, `step:export-commit`, `step:render-tmp`, `step:render-rename-html`, `step:render-rename-pdf`, `step:write-marker`, `step:flip-status`. The crash-recovery table cites the named anchors. Future renumbering can't silently invalidate the recovery contract. (Lane C MEDIUM.)
- ✅ **A38 — Sharpen TC-02-13 + TC-02-19.** Enumerate the four artefacts (`playlist.m3u8`, symlink set, PDF, HTML, marker) with non-zero size assertion; enumerate three crash points (post-step-2b, post-step-3d, post-step-4) for idempotency. (Lane D MEDIUM.)
- ✅ **A39 — Sharpen TC-09-08 (cover resize threshold).** ≤ 10 MB AND ≤ 800×800 → pass-through; > 10 MB OR > 800×800 → resize. (Lane D MEDIUM.)

**Deferred / closed-by-policy (LOW):**

- ✅ **L1 — Spec 08 title `(M3U + Symlink Folder)`.** Stays as written; "M3U" refers to the format here, consistent with Spec 00 §Glossary which calls it the format. No change.
- ✅ **L2 — "Toast" not in Spec 00 §Glossary.** Cross-spec UI term; defined implicitly by Spec 11 surface conventions. Out of Phase 4 prep scope; bookmark for v0.6+ glossary expansion.
- ✅ **L3 — `reports/` deletion ordering note in Spec 09.** Folded into A37 (named anchors) — when steps are named, ordering becomes load-bearing automatically.
- ✅ **L4 — Concurrent export passes for two albums.** Implicit from Spec 10 §Debounce ("Multiple albums are debounced independently"). No new spec text required.
- ✅ **L5 — `reports/` is a user-symlink (shenanigans).** Out of v1 threat model (single-user single-machine); explicitly out of scope per Spec 00.
- ✅ **L6 — TC-11-10 ↔ TC-09-02 duplication.** Intentional cross-spec link per Spec 11's "mirror" wording. No change.

#### ✅ Phase 4 prep — Round 2 spec sweep (2026-04-30)

Single consolidated cold-eyes pass against the round-1 fixed spec set. 18 issues, mostly drift-by-fix (named-anchor renumbering missed leftovers, undefined references introduced by the rename, mojibake from ASCII-only convention applied to a glyph-codepoint citation). Pattern matches expectations: round 1 introduced named anchors; round 2 catches the citations the rename missed.

**Priority A — internal contradictions (BLOCKER + HIGH):**

- ✅ **B1 — Spec 09 §Outputs lines 178–179 still carry `[_vN]` after the §File naming rewrite excised the rule.** Direct contradiction inside the same spec. Fix: drop `[_vN]` from both `<album-name> - YYYY-MM-DD[_vN].pdf` and `.html` lines.
- ✅ **B2 — Spec 02 §approve §Behavior bullet 2 retains numeric "step 1 and step 2" reference.** Should cite `step:verify-paths` and `step:export-staging`.
- ✅ **B3 — Spec 08 contains two stale "Spec 09 step 2" / "Spec 09 step 1" numeric citations.** Inline algorithm comment + TC-08-05a body. Should be `step:export-staging` and `step:verify-paths`.
- ✅ **B5 — TC-09-26 has mojibake `ὑ2` instead of the lock codepoint.** ASCII-only convention applied wrongly. Fix: rewrite as `\U0001F512` per the project's ASCII-source convention.
- ✅ **B6 — Spec 11 §Glyphs has no named constants; Spec 09 references `Glyphs.CHECK` / `Glyphs.LOCK` as if they were defined.** Fix: add a "Constants exposed in `theme.Glyphs`" subsection to Spec 11 §Glyphs mapping each glyph to a Python identifier.

**Priority B — drift / semantic gap (MEDIUM):**

- ✅ **B7 — Spec 02 `Albums/<slug>/` half-conversion drift.** §delete, §Outputs, the companions table, TC-02-05, TC-02-15 still use the literal `Albums/<slug>/`. Fix: add a one-line preamble — "Throughout this spec, `Albums/<slug>/` is shorthand for `<settings.albums_folder>/<slug>/`."
- ✅ **B12 — Spec 09 §The reopen flow step 3 inlines the unapprove substeps instead of cross-referencing.** Fix: replace inline enumeration with "per Spec 02 §unapprove step 2.{i,ii,iii}."
- ✅ **B13 — `step:render-rename-pdf` recovery row references a Spec 02 self-heal that doesn't exist.** Fix: weaken to "no self-heal needed; the marker is the source of truth."
- ✅ **B14 — Spec 10 §Atomic pair scan uses `album.sanitised_name` without defining it.** Fix: add one-liner — "`album.sanitised_name` is `sanitise_title(album.name)` per Spec 09 §File naming."
- ✅ **B15 — Atomic-pair glob can false-match on date-suffix album names** (e.g. `"Daily - 2026-04-30"`). Fix: add constraint — UI-side validation rejects album names ending in ` - YYYY-MM-DD`.

**Priority C — cosmetic / docs hygiene (LOW):**

- ✅ **B8 — Spec 09 doesn't state symmetric "approve regenerates symlinks/M3U; unapprove keeps them."** Fix: add a one-line note to §The reopen flow.
- ✅ **B10 — Spec 08 inline comment "album.track_paths is list[str] per Spec 10" is misleading.** Fix: clarify — "list[str] on disk per Spec 10; coerce to Path here."
- ✅ **B11 — TC-08-03 has no width=3 example.** Fix: add a one-line example for `len > 99`.
- ✅ **B16 — Spec 10 TC-10-22/23 missing `(Phase 4)` tag.** Fix: tag consistently OR amend §Test contract preamble.
- ✅ **B17 — Spec 11 §Branding "Generated by [icon] Album Builder" vs Spec 09 footer mismatch.** Fix: pick one — add icon to Spec 09 cover-page footer, OR drop "[icon]" from Spec 11.

**Closed-without-change (LOW):**

- ✅ **B4 / B9 — Spec 08 in-algorithm "step N" self-references.** Closed by B3 (only cross-spec citations need updating).
- ✅ **B18 — Spec 11 §Album cover placeholder.** Confirmed clean.
- ✅ **TC-09-04 / TC-09-11 / TC-09-23 tombstones.** Confirmed acceptable cleanup approach.

#### ✅ Phase 4 prep — Round 3 spec sweep (2026-04-30)

Single consolidated cold-eyes pass against the round-2 fixed spec set. 3 issues found — **convergence indicator**: round 1 = 39 actionable; round 2 = 17; round 3 = 3.

- ✅ **C1 [HIGH] — Spec 02 §unapprove narration line 89 contradicts Spec 09's `step:render-rename-pdf` recovery contract.** Reads "Spec 09 self-heals this on next load by regenerating the report." No such "regenerate-on-load" self-heal exists in Spec 09 (recovery table says "no self-heal needed; user re-approves"). Fix: rewrite the sentence to match the actual contract — marker presence wins, a load-time toast prompts re-approve.
- ✅ **C2 [MEDIUM] — Spec 10 §Atomic pair attributes the album-name regex constraint to "Spec 02 §rename" but neither Spec 02 §rename nor §create surfaces the rule.** A Spec-02-only reader would never see it. Fix: add the validation rule to Spec 02 §create + §rename + §Errors table; cross-reference Spec 10 §Atomic pair as the rationale.
- ✅ **C3 [LOW] — Spec 11 §Constants exposed in `theme.Glyphs` includes `CLOSE` (`×`, U+00D7) but the visual §Glyphs table above does not.** Small narrative contradiction. Fix: add a `×` row to the upper visual table (toast close affordance) for parity.

#### ✅ Phase 4 prep — Round 4 confirmation pass (2026-04-30)

Single cold-eyes pass against the round-3 fixed spec set. **Zero findings.** Round-3 fixes (album-name regex constraint published byte-identical across 5 sites; Spec 02 §unapprove load-time-toast narration; Spec 11 §Glyphs `×` row addition) are internally consistent and consistent across specs.

**Verdict: READY FOR IMPLEMENTATION.** The Phase 4 spec set (specs 02, 08, 09, 10, 11) is implementer-ready with no surviving BLOCKER, HIGH, MEDIUM, or LOW issues.

**Convergence:** round 1 = 39 actionable findings; round 2 = 17; round 3 = 3; round 4 = 0. Specs grew from 996 → ~1,140 lines net and gained 16 new TC clauses (TC-08-02a, TC-08-05a, TC-08-10a, TC-08-10b, TC-08-14..19; TC-09-09a, TC-09-09b, TC-09-12a, TC-09-16a, TC-09-18..26; TC-10-21..24). 3 TCs were tombstoned (TC-09-04, TC-09-11, TC-09-23).

#### ✅ Phase 4 — v0.5.0 implementation (2026-04-30)

**Modules added:**
- `src/album_builder/services/export.py` (442 LoC) — `sanitise_title`, `_render_m3u`, `regenerate_album_exports` (strict + non-strict), `_commit_export` (eventually-consistent commit), drift-detection `is_export_fresh`, fs-caps cache, `.export-log` rotation, stale-staging cleanup.
- `src/album_builder/services/report.py` (335 LoC) — Jinja2 + WeasyPrint pipeline, `version_string()` `ImportError` fallback, three-state composer/artist column, 32 KB lyrics cap, cover normalise (Pillow OR-threshold), atomic-pair writes.
- `src/album_builder/services/templates/report.html.j2` — single template with `@media print` rules, `break-inside: avoid` page-break CSS, `overflow-wrap: anywhere` for long lyrics, `data:`-URI inlining.
- `src/album_builder/persistence/atomic_pair.py` (112 LoC) — `scan_reports_dir` load-time half-pair + stale-`.tmp` cleanup.

**Modules edited:**
- `src/album_builder/domain/album.py` — `_DATE_SUFFIX_RE` validation in `_validate_name`.
- `src/album_builder/services/album_store.py` — `approve(library=...)` orchestrates `step:verify-paths` → export(strict=True) → report → marker → status; `unapprove` deletes `reports/` first; `rescan` triggers stale-staging wipe + atomic-pair scan per album.
- `src/album_builder/persistence/settings.py` — `UiSettings` + `read_ui` / `write_ui` for `open_report_folder_on_approve`.
- `src/album_builder/ui/main_window.py` — `_on_approve` shows pre-flight summary with warnings + disables button during render + emits success toast + `xdg-open`s reports folder gated on settings; `_on_reopen` confirm dialog matches Spec 09 verbatim text with default-Cancel.

**Tests added (52 new):**
- `tests/services/test_TC_08_export.py` — TC-08-01..19 covering sanitise rules, M3U render predicates, symlink filename + width, idempotence, missing-track strict/loose modes, real-file preservation, dedup-by-title, drift detection, control-char rejection.
- `tests/services/test_TC_09_report.py` — TC-09-01..26 covering full template render, version fallback, three-state composer rule, cover resize threshold, lyrics cap, atomic-pair half-rename recovery, page-break CSS, single-file portability.
- `tests/persistence/test_TC_10_atomic_pair.py` — TC-10-21..24 covering pair-completed / pair-repaired / tmps-swept stats, name regex validation.

**Test count:** 415 → 467 passing (+52). Ruff clean. Audit + indie-review iterations queued next.

##### 🔍 /audit 2026-04-30 (post-implementation)

Tools: ruff, bandit (-ll), semgrep (p/security-audit + p/python on 42 files), gitleaks, pyright. **All clean — 0 actionable findings.** (Pyright surfaced 1 false-positive on weasyprint import resolution; system pyright doesn't see venv.)

##### 🔥 /indie-review 2026-04-30 (6-lane parallel cold-eyes review)

Author-bias flagged: parent session authored entire Phase 4 surface; cold-eyes lanes are the mitigation. Findings consolidated below; cross-cutting themes flagged by ≥2 lanes are the highest-confidence signal.

**Cross-cutting themes (caught by ≥2 reviewers):**

- 🔥 **Theme M — Bare `except Exception` swallowing real bugs.** `services/album_store.py:145` (rescan self-heal) + `ui/main_window.py:311` (post-approve niceties). Both correctly worried about hiding refactor regressions.
- 🔥 **Theme N — Atomic-pair recovery hole between rename-A and rename-B.** `services/report.py:289-298` deletes `pdf_tmp` but leaves orphan `html_final` — Spec 10 §Atomic pair "delete BOTH". Cross-confirmed by services/report H2 + persistence/atomic_pair (load-time scan handles it on next launch, but in-process recovery doesn't match spec).
- 🔥 **Theme O — Drift-detection / fallback-chain zombie infrastructure.** services/export L1 confirms `is_export_fresh` zero callers; `fs_supports_symlinks` + `_FS_CAPS_CACHE_PATH` machinery (50 LoC) zero callers. Spec 08 promises both.
- 🔥 **Theme P — Atomic pair `_unique_tmp_path` glob mismatch with Spec 10 sketch.** `report.py` writes `<final>.<pid>.<uuid8>.tmp` per Spec 10 protocol; the load-time scan's `*.tmp` glob in `atomic_pair.py:41` matches correctly, but Spec 10 §Atomic pair line 92 sketch shows literal `<file>.tmp` — spec sketch should be tightened.

**Tier 1 — ship-this-week (CRITICAL + HIGH that breaks shipping invariants):**

- ✅ **F1 [CRITICAL] — Drift-detection unwired (Theme O).** `services/export.py:188-208` defines `is_export_fresh` with zero callers; `services/album_store.py:138-147` calls `cleanup_stale_staging` and discards its return value (documented as "caller may flag the album `needs_regen`"). Spec 08 line 167 mandates `AlbumStore.load()` to set `needs_regen` on count mismatch; current code can never repair a kill-mid-`_commit_export` short of user mutation. Fix: add `needs_regen` attribute, wire scan in `rescan()`, trigger regeneration via Qt signal on next mutation.
- ✅ **F2 [CRITICAL] — Hardlink/copy fallback chain unimplemented (Theme O, scope decision).** `services/export.py:257` calls `link.symlink_to(...)` with no `try/except OSError`; `fs_supports_symlinks` + `_load_fs_caps` + `_save_fs_caps` + `_fs_key` + `_FS_CAPS_CACHE_PATH` are zombie code (50 LoC). FAT32/vfat album folder produces a stack trace instead of spec'd fallback. **Decision: scope-out the FAT32 fallback for v0.5.0 (not a real-world Linux desktop case)** — delete the dead infrastructure + amend Spec 08 §Errors to mark "Album folder on FS without symlink support" as v0.6+ defer.
- ✅ **F3 [CRITICAL] — `assert staging.parent == folder` disappears under `python -O`.** `services/export.py:416`. Spec 08 line 147 explicitly contrasts "asserted, not just commented" — but `assert` is exactly the wrong tool. Fix: replace with `if … != …: raise RuntimeError(...)`.
- ✅ **F4 [CRITICAL] — Pre-flight approve dialog uses default Qt Yes/No.** `ui/main_window.py:282-285`. Spec 09 §The approve flow step 3 mandates literal "Approve and generate report" / "Cancel" labels with destructive styling; default-Cancel per UX safety. Today: localised "Yes/No" defaults to Yes. Fix: replace `QMessageBox.question(...)` with custom `QMessageBox` mirroring `_on_reopen` shape.
- ✅ **F5 [CRITICAL] — `_show_toast` `statusBar()` fallback materialises a permanent status bar.** `ui/main_window.py:349-351`. Calling `statusBar()` instantiates the widget. `hasattr(self, "statusBar")` is always True (inherited method). Fix: drop the fallback; toast widget is always present in normal init.
- ✅ **F6 [CRITICAL] — `render_report` writes tmp via bare `open()` not `atomic_write_text`.** `services/report.py:264-276`. Spec 09 §step:render-tmp says "Write reports/… via Spec 10 atomic_write_text"; current code does `fsync(fh.fileno())` but skips parent-dir fsync. Fix: route through `atomic_io._atomic_write` or replicate its dir-fsync. (Note: the contract is satisfied at the file level; this is dir-level durability.)
- ✅ **F7 [HIGH] — `_commit_export` partial-failure leaks staging files (Theme N adjacent).** `services/export.py:286-291`. The for-loop calls `os.replace` per entry; ENOSPC mid-loop leaves half the new symlinks plus stale ones from previous order. Fix: catch OSError, log, skip stale-unlink step so previous order survives.
- ✅ **F8 [HIGH] — Atomic-pair recovery hole, in-process (Theme N).** `services/report.py:289-298`. On second `os.replace` failure, `html_final` orphan stays. Fix: in `except OSError` branch, also attempt `html_final.unlink()` matching Spec 10 "delete both".
- ✅ **F9 [HIGH] — `library=None` branch in `approve()` silently skips export+report.** `services/album_store.py:313-322`. Spec 09 mandates steps 2-3; legacy compatibility branch produces "approved album with no artefacts" — exact invariant the spec forbids. Fix: drop the branch (update the legacy test to pass a fake library) or raise on `None`.
- ✅ **F10 [HIGH] — `pairs_repaired` increments even when `unlink` failed.** `persistence/atomic_pair.py:90-102`. Stat lies to caller. Fix: increment only when both unlinks succeed; same for `tmps_swept`.
- ✅ **F11 [HIGH] — `_DATE_STEM_RE` is dead code.** `persistence/atomic_pair.py:23`. Module-top regex never used; inline copy at line 60 does the actual matching. Fix: delete the global; use the inline form (or refactor inline → global).
- ✅ **F12 [HIGH] — `·` glyph hardcoded in toast message (Theme J recurrence).** `ui/main_window.py:305`. Spec 11 §Constants single-source rule. Fix: add `Glyphs.MIDDOT = "·"` (or `Glyphs.SEP`) and reference it.
- ✅ **F13 [HIGH] — `except Exception` in `_on_approve` post-niceties (Theme M).** `ui/main_window.py:311`. Fix: narrow to `(OSError, ImportError)`.
- ✅ **F14 [HIGH] — `except OSError` in `rescan()` self-heal too narrow (Theme M).** `services/album_store.py:145`. `scan_reports_dir` could raise `re.error` in a future edit; `cleanup_stale_staging` could raise `ValueError` on bad input. Fix: add inline comment naming the policy ("OSError only — logic errors propagate to surface bugs"); broader catch with explicit raise-on-non-OSError.
- ✅ **F15 [HIGH] — Approve-failure leaves user with no toast surface.** `ui/main_window.py:285-294`. Spec 09 §Errors row "Disk full at PDF write time → Toast error". Fix: emit toast on OSError alongside (or instead of) the QMessageBox.warning.
- ✅ **F16 [HIGH] — Pillow optional + raw-bytes-survive masks decode failure.** `services/report.py:86-88`. With Pillow missing AND corrupt bytes, broken bytes flow into the data URI; WeasyPrint may abort. Fix: make Pillow a hard runtime dep (it's installed in venv), drop the `try/except ImportError`.

**Tier 2 — hardening sweep (MEDIUM):**

- ✅ **F17 — TOCTOU window between `step:verify-paths` and `step:export-staging`.** `services/album_store.py:307-315`. Mitigation is `strict=True` in export; pre-flight is UX only. Fix: add comment naming the mitigation so a future cleanup-pass author doesn't delete one half.
- ✅ **F18 — Re-entrant `approve()` not guarded at service layer.** `services/album_store.py:290`. Contract delegated to UI button-disabling. Fix: add `_approve_in_flight: set[UUID]` guard.
- ✅ **F19 — `unapprove()` partial-rmtree leaves indeterminate state.** `services/album_store.py:336-342`. EBUSY/EACCES mid-tree raises; album stays APPROVED with half-deleted reports/. Fix: catch OSError, retry once, then surface clear "manual cleanup needed" toast.
- ✅ **F20 — 64-byte sanity check doesn't verify zero-length.** `services/export.py:259-263`. `fh.read(64)` returns `b""` for both zero-length AND short-file-no-error; warning never fires. Fix: check return-value bytes against a minimum threshold.
- ✅ **F21 — M3U round-trip parse promised but not implemented.** `services/export.py:268`. Spec 08 line 186. Fix: scope-out for v0.5.0 (move to v0.6+ in spec) — round-trip is sanity, not safety.
- ✅ **F22 — Toast surface for control-char rejection.** `services/export.py:162` (`_render_m3u`) and `:245-247` (`_build_staging`). Fix: return `(created, warnings)` tuple from `regenerate_album_exports` so caller can surface a toast.
- ✅ **F23 — Permissions error in album folder gives stack trace, not toast.** `services/export.py:412-414`. `staging.mkdir()` raises `PermissionError`; no try-block around it. Fix: catch + raise `ExportFailed` with user-friendly message.
- ✅ **F24 — `_append_export_log` write failure kills successful export.** `services/export.py:326`. Fix: wrap in try/except; log-and-continue (best-effort).
- ✅ **F25 — `pairs_repaired`/`tmps_swept` accuracy + glob-escape sanitised_name.** `persistence/atomic_pair.py:41`. Album name with `[` or `]` (sanitiser doesn't strip these) silently fails to match. Fix: `glob.escape(sanitised_name)`.
- ✅ **F26 — Both-finals + stale-tmp branch missing in scan.** `persistence/atomic_pair.py:88-110`. State not in spec recovery table but spirit ("never half-good") implies stale `.tmp` should be swept. Fix: add `else: unlink(tmps)` arm.
- ✅ **F27 — `version_string()` falls back only on `ImportError`.** `services/report.py:49`. `AttributeError` (no `__version__` attr) raises. Fix: catch `(ImportError, AttributeError)`.
- ✅ **F28 — Reopen confirm dialog has no warning icon, no destructive styling.** `ui/main_window.py:325-332`. TC-09-20 last sentence. Fix: `setIcon(QMessageBox.Icon.Warning)` + `setObjectName("DestructiveButton")` + QSS rule.
- ✅ **F29 — Approve confirm default-Yes; should be default-Cancel.** `ui/main_window.py:282-285`. Destructive (irreversible) UI. Subsumed by F4 (custom dialog).
- ✅ **F30 — Settings re-read on every approve.** `ui/main_window.py:307-310`. Fix: cache at app start; invalidate via signal on settings-change.
- ✅ **F31 — Theme not whitelisted in `read_ui`.** `persistence/settings.py:201-203`. Spec 10 says only `"dark-colourful"` is valid. Fix: add `ALLOWED_THEMES = frozenset({"dark-colourful"})`.
- ✅ **F32 — Date-suffix regex matches pre-sanitise; spec says post-sanitise.** `domain/album.py:30`. Same set rejected in practice (sanitiser doesn't change date pattern), but spec-vs-code drift. Fix: add comment naming the equivalence; OR match against `sanitise_title(n)`.

**Tier 3 — structural / cosmetic (LOW + INFO):**

- ✅ **F33 — Library walked 2-3 times per export pass.** `services/export.py:140-185, 216-269`. Fix: pass `rendered: list[(Path, Track)]` to `_render_m3u`.
- ✅ **F34 — Inline imports in `main_window.py` `_on_approve` / `_on_reopen`.** Lines 267, 302, 307, 318. Fix: move to module-top.
- ✅ **F35 — Unicode em-dash in template `<title>` + `·` in footer.** `services/templates/report.html.j2:5, 251`. Fix: replace with ASCII `-` (template not linted by ruff).
- ✅ **F36 — Performed-by template line is unreachable.** `services/templates/report.html.j2:192`. Predicate `all_artist and not artist` always False because `artist = columns["all_artist"]`. Fix: drop the line, or rewrite predicate against the mixed-artist case.
- ✅ **F37 — `report_paths_for` `cover_uri` MIME hardcoded `image/jpeg`.** `services/report.py:107-110`. PNG cover_override would mislabel. Fix: detect via Pillow, or stream raw bytes through Pillow → JPEG always.
- ✅ **F38 — Approve runs synchronously on GUI thread.** `ui/main_window.py:285-294`. 5s budget per Spec 09 §Performance freezes UI. **Defer to v0.5.1** — Phase 4 ships synchronous; threaded approve is a hardening pass.
- ✅ **F39 — Focus restoration after approve dialog close.** WCAG §2.4.3. Fix: `self.top_bar.btn_reopen.setFocus()` post-success.
- ✅ **F40 — `EXPORT_LOG_RETAIN = 10` truncates user-edited logs silently.** Cosmetic.

**Closed without change:**

- ✅ **Verified — `xdg-open` argv injection.** `subprocess.Popen([list], …)` — list-form, no shell. Safe.
- ✅ **Verified — Jinja2 `select_autoescape(["html", "xml"])` blocks the XSS class.** `services/report.py:206`.
- ✅ **Verified — Single-template, two-output rendering, no `_vN` suffix, lyrics 32 KB cap, three-state composer column, page-break + word-wrap CSS, single-file portability, name regex DoS-safe** — all match spec.

##### 🔥 Round 2 indie-review (2026-04-30 post-fix)

Single-lane cold-eyes follow-up against the round-1 fixed code. 3 surviving findings (2 HIGH, 1 MEDIUM); all closed.

- ✅ **G1 [HIGH] — `_show_toast` typo `self.toast` vs `self._toast`.** `ui/main_window.py`. Round-1 introduced the bug; every toast (success, failure, reopen-partial) silently logged-only. Fixed: read `self._toast` via `getattr` to keep the test-isolation safety.
- ✅ **G2 [HIGH] — `_needs_regen` set in `rescan()` but never consumed on a draft mutation.** Spec 08 §`_commit_export` Drift-detection ("next mutation re-runs the full sequence") was unwired. Fixed: added `AlbumStore.schedule_export(album_id, library)` method calling `regenerate_album_exports(strict=False)` and clearing the flag; wired from main_window's `_on_target_changed`, `_on_track_toggled`, `_on_reorder_done`.
- ✅ **G3 [MEDIUM] — `_commit_export` partial-promote never raised in strict mode.** A failed promote let approve continue to `step:render-tmp` against a half-promoted folder. Fixed: added `strict` parameter to `_commit_export`; `regenerate_album_exports` passes its own `strict` through; failure raises `ExportFailed`.

##### ✅ Round 3 indie-review confirmation pass (2026-04-30)

Single-lane cold-eyes verification against the round-2 fixed code. **0 findings introduced by round-2 fixes.** 1 pre-existing dead branch flagged (`_key_in_text_field` line 482 — pre-existing, not Phase 4). 1 hygiene finding (G2 — `_needs_regen` not discarded on `delete()`); fixed inline.

- ✅ **H1 [LOW, hygiene] — `_needs_regen.discard(album_id)` and `_approve_in_flight.discard(album_id)` on `delete()`.** Stale ids accumulating across long delete-heavy sessions. Fixed.

##### ✅ Full-codebase audit (2026-04-30)

Final tool sweep across the entire `src/album_builder/` + `tests/` tree:

- **ruff** (src + tests): All checks passed.
- **bandit** (-ll, full src tree): 0 medium+ findings.
- **semgrep** (p/security-audit + p/python, 42 files): 0 findings.
- **gitleaks** (src/ + tests/): no leaks.
- **pytest**: 467 passed, 11 skipped (audio integration gates).

**v0.5.0 — Phase 4: Export & Approval — shipped 2026-04-30 on `milnet01/album-builder@main` (commits `9bd98de` feature + `feb49b5` CLAUDE.md refresh).**

---

## ✅ v0.4.2 — Phase 3B Tier 3 sweep (2026-04-30)

Patch release closing the `/indie-review` Tier 3 structural / cosmetic queue. Same-day follow-up to v0.4.1; no user-facing feature changes (one user-visible polish: body font-size now 11.5px to match Spec 11 §Typography exactly, was ~14.7px from `11pt` at 96dpi).

**Shipped (18 items across 5 logical batches):**

- **Domain (4):** `Album` switches to `dataclass(eq=False)` + UUID-identity `__eq__`/`__hash__` (L1-M2; two reads of the same album that differ only by `updated_at` ms drift now compare equal); `Library.find` documents the resolve cost; `_STAMP` regex documents the 999-minute (~16h39m) upper bound (L1-M4); `slugify` adds a manual transliteration table for Latin-1 ligatures NFKD doesn't decompose (Æ→ae, Œ→oe, Ð→d, Þ→th, Ø→o, Ł→l, Đ→d, Ħ→h).
- **Services (5):** `Player.set_source(None)` clears via `setSource(QUrl())` instead of raising `TypeError` (L3-M1); `seek()` documents the `[0, duration - 1.0]` clamp + short-track corner case (L3-M2); `match qstate:` adds `case _:` default for forward-compat; Qt event handler params typed (`PlaybackState`/`MediaStatus`/`Error`); `LyricsTracker._compute_index` forward fast path now also tries `hint+1` before linear-scan fallback (L4-M3 — foreground-playing tracks stay O(1) per tick across single-line crossings).
- **App + UI + theme (7):** `DEFAULT_TRACKS_DIR` renamed `_DEV_TREE_TRACKS_DIR` (gated to dev-mode) + `USER_MUSIC_DIR` (~/Music) added as installed-user fallback (L8-info); window title is bare "Album Builder" (L8-info — `setApplicationVersion` rendered separately by KDE/GNOME shells); body `font-size: 11pt` → `11.5px` (Spec 11 §Typography); `closeEvent` stderr summary scrubs `$HOME` → `~` via `_redact_home()` (L8-privacy); `LibraryPane.set_tracks` annotation widened to `Sequence[Track]`; `LibraryPane.row_accent_at` narrows `model.data()` return via `isinstance(value, str)`; `AlbumOrderPane._rerender_after_move` narrows `itemWidget()` via `isinstance(widget, _OrderRowWidget)`.
- **Theme J (1):** Glyphs single-source-of-truth sweep — `Glyphs.CHECK` / `TOGGLE_ON` / `TOGGLE_OFF` / `SEARCH` / `CLOSE` consumed at every previously-duplicated site (alignment_status.py, library_pane.py × 2, toast.py); literal-vs-escape convention documented at the namespace.
- **Theme I (1):** Test-filename prefix convention adopted forward-only via CLAUDE.md addition. NEW load-bearing tests use `test_TC_NN_*` / `test_WCAG_*` / `test_RFC_*` prefixes; existing files keep their names (retroactive rename would cascade through 15+ doc references without improving correctness).

**Test count:** 408 → 415 passing (+7 regression tests). Ruff clean.

---

## ✅ v0.4.1 — Phase 3B hardening (2026-04-30)

Patch release closing the `/indie-review` Tier 2 hardening queue. Same-day follow-up to v0.4.0; no user-facing feature changes. The detailed fix breakdown lives in the per-tier section below.

**Shipped (35 items across 8 commits):**

- **Domain (3):** `parse_lrc(track_path=...)` threading; majority-malformed → `LRCParseError`; Spec 07 TC-07-02 amended to "semantic equivalence" (the in-memory `Lyrics` doesn't retain headers / multi-stamp / line endings, so byte-identical round-trip is structurally impossible).
- **Persistence (6):** `_fsync_dir` errno narrowed to `{EINVAL, ENOTSUP}`; post-rename fsync failure logs + continues (data is durable); schema migration writes `<file>.v<old>.bak` (Theme C closure, latent until v2 lands); malformed UUID/status/timestamp/required-field surfaces as `AlbumDirCorrupt`; `state.window` width/height clamped to >= 100 (Spec 10); `splitter_sizes` accepts `n >= 0` (Spec 10).
- **Player (2):** `ended` signal for `EndOfMedia`; `(code, message)+50ms` error-emit dedupe.
- **Alignment (4):** `_check_interrupted()` wraps the WhisperX import; segment/lyric count mismatch logged; `.get("end", 0.0)` on the trailing-segment fallback; `LyricsTracker.set_lyrics` resets `_last_position` so a track switch doesn't carry the prior clock.
- **Watcher / store (4):** `_rebind_watch` is now diff-based (no inotify event-loss window); cross-FS `.trash` warning re-runs from first lazy `delete()`; `rescan()` uses local-dict-then-swap so a partial iterdir failure leaves prior state intact; `_on_dir_changed` filters parent-watch fires to the tracked folder + its exact parent.
- **UI top/library/order (6):** drag-handle glyph hidden on approved; Approve/Reopen + AlbumSwitcher pill expose accessible names (Theme F closure); `TargetCounter` text-input rejects values below current selection; `TrackFilterProxy` switched to casefold (Theme G closure); `TrackTableModel` exposes `tracks()` / `is_toggle_enabled(row)` / `selected_paths()` public accessors; approve-below-target documented as intentional per Spec 02.
- **UI playback/lyrics (6):** `LyricsPanel._restyle_at()` partial pass (O(|delta|) per line crossing) preserving Spec 11 typography from `list.font()`; Toast surfaces accessible description (Theme F closure; PyQt6 lacks `QAccessible`, so this is the closest live-region announcement available); transport scrubber switched to `sliderReleased`; `NowPlayingPane.set_track(None)` clears the lyrics panel; `LyricsPanel.palette_for_lyrics()` accessor.
- **App + main_window + theme (7):** splitter `setSizes` deferred to `showEvent` so saved ratios apply against real pane widths; `start_raise_server` requires the SHM lock parameter (assert + test); `closeEvent` collects per-step failures into one stderr summary line; state-save timer stopped first thing in `closeEvent`; Hamilton's largest-remainder method preserves `sum(splitter_sizes) == 13`; `_key_in_text_field` covers `QAbstractSpinBox` / `QDateTimeEdit` / editable `QComboBox`; auto-align gate documented at the call site.

**Test count:** 366 → 408 passing (+42 regression tests). Ruff clean. `/audit` (2026-04-30 post-Tier-2): bandit 0 medium/high (5 low — known assert/try-pass patterns from prior runs); gitleaks clean (116 commits scanned).

One Tier-2 item closed by spec rather than code: **L6-H1** (approve-button-below-target) — Spec 02 §approve preconditions explicitly allows approval at any non-zero count; the green-counter cue at at-target is UX feedback for "complete album", not a gate.

---

## ✅ v0.4.0 — Phase 3B: Lyrics Alignment (2026-04-30)

WhisperX + wav2vec2 forced-alignment pipeline behind the v0.3.0
`LyricsPlaceholder` slot. Pure-domain LRC parser / formatter / `line_at`
helper; cached-hint `LyricsTracker` subscribes to `Player.position_changed`
and emits `current_line_changed` only when a line crosses; `LyricsPanel`
widget renders status pill + 3-line scrolling list (past / now / future
styling driven by the Palette's `text_disabled` / `accent_warm` /
`text_tertiary` tokens). Alignment is opt-in (`alignment.auto_align_on_play`
defaults to False); the user's "Align now" click confirms the ~1 GB model
download before spawning the QThread worker. WhisperX is an optional
runtime dep — the venv ships without ~3 GB of PyTorch; the worker
lazy-imports `whisperx` inside `run()` and surfaces a one-shot
`pip install whisperx` dialog on `ImportError`.

**Shipped (Tasks 1-11 from `docs/plans/2026-04-30-phase-3b-lyrics.md`):**

- **Domain:** `LyricLine` + `Lyrics` frozen dataclasses (TC-07-12); `parse_lrc`
  handles tag headers, multi-stamp lines, 1-3 digit minute fields, 2-3 digit
  centisecond fractions, section-marker detection (TC-07-01); `format_lrc`
  half-up centisecond rounding round-trips byte-identically (TC-07-02);
  `line_at` boundary cases (TC-07-03).
- **Persistence:** `lrc_io.{read,write,is_lrc_fresh,lrc_path_for}`; malformed
  LRC ⇒ `<stem>.lrc.bak` (TC-07-10) + freshness comparison via mtime
  (TC-07-14); `settings.{read,write}_alignment` with `AlignmentSettings`
  (default `auto_align_on_play=False`, `model_size="medium.en"`); bool
  guard on `auto_align_on_play`; whitelist guard on `model_size`
  (TC-07-13).
- **Services:** `AlignmentStatus` enum + `compute_status` + `status_label`
  (TC-07-06); `LyricsTracker` cached-hint forward O(1), backward seek
  resets hint (TC-07-04, 05, 11); `AlignmentService` orchestrates per-path
  worker jobs, rejects empty-lyrics / fresh-LRC / sub-2-s-audio
  preconditions (TC-07-07), cancellable via `QThread.requestInterruption`
  with no `.lrc` written (TC-07-08); `AlignmentWorker` lazy-imports WhisperX,
  emits per-stage progress, maps WhisperX segments back to user lyrics text
  via `_segments_to_lyrics`.
- **UI:** `LyricsPanel` (status pill + scrolling 3-line `QListWidget` +
  Align-now button; per-line styling via `setForeground`/`setFont` keyed
  on Palette tokens — TC-07-15); replaces the v0.3.0 `LyricsPlaceholder`
  in `NowPlayingPane`; `MainWindow` wires tracker + service signals,
  loads fresh LRC at preview-play, gates auto-align via opt-in setting,
  shows download-confirmation dialog on first Align-now, surfaces
  WhisperX-missing one-shot dialog on `ImportError`.
- **Theme:** QSS rules for `QFrame#LyricsPanel`, `QLabel#LyricsStatus`,
  `QListWidget#LyricsList`, `QPushButton#LyricsAlignNow` replace the
  dashed-border placeholder rule.

**Test count:** 264 → 347 passing (+83 across `domain/test_lyrics.py`,
`persistence/test_lrc_io.py`, `persistence/test_settings.py` extension,
`services/test_alignment_status.py`, `services/test_lyrics_tracker.py`,
`services/test_alignment_service.py`, `services/test_alignment_worker.py`,
`ui/test_lyrics_panel.py`, `ui/test_main_window.py` extension). 11
integration tests skipped (10 audio + 1 lyrics, gated on
`AB_INTEGRATION_AUDIO=1` / `AB_INTEGRATION_LYRICS=1`). Ruff clean.

**TC-07 deferrals:** TC-07-09 (model-download interruption resume) is
gated behind a real WhisperX install — `huggingface_hub` already handles
partial-download resume via etag at the library level, so the v0.4.0
implementation does not add a project-side resume layer; the integration
tier covers the on-disk happy path. Tracked as a v0.5+ harden item if the
huggingface behaviour proves unreliable in practice.

**Manual smoke checklist** (per the Phase 3B plan §Manual smoke):

1. Cold launch — preview-play a track with `lyrics-eng` ID3 tag and no
   LRC; pill shows "not yet aligned"; Align-now visible. (Manual.)
2. Click Align now — first time: download confirmation dialog; on
   confirm: progress updates flow. (Manual; needs `pip install whisperx`.)
3. After alignment completes — pill shows "✓ ready"; lyrics scroll in
   sync with playback. (Manual.)
4. Quit + relaunch + preview-play same track — status "✓ ready"
   instantly (cache hit). ✓ (`test_main_window_loads_fresh_lrc_on_preview_play`.)
5. Manually corrupt the LRC (`echo zzz > Tracks/song.lrc`); preview-play
   — status reverts to "not yet aligned"; `.bak` file exists. ✓
   (`test_read_lrc_backs_up_malformed_to_bak`.)
6. Track with no `lyrics-eng` ID3 tag — pill "no lyrics text"; Align-now
   hidden. ✓ (`test_main_window_no_lyrics_text_status`.)
7. Track with audio < 2 s — pill "audio too short to align". ✓
   (`test_start_alignment_rejects_short_audio`.)

### 🔍 Audit 2026-04-30

Tools run: ruff, bandit, semgrep (`p/security-audit` + `p/python`), gitleaks, trivy fs, pyright, shellcheck. Six tools clean (0 findings each); pyright surfaced 65 raw → 3 actionable (95% noise from PyQt6 stub conservatism: `objectName=` kwarg, `Optional[X]` returns from `QListWidget.item()` / `QMenu.addAction()`, parameter-name mismatch on `resizeEvent` overrides, mutagen import resolution on system-Python pyright). Filtered manually given small volume.

- ✅ **LOW — `LibraryPane.set_tracks` annotation widened to `Sequence[Track]`.** Now matches `Library.tracks: tuple[Track, ...]` (commit `b00807b`).
- ✅ **LOW — `AlbumOrderPane._rerender_after_move` narrows `itemWidget()`.** `isinstance(widget, _OrderRowWidget)` makes a future row-widget swap fail at type-check time rather than runtime (commit `b00807b`).
- ✅ **LOW — `LibraryPane.row_accent_at` narrowed via `isinstance(value, str)`.** Toggle-column sort tuple can't leak through the title-column lookup (commit `b00807b`).

Also recommended (not code findings):

- ✅ **INFO — Add `pyrightconfig.json` at project root pointing at `.venv`.** Recovers the 4 `mutagen` unresolved-import diagnostics on every audit run. Landed in v0.5.1 sweep.
- ✅ **INFO — Persist `.gitleaks.toml` allowlist in-repo.** Path-regexp allowlist + extends-default-rules pinned at the repo root; `gitleaks detect -c .gitleaks.toml` runs without a `/tmp` shim. Landed in v0.5.1 sweep.

Calibration: 0 actionable security findings (4th run; cf. 2026-04-28 audit which was 0 actionable post-Phase-2). 95% noise rate on pyright is consistent with PyQt6 stub maturity.

---

## 🔥 Cross-cutting findings from `/indie-review` (2026-04-30)

8-lane multi-agent independent review post-Phase-3B (v0.4.0). Author-bias flagged: parent session authored Phase 3B (Lanes 1, 4, 7 dense in author-recent code). Mitigation: every cross-cutting theme below is grounded in ≥2 independent agent reports.

- ✅ **Theme I — Test names mirror internal modules, not external signals.** Closed by policy in v0.4.2: CLAUDE.md adopts the forward-only `test_TC_NN_*` / `test_WCAG_*` / `test_RFC_*` prefix convention for NEW load-bearing tests; existing files keep their names (retroactive rename would cascade through 15+ doc references without improving correctness).
- ✅ **Theme J — Glyphs single-source-of-truth bypassed across UI.** Closed in v0.4.2 commit `d4ef58f` (`alignment_status.py`, `library_pane.py`, `toast.py` consume `theme.Glyphs`); v0.5.0 F12 added `Glyphs.MIDDOT` for the toast separator.
- ✅ **Theme K — Cancel / teardown semantics are partial across subsystems.** All three components closed: `AlignmentService.cancel()` emits NOT_YET_ALIGNED revert (Tier 1 L4-M5); `AlbumStore.delete/rename` cancel `DebouncedWriter` entries (Tier 1 L5-M3); `closeEvent` collects per-step failures into a stderr summary (Tier 2 L8-H4).
- ✅ **Theme L — Spec text vs code drift on contracts that can't ship in current form.** All four closed: L1-H3 spec amended to "semantic equivalence" (Tier 2); L2-H3 `<file>.v<old>.bak` migration helper added (Tier 2); L6-H4 drag handles hidden on approved (Tier 2); L8-M4 outline-offset workaround in `theme.py:184-186` widens the existing border + shrinks padding to avoid layout shift (Qt QSS limitation documented inline).
- ✅ **Theme F (recurrence)** — WCAG 2.2 §4.1.2 / §4.1.3 a11y gaps closed in Tier 2: top-bar Approve / Reopen + AlbumSwitcher pill expose `setAccessibleName` (L6-H2 + H3); Toast surfaces `AccessibleDescription` for live-region announcement (L7-H2).
- ✅ **Theme B (recurrence)** — settings.json schema growth caught up to Spec 10: `albums_folder` (Tier 1 L8-C1), `ui.theme` + `ui.open_report_folder_on_approve` (v0.5.0 F31 + F30), `schema_version` stamping at every write site (v0.5.1 sweep). All Spec 10 §`settings.json` v1 fields are now implemented.

## 🔒 Tier 1 — Phase 3B ship-this-week fixes (data-loss / blocking)

✅ **All 7 landed 2026-04-30** across 5 commits. 354 → 366 tests pass; ruff clean. Threat-model calibration: single-user desktop, no network/auth/PII; data-locality + crash-atomicity are HIGH; "security" findings universally Low (no remote attacker).

- ✅ **CRITICAL — `app._resolve_project_root()` returned `Path.cwd()` instead of consulting settings.** Wired `albums_folder` setting (Spec 10 declared it but the reader was never built). Resolution order: settings → repo root if running from a source tree → CWD with stderr warning. Installed users with a configured `albums_folder` get Albums/ + state.json at the right location; unconfigured installs get a loud stderr nudge. (Commit `63c1678`. L8-C1.)
- ✅ **HIGH — `AlbumStore.rename()` was not crash-atomic.** Reordered to: validate name → cancel pending → rename folder → mutate domain → save JSON → emit. EBUSY/EACCES/EXDEV on the disk move now leaves the entire pre-state intact. (Commit `5e18c14`. L5-H1.)
- ✅ **HIGH — `AlbumStore.delete()` / `rename()` didn't cancel pending `DebouncedWriter` entries.** Added `DebouncedWriter.cancel(key)`; rename() and delete() call it before moving the folder. (Commit `5e18c14`. L5-M3.)
- ✅ **HIGH — `AlbumStore.delete()` slot-raise left dangling `_current_id`.** Reordered delete() to compute `was_current` → pop dicts → swap `_current_id` → emit album_removed → emit current_album_changed. State is consistent before any signal fires. (Commit `5e18c14`. L5-H3.)
- ✅ **HIGH — `Player._on_media_status` swallowed `MediaStatus.InvalidMedia`.** Added an InvalidMedia clause that mirrors `_on_error`'s ERROR-state transition and emits `Could not decode <source>`. Other media statuses unchanged. (Commit `02ba08a`. L3-H1.)
- ✅ **HIGH — `AlignmentService.cancel()` didn't emit status revert.** Emit `status_changed(path, NOT_YET_ALIGNED)` immediately after `requestInterruption()`. LyricsPanel pill leaves the ALIGNING state. (Commit `b3d7249`. L4-M5.)
- ✅ **HIGH — AlignmentWorker dropped the WhisperX install hint.** Added `except ImportError` branch in `run()` that emits the spec'd "WhisperX not installed. Install via: pip install whisperx" string. (Commit `41a09cf`. L4-L5.)

## 🔒 Tier 2 — Phase 3B hardening sweep (correctness, pre-v0.5.0)

✅ **All 35 landed 2026-04-30** across 8 commits. 366 → 408 tests pass; ruff clean. One spec amendment (L1-H3) and one closure-by-spec (L6-H1) required no code change.

Domain (L1):
- ✅ **HIGH — `Lyrics.track_path` typed `Path | None` but Spec 07 §Outputs declares `Path`; `parse_lrc` never sets it.** Threaded `track_path` through `parse_lrc(text, *, track_path)` (commit `abcc021`). L1-H1.
- ✅ **HIGH — `parse_lrc` malformed-line tolerance has no signal.** Now raises `LRCParseError` when malformed (no-leading-stamp) lines exceed 50% of non-blank, non-tag-header content lines (commit `abcc021`). The persistence layer's existing `LRCParseError → .lrc.bak` path now picks up noisy files. L1-H2.
- ✅ **SPEC AMEND — `format_lrc` byte-identical round-trip is structurally impossible.** Spec 07 TC-07-02 amended to "semantic equivalence" with explicit rationale (headers/multi-stamp/comments are surface metadata, not playable contract); Lyrics dataclass type bumped to `track_path: Path | None = None` (commit `abcc021`). L1-H3.

Persistence (L2):
- ✅ **HIGH — `_fsync_dir` swallows all `OSError` indiscriminately.** Errno check narrowed to `{errno.EINVAL, errno.ENOTSUP}`; EIO / EACCES / ENOENT propagate (commit `a54b5a1`). L2-H1.
- ✅ **HIGH — Post-`os.replace` `_fsync_dir` failure unlinks tmp + raises.** Split try-block: post-rename fsync failure logs warning + continues (data is durable at the final name) (commit `a54b5a1`). L2-H2.
- ✅ **HIGH — Schema migration `.bak` requirement still unimplemented (Theme C closure).** `_write_migration_bak()` helper added to both `album_io.py` and `state_io.py`; load-time migration writes `<file>.v<old>.bak` with the original bytes before rewriting the migrated form (commit `a54b5a1`). Latent until v2 schema lands. L2-H3.
- ✅ **MEDIUM — `_deserialize` field-shape errors leak as bare `KeyError`/`ValueError`.** Wrapped `_deserialize` call site with `except (KeyError, ValueError, TypeError) as exc: raise AlbumDirCorrupt(...) from exc` (commit `a54b5a1`). L2-M4.
- ✅ **MEDIUM — `state_io._coerce_window` accepts width=0 / height=0; Spec 10 mandates >= 100.** Added `max(100, raw)` clamp on width/height; x/y unaffected (commit `a54b5a1`). L2-M2.
- ✅ **MEDIUM — `_coerce_window` rejects splitter_sizes `n == 0`.** Filter relaxed to `n >= 0` per Spec 10 (commit `a54b5a1`). L2-M3.

Player (L3):
- ✅ **HIGH — `Player` has no `EndOfMedia` signal.** Added `ended = pyqtSignal()` emitted from `_on_media_status` on `EndOfMedia` (commit `0e60314`). Lyrics tracker / autoplay UX can now distinguish natural end from user-stop. L3-H2.
- ✅ **MEDIUM — `_on_error` may emit `error` twice on Qt 6.11 backends.** Added `_emit_error()` indirection with (code, message)+50ms-window dedupe; both `_on_error` and `_on_media_status` (InvalidMedia) route through it (commit `0e60314`). L3-M3.

Alignment (L4):
- ✅ **MEDIUM — Worker fast-cancel pulls in WhisperX before hitting interrupt check.** Added `_check_interrupted()` helper; the WhisperX import is now wrapped in `try/finally` so a cancel between the pre-check and the import surfaces as `_AlignmentInterrupted` (commit `e9ef0d4`). L4-H1-real.
- ✅ **MEDIUM — `_segments_to_lyrics` silently mis-pairs on count mismatch.** `logger.info(...)` line now records segment-vs-lyric count drift + the fallback-end timestamp (commit `e9ef0d4`). L4-M1.
- ✅ **MEDIUM — `segments[-1]["end"]` access without `.get()` guard.** Switched to `.get("end", 0.0)` (commit `e9ef0d4`). L4-M2.
- ✅ **MEDIUM — `LyricsTracker.set_lyrics` does not reset `_last_position`.** Reset to 0.0 in `set_lyrics`; the index-recompute uses the reset position (commit `e9ef0d4`). L4-M4.

Library Watcher (L5):
- ✅ **HIGH — `LibraryWatcher._rebind_watch` removes-then-adds = inotify event-loss window.** Replaced removeAll-then-addAll with diff-based `removePaths(current - wanted) + addPaths(wanted - current)`; same-set rebinds touch nothing (commit `e7d29cc`). L5-H2.
- ✅ **MEDIUM — `_check_trash_same_filesystem` only runs at construction.** Re-runs from `delete()` after `trash.mkdir()`; one-shot via `_trash_fs_checked` flag (commit `e7d29cc`). L5-M1.
- ✅ **MEDIUM — `rescan()` clears state before the iterate loop.** Local-dict-then-swap; PermissionError on `iterdir()` returns early with prior state intact (commit `e7d29cc`). L5-M2.
- ✅ **MEDIUM — `LibraryWatcher` parent-watch fires on unrelated sibling changes.** `_on_dir_changed` filters by path argument: only the tracked folder OR its exact parent triggers refresh (commit `e7d29cc`). L5-M4.

UI top/library/order (L6):
- ✅ **HIGH — Drag-handle glyph visible on approved albums.** Extracted `_row_text(i, title, *, approved)` helper; `set_album` and `_rerender_after_move` both consult album status (commit `6d2b88e`). L6-H4.
- ✅ **HIGH (closure) — Approve button enabled below target.** Spec 02 §approve preconditions explicitly allows approval at any non-zero count; the green-counter cue at at-target is UX feedback for "complete album", not a gate. Documented inline in `top_bar.py:87` (commit `091859a`). L6-H1.
- ✅ **HIGH — Top-bar buttons + AlbumSwitcher pill missing `setAccessibleName` (Theme F closure).** Approve / Reopen got accessible names + descriptions; AlbumSwitcher pill folds the current album name into its accessible name on every refresh (commit `6d2b88e`). L6-H2 + H3.
- ✅ **MEDIUM — `TargetCounter` text-input path bypasses at-target floor invariant.** `_on_text_committed` now reverts when typed value < `_selected`; no `target_changed` emit on rejected input (commit `6d2b88e`). L6-M3.
- ✅ **MEDIUM — `TrackFilterProxy` uses `.lower()` not `.casefold()` (Theme G closure).** Both needle and per-field comparison switched to `casefold()`; matches AlbumStore / Library / model sort role behaviour (commit `6d2b88e`). L6-M5.
- ✅ **MEDIUM — `LibraryPane` accesses `_model._toggle_enabled` / `._tracks`.** Added public accessors `tracks()`, `is_toggle_enabled(row)`, `selected_paths()` on `TrackTableModel`; `LibraryPane` no longer reaches into private state (commit `6d2b88e`). L6-M2.

UI playback/lyrics (L7):
- ✅ **HIGH — `LyricsPanel._restyle_items` constructs default `QFont()`.** Per-item font now derived from `self.list.font()` (Spec 11 typography preserved); only the bold property is mutated per row (commit `dab8507`). L7-H1.
- ✅ **HIGH — Toast lacks AlertMessage role / ARIA-live (Theme F closure).** `show_message` updates `setAccessibleName("Notification")` + `setAccessibleDescription(msg)` to fire Qt's DescriptionChange a11y event. (PyQt6 doesn't bind `QAccessible.updateAccessibility` — this is the closest live-region announcement available.) (commit `dab8507`). L7-H2.
- ✅ **MEDIUM — TransportBar scrubber `sliderMoved` spams `player.seek()`.** Switched to `sliderReleased`; the slot reads `self.scrubber.value()` for the final drag position (commit `dab8507`). L7-H3.
- ✅ **MEDIUM — `LyricsPanel._restyle_items` is O(N) per line crossing.** Added `_restyle_at(set)` for partial restyles; `set_current_line` now restyles only the inclusive `[min(old, new), max(old, new)]` range (2 items for forward-by-one ticks; bounded by jump distance for seeks) (commit `dab8507`). L7-H4.
- ✅ **MEDIUM — `NowPlayingPane.set_track(None)` does not clear `lyrics_panel`.** Mirror the per-field clear with `self.lyrics_panel.set_lyrics(None)` (commit `dab8507`). L7-M5.
- ✅ **MEDIUM — `LyricsPanel.__init__` palette default is unsafe-by-default.** Added `palette_for_lyrics()` accessor so callers can verify which palette instance is bound; default `Palette.dark_colourful()` retained for back-compat with construction-without-palette tests (commit `dab8507`). L7-M1.

App + main_window + theme (L8):
- ✅ **HIGH — `splitter.setSizes` runs before `splitter.show()`.** Stash `_restore_splitter_sizes` at construction; `showEvent` applies them once the splitter has its real width. Idempotent: minimise/restore doesn't re-clamp (commit `911784e`). L8-H1.
- ✅ **HIGH — `start_raise_server` precondition only in docstring.** Now takes a required `lock: QSharedMemory` kwarg with `assert lock is not None`; the test that calls it acquires + passes the lock (commit `911784e`). L8-H3.
- ✅ **MEDIUM — `closeEvent` silent-fail with no user surface.** Per-step failures collected into a single stderr summary line at the end of `closeEvent` rather than only `logger.exception` (commit `911784e`). L8-H4.
- ✅ **MEDIUM — `_state_save_timer` not stopped at start of `closeEvent`.** First instruction of `closeEvent` is now `self._state_save_timer.stop()` (commit `911784e`). L8-M2.
- ✅ **MEDIUM — `_save_state_now` ratio rounding doesn't preserve sum=13.** Replaced naive `round()` with `_hamilton_ratios()` (largest-remainder method); pathological splits like `[1, 1, 1500]` now sum to exactly `SPLITTER_RATIO_TOTAL` (commit `911784e`). L8-M1.
- ✅ **MEDIUM — `_key_in_text_field` doesn't include `QAbstractSpinBox` / editable `QComboBox` / `QDateTimeEdit`.** Broadened the isinstance set; editable QComboBox detected by walking up to the parent (commit `911784e`). L8-M3.
- ✅ **MEDIUM — `_sync_lyrics_for_track` calls `auto_align_on_play(track)` whose name hides the gate.** Added a leading comment at the callsite naming the `alignment.auto_align_on_play` setting that gates the actual start (commit `911784e`). L8-M5.

## ⚡ Tier 3 — Phase 3B structural / cosmetic

✅ **All 15 landed 2026-04-30 in v0.4.2** across 5 commits. 408 → 415 tests pass; ruff clean. One MEDIUM item closed by policy (Theme I — test-filename prefix convention adopted forward-only via CLAUDE.md addition; retroactive rename of 30+ test files would cascade through 15+ doc references without improving correctness).

- ✅ **MEDIUM — Glyphs single-source-of-truth sweep (Theme J closure).** Moved `✓` (alignment_status.py), `🔍`/`●`/`○` (library_pane.py), `"x"` (toast.py) to `theme.Glyphs`; literal-vs-escape convention documented at the namespace (commit `d4ef58f`).
- ✅ **MEDIUM — Test naming discipline (Theme I closure, by policy).** CLAUDE.md adds the forward-only convention: NEW load-bearing test files use `test_TC_NN_*` / `test_WCAG_*` / `test_RFC_*` prefixes. Inline `# Spec:` markers stay required at every test body regardless of filename (commit `1f336df`).
- ✅ **LOW — `Album` UUID-identity `__eq__`/`__hash__`.** Switched to `dataclass(eq=False)` + explicit identity by `id`. Reads that differ only by `updated_at` ms drift now compare equal (commit `46a33e0`). L1-M2.
- ✅ **LOW — `Library.find` resolve cost.** Documented at the call site; callers in tight loops should pre-resolve once (commit `46a33e0`). L1-M3.
- ✅ **LOW — `_format_stamp` 16h cap.** Documented at the `_STAMP` regex (commit `46a33e0`). L1-M4.
- ✅ **LOW — `slugify` Latin-1 ligature transliteration.** Manual table for Æ/Œ/Ð/Þ/Ø/Ł/Đ/Ħ added before the ASCII-encode step. "Łódź" now slugs to "lodz" not "odz" (commit `46a33e0`).
- ✅ **LOW — `seek()` clamp below 1.0s.** Documented; tracks <1.0s always seek to start (commit `5ad12f8`). L3-M2.
- ✅ **LOW — `match qstate:` default case.** Added `case _: pass` for forward-compat with future Qt PlaybackState additions (commit `5ad12f8`).
- ✅ **LOW — Player handler params typed.** `_on_playback_state` / `_on_media_status` / `_on_error` annotated with `QMediaPlayer.{PlaybackState,MediaStatus,Error}` (commit `5ad12f8`). L3-L1.
- ✅ **LOW — `LyricsTracker._compute_index` `hint+1` fast path.** Foreground-playing tracks stay O(1) per tick across single-line crossings; two+-line jumps still fall back (commit `5ad12f8`). L4-M3.
- ✅ **LOW — `Player.set_source(None)` clear.** `path: Path | None` + `setSource(QUrl())`; no more `TypeError` from `Path(None)` (commit `5ad12f8`). L3-M1.
- ✅ **LOW — Hardcoded `DEFAULT_TRACKS_DIR` path.** Renamed `_DEV_TREE_TRACKS_DIR` (gated to dev mode) + `USER_MUSIC_DIR` (~/Music) added as installed-user fallback (commit `b00807b`). L8-info.
- ✅ **LOW — Window title duplicates app version.** Title is bare "Album Builder"; `setApplicationVersion` rendered separately by shell (commit `b00807b`). L8-info.
- ✅ **LOW — Theme font-size 11pt vs Spec 11 11.5px.** Switched body to `font-size: 11.5px`; pixel units sidestep dpi conversion and stay font-anchored across screen scales (commit `b00807b`). L8-info.
- ✅ **LOW — `closeEvent` `~/` path leak.** `_redact_home()` scrubs `$HOME` → `~` in the per-step failure summary so a desktop launcher redirecting stderr to a shared journal can't expose the username via os-level exception paths (commit `b00807b`). L8-privacy.

## 🔭 Methodology gaps (standing practice for v0.5+)

- **Spec-anchored test naming.** Adopt prefix discipline for at least one test per spec contract (every 8 of 8 reviewers flagged this).
- **Re-run `/indie-review` before each minor tag.** Pre-v0.5.0 (Phase 4 export/approval) is the next checkpoint.
- **For every Tier 1/2 fix, write a spec-anchored failing test FIRST (red commit), then the fix (green commit), then `/indie-review --fix <ref>`** — Phase 5 remediation contract from the indie-review skill.
- **Spec 07 contract triage required.** Three Spec 07 clauses (TC-07-02 round-trip, TC-07-09 model-download resume, TC-07-15 outline-offset partial) need either spec amendments or code changes; the contract can't ship in current form on either side.

---

## ✅ v0.3.0 — Phase 3A: Audio Playback (2026-04-28)

`QMediaPlayer` integration with transport bar, per-row preview-play on both library + order panes, Spec 06 signal API normalised to seconds + `PlayerState` enum, `last_played_track_path` round-trip via `state.json`, volume + mute persistence via `settings.json`, all Spec 00 keyboard shortcuts wired with focus suppression. Lyrics alignment (Spec 07) carries forward to v0.4.0 — `LyricsPlaceholder` `QFrame` reserves the panel space; `Player.position_changed` is fully exposed for the future `LyricsTracker` to subscribe.

**Shipped (Tasks 1-11 from `docs/plans/2026-04-28-phase-3a-playback.md`):**

- **Persistence:** `audio.{volume, muted}` round-trip via `read_audio` / `write_audio`; `_read_settings_dict` extracted as shared malformed-JSON guard reusable by Phase 3B `alignment.*` block.
- **Services:** `Player` (QMediaPlayer + QAudioOutput wrapper) emits domain-shaped signals — `position_changed(seconds)`, `duration_changed(seconds)`, `state_changed(PlayerState)`, `error(str)`, `buffering_changed(bool)`. Volume clamps to 0..100; bool guard rejects True/False. Seek clamps to `(duration - 1.0)` and to 0. Two test tiers: unit (always runs) + integration (gated on `AB_INTEGRATION_AUDIO=1`).
- **UI widgets:** `TransportBar` (play/pause toggle glyph, scrubber, time labels, volume slider, mute button, buffering indicator); `NowPlayingPane` (cover + title + album/artist/composer/comment + transport + lyrics placeholder); `Toast` (transient bottom-of-window error notice with auto-dismiss).
- **UI extensions:** preview-play column on `LibraryPane` (col 0, PLAY glyph) + per-row preview-play QPushButton on `AlbumOrderPane` via `setItemWidget`. Column-index lookups via name-based `_column_index()` helper.
- **MainWindow integration:** Player owned; preview-play wired on both panes through `_on_preview_play(path)`; `last_played_track_path` restored paused at zero on startup; `closeEvent` stops player + persists audio settings (each step try/except-wrapped per L7-C1 pattern); `Toast` positioned at bottom of central widget on resize.
- **Keyboard:** Ctrl+N / Ctrl+Q / F1 / Space / Left / Right / Shift+Left / Shift+Right / M wired with `_key_in_text_field` suppression (`QLineEdit` / `QSpinBox` / `QTextEdit`). F1 surfaces a help dialog enumerating bindings. **Closes indie-review Theme E.**
- **Error UX:** Player errors route through `Toast`; one-shot `QMessageBox.warning` surfaces the openSUSE GStreamer/FFmpeg install command on the first decoder-class failure, then suppresses for the rest of the session.
- **Theme:** QSS rules for transport bar, now-playing labels, lyrics placeholder (dashed border), Toast (danger border + close button), per-row preview-play hover.
- **Spec 00 keyboard table:** "Wired?" column flipped from "Phase 3" to "✓ v0.3.0" across all rows.

**Test count:** 195 → 264 passing (+69 across player/transport_bar/now_playing_pane/toast/keyboard_shortcuts/main_window/settings/library_pane/album_order_pane). 10 integration tests skipped pending `AB_INTEGRATION_AUDIO=1`. Ruff clean.

**Indie-review carry-forward closures:**

- ✅ **Theme E (keyboard shortcuts).** Every Spec 00 shortcut wired with documented suppression machinery.

**Manual smoke checklist** (per the Phase 3A plan §Manual smoke):

1. Cold launch — right pane shows "(nothing loaded)" placeholder. ✓
2. Click `▶` on a library row — track loads + plays + transport updates. (Manual on host with audio.)
3. Drag scrubber → seek lands. (Manual on host with audio.)
4. Volume + mute persist across launches via `settings.json`. (Manual.)
5. Space toggles play/pause; suppressed in QLineEdit. ✓ (unit-tested via handler.)
6. Quit while playing → exits cleanly; re-launch → last-played track loaded paused at zero. (Manual.)
7. Bogus path → toast appears. ✓ (`test_preview_play_unknown_path_shows_toast`.)
8. Codec-class error → one-shot dialog. ✓ (`test_codec_error_shows_one_shot_dialog`.)

---

## ✅ v0.2.2 — Phase 2 Tier 3 sweep (2026-04-28)

Patch release closing the `/indie-review` Tier 3 structural / cosmetic queue. Same-day follow-up to v0.2.1; no user-facing feature changes (one user-visible polish: classic half-up rounding on track durations + Spec 11 gradients on the approve button and album pill).

**Shipped (20 items across 5 logical batches):**

- **Domain (5):** `slugify` NFKD transliteration ("Émile" → "emile" instead of collapsing to "album"); `Library` precomputes a casefolded search blob per track at `__post_init__`; `Library.sorted()` casefolds (Unicode-aware lower); `Album.unapprove` defensive target-invariant assert; `_to_iso` rejects naive datetimes.
- **Persistence (4):** `cover_override` self-heal symmetric with `track_paths`; `_write_album_json` + `_snap_timestamps_to_ms` extracted from the three `save_album*` variants; `_atomic_write` shared core for text/bytes; `read_text(encoding="utf-8")` pinned on `album_io.load_album`.
- **Services + UI (5):** `AlbumStore.list()` casefolds; `AlbumStore` signal docstring on `pyqtSignal(object)` idiom; `LibraryPane.set_tracks` selection-cache contract documented; `_format_duration` uses classic half-up rounding (was banker's); approve dialog string rewritten in user-neutral language.
- **Theme (2):** `QPushButton#ApproveButton` `success → success-dark` gradient + `QPushButton#AlbumPill` `accent-primary-1 → accent-primary-2` gradient (Spec 11 §Gradients TC-11-08); `Glyphs.DRAG_HANDLE` rendering documented.
- **Logging + tests (4):** `settings.read_tracks_folder` now logs OSError / malformed-JSON / non-object cases; +7 regression tests across slug, library, album_io, library_pane, and album.

**Test count:** 188 → 195 passing (+7 regression tests). Ruff clean.

One item carried forward as ongoing observation: `tests/ui/` filenames mirror module names rather than citing WCAG / RFC / TC-* IDs in filenames. Coverage map lives in spec; flagged for awareness, not a defect.

---

## ✅ v0.2.1 — Phase 2 hardening (2026-04-28)

Patch release closing the `/indie-review` Tier 1 + Tier 2 fix queue. Same-day follow-up to v0.2.0; no user-facing feature changes. The detailed fix breakdown lives in the per-tier sections below.

**Shipped (34 items across 13 commits):**

- **Tier 1 (6 ship-now items):** `AlbumStore.delete()` crash-atomicity + sub-second trash precision; `closeEvent` step-isolated try/except; CLAUDE.md rewrite; README v0.2.0 status; Phase-2-plan crosswalk truthfulness for TC-01-P2-03/04.
- **Tier 2 (28 hardening items):** Domain invariants + per-entry OSError; JSON self-heal symmetry + state.json field-type guards + `Path.absolute()` symlink preservation; atomic-write parent fsync + `DebouncedWriter` exception guard + XDG absolute-path conformance; cross-FS trash warning + parent-folder watcher + dotfile-skip; UI a11y (keyboard activation, AccessibleTextRole, accessible names, approved tooltip); locale-aware sort; pill empty-state middle dot; counter empty-snap-to-1; setMaxLength→commit-time validation; SHM-error-class distinction + try/finally; window-geometry restore clamp; spec coherence sweep (Spec 12 `%F`, Spec 04 boundary, Spec 00 keyboard wiring status, Spec 01 watcher ownership).

**Test count:** 173 → 188 passing (+15 regression tests). Ruff clean. `/audit` clean across all 7 tools.

Three items intentionally deferred:
- `LibraryPane._model._toggle_enabled` direct access (refactor → public accessor on `TrackTableModel`) — naming-only; carried to v0.3.0.
- `ACCENT_ROLE = Qt.UserRole + 2` magic-number → module constant — naming-only; carried to v0.3.0.
- 20 Tier 3 structural / cosmetic items — landed in v0.2.2.

One item accepted as v1 acceptance: stale-segment-recovery TOCTOU (microsecond race window during owner shutdown; documented in code).

---

## ✅ v0.2.0 — Phase 2: Albums (2026-04-28)

Phase 2 lands the entire album state machine + service layer + UI on top of Phase 1's library. Specs: **02** (lifecycle), **03** (switcher), **04** (selection + target counter), **05** (drag-reorder), **10** (full schema-versioning framework + per-key debounce + state.json), **11** (palette tokens + glyph anchors used by the new widgets), and Spec 01 TC-01-P2-01..02 (`tracks_changed` + `QFileSystemWatcher` watcher mechanism).

**Shipped (Tasks 1–18 from `docs/plans/2026-04-28-phase-2-albums.md`):**

- Domain — `Album` dataclass + `AlbumStatus` + state machine (create, rename, select, deselect, set_target, reorder, approve, unapprove); `slug` helper with collision resolver.
- Persistence — schema-version migration runner (`migrate_forward`); `album.json` (de)serialization with self-heal (relative-path resolve, target-vs-count bump, marker/status reconcile); `state.json` AppState round-trip with corrupt/too-new fallback; `DebouncedWriter` (250 ms per-key idle); ISO-8601 ms-precision Z-suffix encoding helper.
- Services — `AlbumStore` (Qt-aware CRUD + signals + `.trash` backup + service-level `approve` / `unapprove`); `LibraryWatcher` wraps `QFileSystemWatcher` with 200 ms debounce.
- UI — `TargetCounter` widget; `AlbumSwitcher` pill dropdown (stackable ✓/🔒 prefixes); `AlbumOrderPane` (middle pane drag-reorder via `QListWidget.InternalMove`); `LibraryPane` extensions (selection toggle column + at-target disable + accent strip with primary/warning variants); `TopBar` (composes switcher + name editor + counter + approve/reopen); `MainWindow` fully wired with state restore + close-flush + window-resize/move state-save.
- Release — bumped 0.1.0 → 0.2.0; ROADMAP close-out.

Two TCs explicitly Phase-4-deferred: TC-02-13 (export-pipeline regen on approve) and TC-02-19 (export-pipeline crash-injection idempotence). Phase 2's `AlbumStore.approve()` writes the `.approved` marker + flips status only.

Spec 01 deferral correction: TC-01-P2-03 (Track.is_missing on file-removed) and TC-01-P2-04 (Library.search filter parameter) remain deferred — they require diffing successive scans + a search() kwarg. Spec 01 was updated to reflect this honestly rather than claim full TC-01-P2-01..04 coverage.

**Test contract:** all 79 TCs in the plan crosswalk are mapped to direct/indirect/deferred coverage. Final test count: 171 passing (up from 86 at end of Phase 1).

Plan: [`docs/plans/2026-04-28-phase-2-albums.md`](docs/plans/2026-04-28-phase-2-albums.md) (~3700 lines, 18 tasks, all complete).

---

## 🔥 Cross-cutting findings from `/indie-review` (2026-04-28)

8-lane multi-agent independent review (7 code lanes + 1 documentation lane). Same-mental-model blind spots caught by ≥2 reviewers. Author-bias flagged: parent session authored all of Phase 2; mitigation = fresh-context subagents widening external specs cited.

- ✅ **Theme A — Empty-state pill text drift.** Closed in v0.2.1 Tier 2 (album_switcher.py uses U+00B7 middle dot per Spec 03 + TC-03-06).
- ✅ **Theme B — `settings.json` 8-field schema.** All Spec 10 v1 fields landed across releases — `tracks_folder` (Phase 1), `albums_folder` (v0.4.0 Tier 1 L8-C1), `audio.{volume,muted}` (v0.3.0), `alignment.*` (v0.4.0), `ui.theme` + `ui.open_report_folder_on_approve` (v0.5.0 F30 + F31), `schema_version` stamping (v0.5.1 sweep).
- ✅ **Theme C — `.bak` file requirement unimplemented.** Closed in v0.4.1 Tier 2 (L2-H3): `_write_migration_bak()` helper added to both `album_io.py` and `state_io.py`; migration writes `<file>.v<old>.bak` before rewriting.
- ✅ **Theme D — Approve-button + AlbumPill QSS gradients absent.** Closed in v0.2.2 Tier 3: `QPushButton#ApproveButton` (`success → success-dark`) and `QPushButton#AlbumPill` (`accent-primary-1 → accent-primary-2`) gradient rules in `theme.qt_stylesheet`.
- ✅ **Theme E — Keyboard shortcuts not wired.** Closed in v0.3.0. Every Spec 00 shortcut wired with `QShortcut` + `_key_in_text_field` suppression for transport keys; F1 help dialog enumerates the bindings.
- ✅ **Theme F — Screen-reader / a11y labels missing across all widgets.** Closed in v0.2.1 Tier 2 (toggle column `AccessibleTextRole`, drag a11y) + v0.4.1 Tier 2 (top-bar Approve / Reopen + AlbumSwitcher pill `setAccessibleName`; Toast `AccessibleDescription`).
- ✅ **Theme G — Locale-aware sort missing.** Closed in v0.2.1 Tier 2 (L5-H1 — `library_pane.py` casefold sort role) + v0.2.2 Tier 3 (`AlbumStore.list()` and `Library.sorted()` casefold).
- ✅ **Theme H — TC-01-P2-03/04 plan-crosswalk lies about coverage.** Closed in v0.2.1 Tier 1 (L8-H2 — both rows flipped from "direct" to "deferred" matching Spec 01 + ROADMAP).

---

## 🔒 Tier 1 — Phase 2 ship-now fixes (data-loss / blocking / doc-blast-radius)

✅ **All 6 landed 2026-04-28.** 3 surviving Criticals + 3 high-impact docs after threat-model calibration; single-user desktop threat model demoted SHM-leak-on-exception (L7-C2) to MEDIUM and CSRF-class to LOW. 173/173 tests pass; ruff clean.

- ✅ **CRITICAL — `AlbumStore.delete()` not crash-atomic.** Reordered to move-then-mutate at `src/album_builder/services/album_store.py:114-128`; failed `shutil.move` now leaves the album recoverable. Regression test in `test_album_store.py` monkeypatches the move to raise. Commit `a497943`. (L4-C1)
- ✅ **CRITICAL — Same-second `.trash` collision silently overwrites.** Switched to `%Y%m%d-%H%M%S-%f` (microseconds, UTC) at `album_store.py:124`. Regression test exercises delete-recreate-delete same-name same-second cycle. Commit `a497943`. (L4-C2)
- ✅ **CRITICAL — `closeEvent` flush is not exception-safe.** Each step wrapped in try/except with `logger.exception` at `main_window.py:217-228`. Regression test monkeypatches `store.flush` to raise; asserts state.json still receives new geometry. Commit `ac6ecbe`. (L7-C1)
- ✅ **CRITICAL — Project `CLAUDE.md` total rewrite.** Now describes the actual album-builder PyQt6 project (4-layer architecture, build/test/lint commands, conventions, applicable slash commands). Replaces the wholly-wrong "not a code project" declaration. Commit `941a5c3`. (L8-C1)
- ✅ **HIGH — README v0.2.0 status update.** Status section now describes shipped Phase 2 features (album CRUD, drag-reorder, target counter, watcher, debounced state.json) and clarifies playback → Phase 3 / export → Phase 4. Commit `053893f`. (L8-H1)
- ✅ **HIGH — Phase-2-plan crosswalk TC-01-P2-03/04 honesty.** Both rows flipped from "direct" to "deferred" matching Spec 01 + ROADMAP. Inline notes explain why the cited tests don't actually assert the spec contract (`is_missing` semantics + `include_missing` filter). Commit `e2eeeaa`. (L8-H2)

## 🔒 Tier 2 — Phase 2 hardening sweep (correctness, pre-v0.3.0)

✅ **All 28 landed 2026-04-28** across 7 commits. 195/195 tests pass; ruff clean. Two MEDIUM items intentionally deferred to Tier 3 (`LibraryPane` direct `_model` access — refactor; `ACCENT_ROLE` constant — naming-only).

**Domain (L1):**

- ✅ **HIGH — `Library.scan` per-entry `OSError` unhandled.** `src/album_builder/domain/library.py:51` now wraps the per-entry `is_file()` + `suffix` access in try/except; stale-NFS or permission-denied entries skip the entry instead of aborting the whole scan. Commit `6744d42`. (L1-H1)
- ✅ **HIGH — `Album.approve` missing-track check delegated, not documented.** Domain method's docstring now names `AlbumStore.approve()` as the precondition's owner; future direct callers must replicate the FileNotFoundError check or accept the risk. Commit `6744d42`. (L1-H2)
- ✅ **HIGH — `Album.__post_init__` invariant absent.** Now enforces 1≤target_count≤99, target_count≥len(track_paths), and "approved → non-empty selection". `_deserialize` pre-bumps target_count BEFORE construction so the existing TC-04-09 self-heal flow still works. Three new domain tests. Commit `6744d42`. (L1-H3)

**Persistence — JSON (L2):**

- ✅ **HIGH — `save_album_for_unapprove` ordering enforcement.** Now asserts `not (folder/"reports").exists()` before unlinking the marker; Phase 4 export-pipeline integration must delete reports/ first. Commit `4c5a562`. (L2-H1)
- ✅ **HIGH — Self-heal "approved-without-marker" skips `save_album()`.** Now routes through `save_album` for symmetry with the marker-present-status-draft branch; `updated_at` bumps on the heal. Commit `4c5a562`. (L2-H2)
- ✅ **HIGH — `_deserialize` uses `Path.resolve()` not `Path.absolute()`.** Switched to `Path.absolute()` so user-supplied symlinks survive the relative→absolute heal. Commit `4c5a562`. (L2-H3)
- ✅ **MEDIUM — `state_io.load_state` rewrite-on-corrupt.** Corrupt JSON now triggers an immediate rewrite with defaults (TC-10-12). New regression test. Commit `4c5a562`. (L2-M3)
- ✅ **MEDIUM — `state_io.load_state` field-type guards.** Per-field `_coerce_uuid` / `_coerce_path` / `_coerce_window` helpers catch malformed UUID, junk window types, stray keys; falls back to defaults instead of raising past the load_state guard. Commit `4c5a562`. (L2-M4)
- ✅ **MEDIUM — Self-heal `target_count` upper-bound clamp.** `_deserialize` pre-bumps target_count via `max(raw_target, len(resolved_paths))`; the new `Album.__post_init__` invariant catches >99 corruption at construction. Commit `4c5a562` + `6744d42`. (L2-M5)

**Persistence — write infra (L3):**

- ✅ **HIGH — `atomic_write_text` parent-dir fsync.** New `_fsync_dir` helper called after `os.replace` in both atomic-write helpers; best-effort (swallows EINVAL/ENOTSUP on filesystems without directory-fsync support). Commit `c997729`. (L3-H1)
- ✅ **HIGH — `DebouncedWriter._fire` callback lacks exception guard.** Wrapped in try/except + `logger.exception` so disk-full mid-callback no longer silently drops the write. Regression test schedules a raising callback + survivor. Commit `c997729`. (L3-H4)
- ✅ **MEDIUM — `XDG_CONFIG_HOME` relative-path acceptance.** `settings.settings_dir` rejects relative + empty values per the freedesktop Base Dir Spec; falls back to `~/.config/album-builder`. Two regression tests. Commit `c997729`. (L3-M3)
- 📋 **LOW (deferred to Tier 3) — `DebouncedWriter._timers` unbounded growth.** Bounded by album count today; revisit when high-cardinality keys land. (L3-M4)

**Services (L4):**

- ✅ **HIGH — Cross-FS `shutil.move` for `.trash` not asserted.** `AlbumStore.__init__` now compares `st_dev` of `Albums/` and `.trash` (when both exist) and warns on mismatch. Commit `0255943`. (L4-H1)
- ✅ **HIGH — `datetime.now()` in trash stamp is local time.** Already fixed in Tier 1 (commit `a497943`) — `datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")`. (L4-H2)
- ✅ **HIGH — `rescan()` race assumption undocumented.** Docstring now pins the single-threaded-Qt-event-loop assumption + adds defensive `except Exception` so a future loader bug doesn't abort startup. Commit `0255943`. (L4-H3)
- ✅ **MEDIUM — `LibraryWatcher.fileChanged` is dead code.** Connection dropped; comment explains the design choice. Commit `0255943`. (L4-M1)
- ✅ **MEDIUM — `LibraryWatcher` doesn't watch parent for folder-recreate.** `_rebind_watch` now adds the parent folder to the watcher; folder-delete-then-recreate cycle (TC-01-P2-04) recovers without manual `refresh()`. Commit `0255943`. (L4-M2)

**UI — lists/tables (L5):**

- ✅ **HIGH — `_toggle` column header sortable would crash.** Sort role for `_toggle` now returns a `(selected, casefolded-name)` tuple; header click no longer raises AttributeError. Commit `236456b`. (L5-H2)
- ✅ **HIGH — Toggle column not keyboard-reachable.** `QTableView.activated` connected to the click handler; Enter/Return on a focused toggle cell triggers the toggle. WCAG 2.2 §2.1.1. Commit `236456b`. (L5-H3)
- ✅ **HIGH — Toggle column has no `AccessibleTextRole`.** Branch in `data()` returns `"selected: <title>"` / `"not selected: <title>"`. WCAG 2.2 §4.1.2. Regression test. Commit `236456b`. (L5-H4)
- ✅ **HIGH — Drag has no reduced-motion / accessible feedback.** `AlbumOrderPane.list.setAccessibleName` + `setAccessibleDescription`; LibraryPane likewise. Commit `236456b`. (L5-H5)
- ✅ **MEDIUM — Approved-album tooltip absent.** `ToolTipRole` branch on the toggle cell of an APPROVED album returns the spec'd tooltip. Regression test. Commit `236456b`. (L5-M1)
- ✅ **MEDIUM — `_rerender_after_move` text-mangle fragility.** Now reconstructs from a cached title (`UserRole+3 / TITLE_ROLE`) rather than splitting display text on `". "`. Titles containing ". " (e.g. "Mr. Brightside") survive. Regression test. Commit `236456b`. (L5-M2)
- ✅ **HIGH — Sort role returns raw value, not `casefold()`.** Now `value.casefold() if isinstance(value, str) else value`. Spec 00 §"Sort order (canonical)". Regression test. Commit `236456b`. (L5-H1)

**UI — top-bar (L6):**

- ✅ **HIGH — Empty-state pill text middle dot.** Restored to `▾ No albums · + New album` per Spec 03 line 21 + TC-03-06. Commit `ced2923`. (L6-H1)
- ✅ **HIGH — `set_current(None)` initial-emit suppressed.** Docstring now documents the "no emit on construction; caller must seed" contract. MainWindow already seeds correctly. Commit `ced2923`. (L6-H2)
- ✅ **HIGH — `TargetCounter` empty-string commit reverts.** Empty now snaps to `MIN_TARGET` (TC-04-12); non-integer reverts via try/except `int()` (handles negative signs, Unicode digit forms). Commit `ced2923`. (L6-H4)
- ✅ **HIGH — `setMaxLength(80)` is UTF-16 code units.** Dropped; validation moved to commit time and uses `len(text) > 80` (code points) matching domain. Emoji-rich names no longer truncated. Commit `ced2923`. (L6-H5)
- ✅ **LOW — `LibraryPane._model._toggle_enabled` direct access.** Closed in v0.4.1 Tier 2 (L6-M2): `tracks()` / `is_toggle_enabled(row)` / `selected_paths()` public accessors on `TrackTableModel`.
- ✅ **LOW — `ACCENT_ROLE` magic number.** Closed in v0.5.1 sweep: `ACCENT_ROLE = Qt.ItemDataRole.UserRole + 2` extracted as module-level constant in `library_pane.py`; mirrors the `MISSING_ROLE` / `TITLE_ROLE` shape in `album_order_pane.py`.

**App integration (L7):**

- ✅ **HIGH — `_save_state_now` magic constant `13`.** Extracted `SPLITTER_RATIO_TOTAL = 13` module constant. Commit `8aa06d5`. (L7-H1)
- ✅ **HIGH — `DEFAULT_TRACKS_DIR` developer absolute path.** Now gated behind `ALBUM_BUILDER_DEV_MODE=1` env OR `pyproject.toml` colocated with the running script. Installed user no longer silently picks the dev path. Commit `8aa06d5`. (L7-H2)
- ✅ **HIGH — `signal_raise_existing_instance` silent timeout.** `RAISE_TIMEOUT_MS` 500 → 2000 ms; logs to stderr on timeout so a busy peer surfaces a diagnostic. Commit `8aa06d5`. (L7-H3)
- ✅ **HIGH — `start_raise_server` calls `removeServer` unconditionally.** Docstring now documents the lock-holder-only precondition that justifies the unconditional removeServer. Commit `8aa06d5`. (L7-H4)
- ✅ **MEDIUM — `acquire_single_instance_lock` doesn't distinguish error classes.** Inspects `lock.error()`; logs to stderr on non-`AlreadyExists` failures. Commit `8aa06d5`. (L7-M2)
- ✅ **MEDIUM — SHM detach + server.close not in `finally`.** `app.exec()` wrapped in try/finally. Commit `8aa06d5`. (L7-M3)
- ✅ **MEDIUM — Window geometry restore not bounds-checked.** `max(400, w) / max(300, h) / max(0, x|y)` clamp on restore. Commit `8aa06d5`. (L7-L1)
- 📋 **LOW (accepted as v1) — Stale-segment recovery TOCTOU.** Microsecond race window during owner shutdown; documented in code as v1 acceptance. (L7-M1)

**Documentation (L8):**

- ✅ **HIGH — Spec 12 + `.desktop.in` `Exec=` drift.** Spec updated to match `Exec=@@LAUNCHER@@` (no `%F`); inline note explains the omission. Commit `ce37096`. (L8-H3)
- ✅ **MEDIUM — `set_current` ValueError vs MainWindow ad-hoc check.** Spec 03 TC-03-09 row now documents the lookup-first approach as canonical. Commit `ce37096`. (L8-M1)
- ✅ **MEDIUM — Phase 2 plan crosswalk missing TC-12-NN.** Crosswalk now has TC-12-01..05 (direct, Phase 1) + TC-12-06..09 (manual smoke). Commit `ce37096`. (L8-M2)
- ✅ **MEDIUM — Spec 04 `selected == target` boundary wording.** Now explicit: at-target is valid; `set_target(n)` accepts `n == selected_count`. Commit `ce37096`. (L8-M4)
- ✅ **MEDIUM — Spec 00 keyboard-shortcut table claims Phase-1-2 shortcuts wired.** Added "Wired?" column; all marked "Phase 3" (focus-suppression machinery groups with Spec 06 work). Commit `ce37096`. (L8-M5)
- ✅ **MEDIUM — Spec 01 `tracks_changed` ownership.** Spec line 37 now correctly attributes the signal to `LibraryWatcher`, not `Library`. Commit `ce37096`. (L8-M6)

## ⚡ Tier 3 — Phase 2 structural / cosmetic

✅ **All landed 2026-04-28.** 188 -> 195 tests; ruff clean. Two INFO items intentionally not actioned (test-name convention review carried as ongoing flag; `Albums/__pycache__/` silent-skip already shipped in Tier 2 L4-M1).

- ✅ **MEDIUM — Locale-aware sort.** `AlbumStore.list()` and `Library.sorted()` now use `casefold()` (Unicode-aware lower; handles German ß, Turkish dotless I, Polish ł). LibraryPane's `data()` already used casefold from Tier 2.
- ✅ **MEDIUM — Approve / pill QSS gradients.** Added `QPushButton#ApproveButton` (`success → success-dark`) and `QPushButton#AlbumPill` (`accent-primary-1 → accent-primary-2`) gradient rules in `theme.qt_stylesheet`; `objectName="ApproveButton"` set on the top-bar approve button.
- ✅ **MEDIUM — `Library.search` lowercased-cache.** Added `Library._search_blobs: tuple[str, ...]` precomputed at `__post_init__`. Each keystroke now allocates one casefold() on the needle, not 500 on the haystack. Field is `compare=False, repr=False` so it's invisible to equality/repr.
- ✅ **MEDIUM — `slugify` non-ASCII transliteration.** NFKD-normalise + casefold + ASCII-encode before the regex. "Émile" → "emile", "Café" → "cafe", "Straße" → "strasse", CJK / emoji-only inputs still fall back to "album".
- ✅ **MEDIUM — `Album.unapprove` re-validate target invariant.** Defensive `assert self.target_count >= len(self.track_paths)` closes the gap when a caller bypasses `select()`'s guard via direct list mutation.
- ✅ **MEDIUM — `_to_iso` naive-datetime guard.** Now raises `ValueError` if `dt.tzinfo is None`. Prevents wrong-hour `Z` stamps from silently appearing if a caller forgets `tz=UTC`.
- ✅ **LOW — Refactor `atomic_write_text` / `atomic_write_bytes`.** Shared `_atomic_write(path, mode, content, encoding=...)` core; two 14-line functions are now 1-line wrappers + a 14-line helper.
- ✅ **LOW — Refactor three `save_album*` post-write blocks.** Extracted `_write_album_json(folder, album)` and `_snap_timestamps_to_ms(album)`; variants now differ only on marker timing as the spec intends.
- ✅ **LOW — `read_text()` without explicit encoding.** `album_io.load_album` now passes `encoding="utf-8"`. (`state_io.load_state` was already pinned in Tier 2 P4; `settings.read_tracks_folder` was already pinned.)
- ✅ **LOW — `cover_override` no relative-path heal.** `_deserialize` now applies the same `Path.absolute()` heal to `cover_override` as to `track_paths`; rewrites the file when healed.
- ✅ **LOW — `Library.scan` casefold not `.lower()`.** `Library.sorted()` lambdas now casefold; `.lower()` was only wrong on German ß + Turkish dotless I but the deviation closes the loop with Spec 00.
- ✅ **LOW — Approve dialog string mentions "Phase 4".** Rewrote the QMessageBox prompt to user-neutral language ("locked from edits until you reopen it" + parenthetical about export running automatically once that feature ships).
- ✅ **LOW — `AlbumStore` signal type comment.** Added a leading docstring block on the four signal lines explaining the `pyqtSignal(object) + # Type` idiom and why typed signatures aren't used directly.
- ✅ **LOW — `LibraryPane.set_tracks` `_selected_paths` contract.** Documented: selection state belongs to `set_album_state()`, not `set_tracks()`. Path equality is value-based so a track that vanishes and reappears stays correctly selected; clearing on every library refresh would visually drop the user's selection.
- ✅ **LOW — `_format_duration` banker's rounding.** Replaced `round()` (half-to-even) with `int(seconds + 0.5)` (classic half-up). 0.5s → 1, 1.5s → 2, 2.5s → 3. Regression test pinned.
- ✅ **LOW — `Albums/__pycache__/` noisy warning.** Already shipped in Tier 2; verified `entry.name.startswith("__")` filters it before the `AlbumDirCorrupt` log.
- ✅ **LOW — Empty-state pill middle dot.** Already shipped in Tier 2 (album_switcher.py:103 uses U+00B7 middle dot).
- ✅ **LOW — DRAG_HANDLE rendering.** Documented in `theme.Glyphs.DRAG_HANDLE`: U+22EE x2 approximates the spec's vertical stack at the available font sizes; a true vertical stack would require a custom-painted `QStyledItemDelegate`.
- ✅ **INFO — Structured logging in persistence/.** Added `logger = logging.getLogger(__name__)` to `settings.py`; `read_tracks_folder` now logs `OSError`, malformed-JSON, and non-object cases. (`album_io`, `state_io`, `debounce` already had loggers from prior tiers.)
- ✅ **INFO (closed by policy) — Tests don't cite WCAG / RFC / TC-* in filenames.** Closed in v0.4.2 by adopting the forward-only `test_TC_NN_*` / `test_WCAG_*` / `test_RFC_*` prefix convention via CLAUDE.md (existing files keep their names, NEW load-bearing tests use the prefix).

---

## ✅ v0.1.0 — Phase 1: Foundation (2026-04-27)

Themed PyQt6 window scans `Tracks/`, displays the library list with full metadata, installable via `.desktop`. No albums, playback, lyrics, export, or report yet — those land in Phases 2–4.

**Deliverables:**

- ✅ Project skeleton, venv, ruff config, pytest config
- ✅ Atomic-write helper (`atomic_write_text` / `atomic_write_bytes`)
- ✅ `Track` dataclass with mutagen ID3 parsing
- ✅ `Library` with scan / search / sort
- ✅ Dark + colourful theme (`Palette` + `qt_stylesheet`)
- ✅ `LibraryPane` widget (sortable, filterable QTableView)
- ✅ `MainWindow` with three-pane splitter
- ✅ Single-instance launcher via `QSharedMemory`
- ✅ Vinyl SVG icon + freedesktop `.desktop` template
- ✅ Per-user installer / uninstaller / README
- ✅ 30-test pytest suite (TDD throughout)

**Tag:** `v0.1.0-phase1` (local; not pushed)

---

## 🔥 Cross-cutting findings from `/indie-review` (2026-04-27)

3-lane multi-agent independent review. Same-mental-model blind spots caught by ≥2 reviewers.

- ✅ **Theme 1 — Spec drift.** All 5 instances closed by Tier 1 + Tier 2 fixes (hardcoded Tracks path, `album_artist` filter scope, default sort, PermissionError propagation, JPEG covers).
- ✅ **Theme 2 — Defensive-handler breadth.** `Library.scan` `OSError` catch narrowed (Tier 1.3); `install.sh` / `uninstall.sh` `2>/dev/null` removed from cache-refresh tools — real failures now surface to the user.
- ✅ **Theme 3 — Single source of truth violations.** Version string consolidated to `version.py:__version__` (Tier 1.2 fold-in); icon path now resolves through `QIcon.fromTheme("album-builder")` — same theme name the `.desktop` file uses — with a dev-tree SVG fallback for running pre-install.

**Methodology gap (deferred to Phase 2 prep):** add a "Test contract" section to per-feature specs naming the clauses each test must validate. The implementation pipeline `spec → plan → code → tests` currently lets tests encode the plan's interpretation rather than the spec's contract. Tracked as a Phase 2 prep task; not blocking Phase 2 implementation work.

---

## 🔒 Tier 1 — ship-this-week fixes (security / data-loss / DoS)

✅ **All 4 landed 2026-04-28** on branch `feature/phase-1-foundation`. 47/47 tests pass; ruff clean. Net diff: +194 LOC across `app.py`, `track.py`, `library.py`, `library_pane.py`; +1 new module `persistence/settings.py`; +17 new tests.

- ✅ **CRITICAL — QSharedMemory stale-lock recovery + QLocalServer raise handshake.** `src/album_builder/app.py`. `attach()/detach()` recovery dance before `create(1)` reclaims orphan SHM segments left by SIGKILL/OOM/power-loss. `QLocalServer` listens on the same key; second-launch sends `raise\n` via `QLocalSocket` and exits silently. Previous "Already running" dialog removed. Commit `36afe6b`.
- ✅ **HIGH — `_resolve_tracks_dir()` consults settings.json first.** `src/album_builder/app.py`. New `persistence.settings` module is XDG-aware (`$XDG_CONFIG_HOME` honored). Dev path is the labelled fallback with stderr warning so a misconfigured install is loud. Commit `ad0496b`.
- ✅ **HIGH — `Library.scan` surfaces real I/O errors.** `src/album_builder/domain/track.py`. New `_open_tags` helper unwraps OSError from MutagenError; PermissionError now propagates instead of silently dropping the file. Commit `cbeca8e`.
- ✅ **HIGH — `LibraryPane` filter includes `album_artist`.** `src/album_builder/ui/library_pane.py`. New `TrackFilterProxy` subclass overrides `filterAcceptsRow` to consult the underlying Track's `SEARCH_FIELDS`, matching domain `Library.search()` semantics. Commit `87ec172`.

## 🔒 Tier 2 — hardening sweep (correctness)

✅ **All 7 landed 2026-04-28** (6 from this sweep + 1 free fix folded into Tier 1.2). 57/57 tests pass; ruff + shellcheck clean.

- ✅ **HIGH — Three-way version split.** `src/album_builder/app.py` now imports `__version__` from `album_builder.version` (commit `ad0496b`, folded into Tier 1.2 since the file was already being touched).
- ✅ **HIGH — install.sh Python version check uses the wrong interpreter.** Now uses `"$PY"` consistently for both version read AND comparison; tuple compare via `sys.version_info >= (3, 11)`. Commit `a7dc745`.
- ✅ **HIGH — Non-deterministic COMM/USLT frame selection.** New `_pick_localised()` helper in `track.py` prefers `lang == "eng"` and falls back to the first non-empty other language. Empty English frames no longer shadow populated alternatives. Commit `cd829d4`.
- ✅ **HIGH — JPEG covers silently dropped.** Field renamed `cover_png → cover_data` + new `cover_mime`. `_first_apic_image()` accepts any `image/*` MIME (PNG, JPEG, WebP, GIF). Spec 01 updated. Commit `cd829d4`.
- ✅ **HIGH — WCAG AA contrast failure on placeholder text.** New `text_placeholder` palette token at `#9a9da8` (6.4:1 vs `bg_pane`). New `QLabel#PlaceholderText` QSS rule replaces inline `setStyleSheet`. Test asserts ratio via WCAG 2.2 luminance formula. Commit `b632264`.
- ✅ **HIGH — `TrackTableModel.data()` no row-bounds guard.** Explicit `if index.row() >= len(self._tracks): return None` after the validity check; stale proxy indices no longer crash via `IndexError` into Qt's C++ slot dispatch. Commit `b54466d`.
- ✅ **MEDIUM — No default sort applied at construction.** `LibraryPane.__init__` now calls `sortByColumn(0, AscendingOrder)`. Commit `b54466d`.

## ⚡ Tier 3 — structural / cosmetic

✅ **Sweep complete 2026-04-28.** 11 fixes landed; 2 carried forward (Phase 4 prep + intentional INFO defer). 65/65 tests pass; ruff + shellcheck clean.

- ✅ **MEDIUM — `pgrep` regex tightened.** `python[0-9.]*` matches `python`, `python3`, `python3.11`, `python3.13` — but not `pythonista` or random binaries.
- ✅ **MEDIUM — `.desktop` Exec= dead `%F` removed.** App doesn't parse argv files; the field was a Phase-1 placeholder.
- ✅ **MEDIUM — install.sh swallows cache-refresh errors.** `2>/dev/null` removed; `|| true` preserved. Folded into Theme 2 sweep.
- ✅ **MEDIUM — Focus ring 2px outline.** New `QPushButton:focus`, `QTableView:focus`, `QLineEdit:focus` rules with `2px solid accent_primary_1`. Padding compensated to avoid layout shift.
- ✅ **MEDIUM — Library pane column resize policy.** Title=Stretch, all others=Interactive with sensible default widths (140/160/140/70 px). Min table width 420 px.
- ✅ **MEDIUM — `Library.tracks` is now `tuple[Track, ...]`.** `__post_init__` coerces incoming iterables; Library is hashable; mutation through the frozen boundary blocked.
- ✅ **LOW — `cover_data` rename + spec sync.** Resolved by Tier 2.D (rename `cover_png → cover_data`/`cover_mime` + accept any `image/*` MIME). Spec 01 already updated.
- ✅ **LOW — Tmp filename collision.** `_unique_tmp_path()` suffixes with PID + 8 hex chars of `uuid4`. Concurrent Phase-2 debounce writers no longer collide.
- ✅ **LOW — `[[ $PURGE -eq 0 ]] && echo …` brittleness.** Converted to `if`-block; `set -e` safe.
- ✅ **LOW — `Library.search()` doesn't filter `is_missing`.** Carried forward into Phase 2 deliverables (only meaningful once `is_missing` is reachable post-rescan).
- ✅ **LOW — QScrollBar QSS styling.** Dark-theme scrollbars: `bg_pane` track, `border_strong` → `text_tertiary`-on-hover handle, 5px radius, no arrow buttons.
- ✅ **LOW — Splitter ratios.** `[500, 350, 550]` → `[5, 3, 5]` — HiDPI-friendly.
- ✅ **LOW — README WeasyPrint system-deps.** Closed in v0.5.1 sweep: README §System dependencies lists Pango / Cairo / GDK-PixBuf install commands for openSUSE + Debian/Ubuntu, with link to WeasyPrint's per-distro guide.
- ✅ **INFO — `track_at()` only used by tests.** Closed in v0.3.0: `LibraryPane._on_table_clicked` and `_on_double_click` consume `track_at()` for preview-play row → Track resolution.


## 🔭 Future / deferred

- Group-by-artist tabs (Spec 00 roadmap)
- Tap-along LRC editor for manual alignment correction
- Multi-project (multiple Tracks/ folders open at once)
- Album cover compositing
- Bulk pre-alignment scheduler
- Light-theme support / themable palette
- Recursive subfolder scanning under Tracks/

---

*Last reviewed: 2026-04-30 — v0.5.0 (Phase 4: Export & Approval) shipped. 4-round pre-implementation spec sweep (39 → 17 → 3 → 0 findings) + implementation + 3-round post-implementation `/audit` + `/indie-review` (40 → 3 → 0 findings) + full-codebase audit (ruff/bandit/semgrep/gitleaks all clean). 467 passing tests (+52 since v0.4.2). Specs 02 / 08 / 09 / 10 / 11 grew from 996 → ~1,140 lines with 16 new TC contracts. Phases 1–4 are feature-complete and hardened.*

*Round-1 spec sweep landed 2026-04-28 (32 issues across all 13 specs: schema-ownership canonicalised to Spec 10, approve-with-missing contradiction resolved, Specs 06–12 received TC-NN-MM IDs at speccing time, global keyboard-shortcuts table added to Spec 00, canonical approve sequence pinned in Spec 09, Spec 11 §Glyphs added to single-source `⋮⋮ ▲▼ ●○ 🔒 ✓ ▶ ⏸` etc.). Round-2 sweep landed 2026-04-28 (28 follow-ups: timestamp-encoding precision pin, atomic-write-tmp-strategy alignment, plan timestamp helper, approve/unapprove side-effect ordering, plan TC crosswalk extended to TC-10/TC-11/TC-01-P2). Round-3 sweep landed 2026-04-28 (15 follow-ups: state-diagram terminology, splitter ratios on save, glyph literals in widgets, approved-album badge, rename self-collision, UTC normalisation, TC-10-09 + TC-10-20 strengthened, delete emit order). Round-4 confirmation pass 2026-04-28 verified all fixes landed cleanly with 0 surviving HIGH issues and 0 new contradictions. **Documentation set is implementation-ready for Phase 2.**
