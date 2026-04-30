"""Atomic-pair load-time scan (Spec 10 §Atomic pair (multi-file transactions)).

Spec 09's canonical approve sequence writes the report as a `(html, pdf)`
pair: both `.tmp` siblings are written first, then both are renamed via
`os.replace`. A crash between the two renames leaves exactly one final
+ one `.tmp`; the load-time scan deletes both members so re-approve lands
in a clean directory.

Public API:
- `scan_reports_dir(reports_dir, *, sanitised_name)` - idempotent cleanup
  of half-pairs, stale `.tmp` siblings, and orphan tmps alongside complete
  pairs. Called from `AlbumStore.rescan()` per album. No-op when the
  directory is missing or clean.
"""

from __future__ import annotations

import glob as _glob
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _final_pair_for(reports_dir: Path, sanitised_name: str, date_stem: str) -> tuple[Path, Path]:
    return (
        reports_dir / f"{sanitised_name} - {date_stem}.html",
        reports_dir / f"{sanitised_name} - {date_stem}.pdf",
    )


def _tmp_siblings(reports_dir: Path, sanitised_name: str, date_stem: str) -> list[Path]:
    """Return any `.tmp` siblings whose final-name prefix matches the pair.

    `atomic_io._unique_tmp_path` produces `<final>.<pid>.<uuid8>.tmp`,
    so the glob pattern is `<final>.*.tmp` for both `.html` and `.pdf`
    finals. `glob.escape` defends against album names containing `[` or
    `]` (sanitise_title doesn't strip these); without escaping, such
    names silently fail to match their own tmps.
    """
    name_glob = _glob.escape(sanitised_name)
    out: list[Path] = []
    for ext in ("html", "pdf"):
        out.extend(reports_dir.glob(f"{name_glob} - {date_stem}.{ext}.*.tmp"))
    return out


def _date_stems_in(reports_dir: Path, sanitised_name: str) -> set[str]:
    """Distinct YYYY-MM-DD stems for which any HTML/PDF/tmp file exists."""
    stems: set[str] = set()
    name_re = re.escape(sanitised_name)
    pattern = re.compile(rf"^{name_re} - (\d{{4}}-\d{{2}}-\d{{2}})")
    for entry in reports_dir.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        # `.html.<pid>.<uuid>.tmp` -> strip `.tmp` then re-match below.
        stripped = name[:-4] if name.endswith(".tmp") else name
        m = pattern.match(stripped)
        if m:
            stems.add(m.group(1))
    return stems


def _try_unlink(path: Path) -> bool:
    """Return True iff path is gone after the call (was unlinked or
    never existed). False on OSError - caller decides whether the
    incomplete cleanup invalidates the parent operation."""
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError as exc:
        logger.warning("atomic-pair: unlink %s failed: %s", path, exc)
        return False


def scan_reports_dir(reports_dir: Path, *, sanitised_name: str) -> dict[str, int]:
    """Sweep the reports/ directory for half-pairs and stale `.tmp` siblings.

    Idempotent: a clean directory (both finals, no tmps) is a no-op.
    Returns a small stats dict for telemetry / tests:
      - `pairs_completed`: count of date stems where both finals exist.
        Increments only when no leftover `.tmp` siblings exist for that
        stem (a clean state).
      - `pairs_repaired`: count where exactly one final was found and
        removed AND every related `.tmp` was successfully unlinked. A
        partial cleanup (one of the unlinks raised) does NOT count as
        repaired - the next scan retries.
      - `tmps_swept`: count of `.tmp` files removed where no final yet
        existed for that date stem AND every unlink succeeded.

    Empty `sanitised_name` is rejected (would collapse the regex/glob
    prefix and false-match every file).
    """
    stats = {"pairs_completed": 0, "pairs_repaired": 0, "tmps_swept": 0}
    if not sanitised_name:
        return stats
    if not reports_dir.exists() or not reports_dir.is_dir():
        return stats
    for stem in _date_stems_in(reports_dir, sanitised_name):
        html_final, pdf_final = _final_pair_for(reports_dir, sanitised_name, stem)
        tmps = _tmp_siblings(reports_dir, sanitised_name, stem)
        has_html = html_final.exists()
        has_pdf = pdf_final.exists()

        # Branch 1: clean pair, no leftovers.
        if has_html and has_pdf and not tmps:
            stats["pairs_completed"] += 1
            continue

        # Branch 2: clean pair PLUS leftover tmps (rare - re-approve
        # interrupted Phase 1 of a same-day retry). Sweep the stale tmps;
        # the pair survives.
        if has_html and has_pdf and tmps:
            tmps_ok = all(_try_unlink(t) for t in tmps)
            if tmps_ok:
                stats["pairs_completed"] += 1
                stats["tmps_swept"] += 1
                logger.info(
                    "atomic-pair: swept %d stale tmp(s) alongside complete pair %s",
                    len(tmps), stem,
                )
            continue

        # Branch 3: half-pair (one final, the other absent). Delete the
        # surviving final + every related tmp. Only count `pairs_repaired`
        # when EVERY unlink succeeded - the spec contract is "delete both",
        # so partial completion stays "needs another scan".
        if has_html != has_pdf:
            unlinks: list[bool] = []
            for p in (html_final, pdf_final):
                if p.exists():
                    if _try_unlink(p):
                        logger.warning("atomic-pair: removed orphan final %s", p.name)
                        unlinks.append(True)
                    else:
                        unlinks.append(False)
            for tmp in tmps:
                unlinks.append(_try_unlink(tmp))
            if unlinks and all(unlinks):
                stats["pairs_repaired"] += 1
            continue

        # Branch 4: phase-1-mid-crash (no finals, only tmps).
        if tmps and not (has_html or has_pdf):
            unlinks = [_try_unlink(t) for t in tmps]
            if unlinks and all(unlinks):
                stats["tmps_swept"] += 1
                logger.info(
                    "atomic-pair: swept %d stale tmp(s) for stem %s",
                    len(tmps), stem,
                )
    return stats
