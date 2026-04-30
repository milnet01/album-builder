"""TC-10-21..23 — Spec 10 §Atomic pair load-time scan tests."""

from __future__ import annotations

from pathlib import Path

from album_builder.persistence.atomic_pair import scan_reports_dir


def _make_pair(reports_dir: Path, name: str, stem: str, *, html_final=True, pdf_final=True,
               html_tmp=False, pdf_tmp=False) -> tuple[Path, Path, Path | None, Path | None]:
    html_p = reports_dir / f"{name} - {stem}.html"
    pdf_p = reports_dir / f"{name} - {stem}.pdf"
    html_tmp_p = reports_dir / f"{name} - {stem}.html.12345.abcdef01.tmp" if html_tmp else None
    pdf_tmp_p = reports_dir / f"{name} - {stem}.pdf.12345.abcdef01.tmp" if pdf_tmp else None
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
