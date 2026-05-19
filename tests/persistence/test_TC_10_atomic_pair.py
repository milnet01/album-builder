"""TC-10-21..26 — Spec 10 §Atomic pair load-time scan tests."""

from __future__ import annotations

from pathlib import Path

from album_builder.persistence.atomic_pair import scan_reports_dir


def _make_pair(reports_dir: Path, name: str, stem: str, *, html_final=True, pdf_final=True,
               html_tmp=False, pdf_tmp=False,
               artist_view: bool = False) -> tuple[Path, Path, Path | None, Path | None]:
    """Build a (html, pdf, html.tmp, pdf.tmp) quadruple on disk for either the
    full report variant or the artist-view variant. `artist_view=True` appends
    ` - artist` between the date stem and the extension, per Spec 09 §File
    naming."""
    suffix = " - artist" if artist_view else ""
    html_p = reports_dir / f"{name} - {stem}{suffix}.html"
    pdf_p = reports_dir / f"{name} - {stem}{suffix}.pdf"
    html_tmp_p = (
        reports_dir / f"{name} - {stem}{suffix}.html.12345.abcdef01.tmp"
        if html_tmp else None
    )
    pdf_tmp_p = (
        reports_dir / f"{name} - {stem}{suffix}.pdf.12345.abcdef01.tmp"
        if pdf_tmp else None
    )
    if html_final:
        html_p.write_text("html")
    if pdf_final:
        pdf_p.write_bytes(b"%PDF")
    if html_tmp_p:
        html_tmp_p.write_text("html-tmp")
    if pdf_tmp_p:
        pdf_tmp_p.write_bytes(b"%PDF-tmp")
    return html_p, pdf_p, html_tmp_p, pdf_tmp_p


def test_TC_10_21_clean_pair_is_noop(tmp_path):
    # Spec: TC-10-21 — both finals + no tmps → counted, no mutation.
    reports = tmp_path / "reports"
    reports.mkdir()
    html, pdf, _, _ = _make_pair(reports, "Album", "2026-04-30")
    stats = scan_reports_dir(reports, sanitised_name="Album")
    assert stats == {"pairs_completed": 1, "pairs_repaired": 0, "tmps_swept": 0}
    assert html.exists() and pdf.exists()


def test_TC_10_22_phase1_mid_crash_sweeps_tmps(tmp_path):
    # Spec: TC-10-22 — both .tmp present, no finals → both .tmp removed.
    reports = tmp_path / "reports"
    reports.mkdir()
    _, _, html_tmp, pdf_tmp = _make_pair(
        reports, "Album", "2026-04-30",
        html_final=False, pdf_final=False, html_tmp=True, pdf_tmp=True,
    )
    stats = scan_reports_dir(reports, sanitised_name="Album")
    assert stats["tmps_swept"] == 1
    assert stats["pairs_repaired"] == 0
    assert not html_tmp.exists()
    assert not pdf_tmp.exists()


def test_TC_10_23_phase2_half_pair_removes_both(tmp_path):
    # Spec: TC-10-23 — one final + one .tmp → both removed.
    reports = tmp_path / "reports"
    reports.mkdir()
    html, pdf, _, pdf_tmp = _make_pair(
        reports, "Album", "2026-04-30",
        html_final=True, pdf_final=False, html_tmp=False, pdf_tmp=True,
    )
    stats = scan_reports_dir(reports, sanitised_name="Album")
    assert stats["pairs_repaired"] == 1
    assert not html.exists()
    assert not pdf.exists()
    assert not pdf_tmp.exists()


def test_atomic_pair_scan_idempotent(tmp_path):
    # Spec: TC-10-21 — repeated scans don't change a clean directory.
    reports = tmp_path / "reports"
    reports.mkdir()
    _make_pair(reports, "Album", "2026-04-30")
    s1 = scan_reports_dir(reports, sanitised_name="Album")
    s2 = scan_reports_dir(reports, sanitised_name="Album")
    assert s1 == s2


def test_atomic_pair_scan_missing_dir(tmp_path):
    # No reports/ dir → all-zero stats.
    stats = scan_reports_dir(tmp_path / "no-such-dir", sanitised_name="Album")
    assert stats == {"pairs_completed": 0, "pairs_repaired": 0, "tmps_swept": 0}


def test_TC_10_24_album_name_validation():
    # Spec: TC-10-24 — names ending in date suffix are rejected.
    import pytest

    from album_builder.domain.album import Album
    with pytest.raises(ValueError, match="date suffix"):
        Album.create(name="Daily - 2026-04-30", target_count=12)


def test_album_name_validation_allows_normal_names():
    from album_builder.domain.album import Album
    a = Album.create(name="Memoirs of a Sinner", target_count=12)
    assert a.name == "Memoirs of a Sinner"


# Spec: TC-10-25 — Atomic-pair scan enumerates BOTH variants per date stem
# and processes each pair independently. A half-pair in the artist variant
# must not cascade into deleting the full variant.
def test_TC_10_25_artist_variant_half_pair_does_not_touch_full(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    # Full variant: complete, byte-identical, untouched.
    full_html, full_pdf, _, _ = _make_pair(reports, "Album", "2026-04-30")
    full_html_bytes = full_html.read_bytes()
    full_pdf_bytes = full_pdf.read_bytes()
    # Artist variant: Phase-2 mid-crash (one final renamed, one tmp pending).
    art_html, art_pdf, _, art_pdf_tmp = _make_pair(
        reports, "Album", "2026-04-30",
        html_final=True, pdf_final=False, html_tmp=False, pdf_tmp=True,
        artist_view=True,
    )

    stats = scan_reports_dir(reports, sanitised_name="Album")

    # Full pair survives byte-identically.
    assert full_html.exists() and full_pdf.exists()
    assert full_html.read_bytes() == full_html_bytes
    assert full_pdf.read_bytes() == full_pdf_bytes
    # Artist pair: both members removed (the orphan final + the .tmp).
    assert not art_html.exists()
    assert not art_pdf.exists()
    assert not art_pdf_tmp.exists()
    # Stats: 1 completed pair (full), 1 repaired pair (artist half-pair).
    assert stats["pairs_completed"] == 1
    assert stats["pairs_repaired"] == 1


# Spec: TC-10-25 — Reverse: half-pair in full, artist complete. Full deleted,
# artist survives.
def test_TC_10_25_full_variant_half_pair_does_not_touch_artist(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    # Full variant: Phase-2 mid-crash.
    full_html, full_pdf, _, full_pdf_tmp = _make_pair(
        reports, "Album", "2026-04-30",
        html_final=True, pdf_final=False, html_tmp=False, pdf_tmp=True,
    )
    # Artist variant: complete.
    art_html, art_pdf, _, _ = _make_pair(reports, "Album", "2026-04-30", artist_view=True)
    art_html_bytes = art_html.read_bytes()
    art_pdf_bytes = art_pdf.read_bytes()

    stats = scan_reports_dir(reports, sanitised_name="Album")

    assert not full_html.exists()
    assert not full_pdf.exists()
    assert not full_pdf_tmp.exists()
    assert art_html.exists() and art_pdf.exists()
    assert art_html.read_bytes() == art_html_bytes
    assert art_pdf.read_bytes() == art_pdf_bytes
    assert stats["pairs_completed"] == 1
    assert stats["pairs_repaired"] == 1


# Spec: TC-10-25 — Both variants complete: counts as 2 pairs_completed, no
# mutation.
def test_TC_10_25_both_variants_clean_counts_two_pairs(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    _make_pair(reports, "Album", "2026-04-30")
    _make_pair(reports, "Album", "2026-04-30", artist_view=True)

    stats = scan_reports_dir(reports, sanitised_name="Album")

    assert stats["pairs_completed"] == 2
    assert stats["pairs_repaired"] == 0
    assert stats["tmps_swept"] == 0


# Spec: TC-10-26 — Artist-only-on-disk (e.g., user manually removed the full
# pair) still surfaces the date stem so the scan can decide complete vs
# half-pair on the artist side.
def test_TC_10_26_artist_only_on_disk_half_pair_is_repaired(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    # No full variant on disk at all. Artist variant: half-pair.
    art_html, art_pdf, _, _ = _make_pair(
        reports, "Album", "2026-04-30",
        html_final=True, pdf_final=False,
        artist_view=True,
    )

    stats = scan_reports_dir(reports, sanitised_name="Album")

    assert not art_html.exists()
    assert not art_pdf.exists()
    assert stats["pairs_repaired"] == 1


# Spec: TC-10-26 — A complete artist variant (no full variant) is counted as
# pairs_completed=1, not mis-classified as a half-pair.
def test_TC_10_26_artist_only_complete_counts_as_completed(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    art_html, art_pdf, _, _ = _make_pair(reports, "Album", "2026-04-30", artist_view=True)

    stats = scan_reports_dir(reports, sanitised_name="Album")

    assert art_html.exists() and art_pdf.exists()
    assert stats["pairs_completed"] == 1
    assert stats["pairs_repaired"] == 0


# Spec: TC-10-21 — Complete pair with stale .tmp siblings: pair stays intact,
# the orphan .tmp files are swept. This is the only path that increments
# tmps_swept alongside a non-zero pairs_completed.
def test_TC_10_21_complete_pair_with_stale_tmps_sweeps_tmps(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    html, pdf, html_tmp, pdf_tmp = _make_pair(
        reports, "Album", "2026-04-30",
        html_final=True, pdf_final=True,
        html_tmp=True, pdf_tmp=True,
    )
    html_bytes = html.read_bytes()
    pdf_bytes = pdf.read_bytes()

    stats = scan_reports_dir(reports, sanitised_name="Album")

    # Finals untouched.
    assert html.exists() and pdf.exists()
    assert html.read_bytes() == html_bytes
    assert pdf.read_bytes() == pdf_bytes
    # Orphans gone.
    assert not html_tmp.exists()
    assert not pdf_tmp.exists()
    assert stats["pairs_completed"] == 1
    assert stats["pairs_repaired"] == 0
    assert stats["tmps_swept"] == 1
