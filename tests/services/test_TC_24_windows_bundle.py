"""TC-24-01..03 — Spec 24 Windows-bundle PDF fallback + atomic-pair scan.

Locks the point-of-use PDF fallback (INV-24-6) and the PDF-parity default
(INV-24-7). The Windows build script + workflow are validated on CI plus a
manual Windows run, not here (Spec 24 §3), so this file exercises only the
app-code change, which is platform-independent.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from album_builder.persistence.atomic_pair import scan_reports_dir
from album_builder.services import report as report_module
from album_builder.services.report import render_report


def _make_track(path, *, title="T", artist="A"):
    return SimpleNamespace(
        path=path, title=title, artist=artist, album_artist=artist,
        composer=None, comment=None, lyrics_text=None,
        cover_data=None, cover_mime=None,
        duration_seconds=120.0, is_missing=False,
    )


class _FakeLibrary:
    def __init__(self, tracks):
        self._tracks = {Path(p): t for p, t in tracks.items()}

    def find(self, path):
        return self._tracks.get(Path(path))


def _one_album(tmp_path):
    src = tmp_path / "src_0.mpeg"
    src.write_bytes(b"X" * 128)
    library = _FakeLibrary({src: _make_track(src, title="solo")})
    album = SimpleNamespace(
        name="Memoirs of a Sinner",
        target_count=1,
        track_paths=[str(src)],
        cover_override=None,
    )
    return album, library


def test_TC_24_01_pdf_failure_writes_html_only(tmp_path, monkeypatch):
    # Spec: TC-24-01 — render_pdf_from_html raising -> HTML-only, no .pdf, no
    # pdf.tmp, returns (html, None), does not raise (INV-24-6 render half).
    album, library = _one_album(tmp_path)
    reports = tmp_path / "reports"

    def _boom(_html):
        raise OSError("cannot load library 'gobject-2.0-0'")

    monkeypatch.setattr(report_module, "render_pdf_from_html", _boom)
    html, pdf = render_report(album, library, reports_dir=reports, today=date(2026, 4, 30))

    assert pdf is None
    assert html.exists() and html.stat().st_size > 0
    assert html.suffix == ".html"
    # No PDF final, and nothing left in flight.
    assert list(reports.glob("*.pdf")) == []
    assert list(reports.glob("*.pdf.*.tmp")) == []


def test_TC_24_02_scan_keeps_lone_html(tmp_path):
    # Spec: TC-24-02 — a lone .html (no .pdf, no pdf.tmp) is a complete
    # single-file report: kept, counted pairs_completed, not deleted as a
    # half-pair (the anti-wipe contract, INV-24-6 stability half).
    reports = tmp_path / "reports"
    reports.mkdir()
    html = reports / "Album - 2026-04-30.html"
    html.write_text("<html>report</html>")

    stats = scan_reports_dir(reports, sanitised_name="Album")

    assert html.exists()
    assert stats["pairs_completed"] == 1
    assert stats["pairs_repaired"] == 0


@pytest.mark.slow
def test_TC_24_03_pdf_success_writes_pair(tmp_path):
    # Spec: TC-24-03 — when the PDF renders (real WeasyPrint), both finals are
    # written and returned non-None, exactly as before this phase (INV-24-7).
    album, library = _one_album(tmp_path)
    reports = tmp_path / "reports"
    html, pdf = render_report(album, library, reports_dir=reports, today=date(2026, 4, 30))
    assert html.exists() and html.stat().st_size > 0
    assert pdf is not None and pdf.exists() and pdf.stat().st_size > 0
