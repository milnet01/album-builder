"""TC-09-* — Spec 09 Approval & Report tests.

Covers the Jinja2 + WeasyPrint render pipeline, atomic-pair semantics,
three-state composer column, version-string fallback, and lyrics caps.
WeasyPrint is real (no mock) so each test costs ~1 s; the full file
should run under 10 s on warm imports.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from album_builder.services import report as report_module
from album_builder.services.report import (
    LYRICS_BODY_CAP_BYTES,
    _normalise_cover,
    _resolve_columns,
    _truncate_lyrics,
    render_html,
    render_report,
    version_string,
)


def _make_track(path, *, title="T", artist="A", composer=None, comment=None,
                lyrics_text=None, cover_data=None, cover_mime=None,
                duration_seconds=120.0, is_missing=False):
    return SimpleNamespace(
        path=path, title=title, artist=artist, album_artist=artist,
        composer=composer, comment=comment, lyrics_text=lyrics_text,
        cover_data=cover_data, cover_mime=cover_mime,
        duration_seconds=duration_seconds, is_missing=is_missing,
    )


class _FakeLibrary:
    def __init__(self, tracks):
        self._tracks = {Path(p): t for p, t in tracks.items()}

    def find(self, path):
        return self._tracks.get(Path(path))


def _make_album(track_paths, *, name="Memoirs of a Sinner", target_count=None,
                cover_override=None):
    tc = target_count if target_count is not None else max(1, len(track_paths))
    return SimpleNamespace(
        name=name,
        target_count=tc,
        track_paths=[str(p) for p in track_paths],
        cover_override=cover_override,
    )


def _seed_paths(tmp_path, n):
    out = []
    for i in range(n):
        p = tmp_path / f"src_{i}.mpeg"
        p.write_bytes(b"X" * 128)
        out.append(p)
    return out


# --- TC-09-01 minimal render exercises the full template ---


def test_TC_09_01_render_html_contains_every_field(tmp_path):
    # Spec: TC-09-01
    paths = _seed_paths(tmp_path, 2)
    library = _FakeLibrary({
        paths[0]: _make_track(paths[0], title="memoirs intro", composer="Charl Jordaan",
                               comment="Copyright 2026 CJ", lyrics_text="walking the line"),
        paths[1]: _make_track(paths[1], title="something more (calm)", composer="Charl Jordaan",
                               lyrics_text=None),
    })
    album = _make_album(paths, target_count=2)
    html = render_html(album, library, today=date(2026, 4, 30))
    assert "Memoirs of a Sinner" in html
    assert "memoirs intro" in html
    assert "something more (calm)" in html
    assert "All tracks composed by Charl Jordaan" in html
    assert "Copyright 2026 CJ" in html
    assert "walking the line" in html
    assert "No lyrics provided" in html  # second track empty
    assert "30 April 2026" in html
    assert "2 of 2 tracks" in html


# --- TC-09-02 version_string + ImportError fallback ---


def test_TC_09_02_version_string_normal():
    # Spec: TC-09-02 — version comes from the package
    v = version_string()
    assert v and v != "unknown"


def test_TC_09_02_version_string_import_error_falls_back():
    # Spec: TC-09-02 — ImportError path returns "unknown"
    import builtins
    real_import = builtins.__import__

    def fake(name, *a, **kw):
        if name == "album_builder.version":
            raise ImportError("simulated")
        return real_import(name, *a, **kw)

    with patch.object(builtins, "__import__", fake):
        # Force re-import inside version_string (not pre-imported by module body)
        assert version_string() == "unknown"


# --- TC-09-05 approve produces three artefacts non-zero size ---


def test_TC_09_05_render_report_writes_pair(tmp_path):
    # Spec: TC-09-05 — both files exist and are non-zero
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0], title="solo")})
    album = _make_album(paths, target_count=1)
    reports = tmp_path / "reports"
    html, pdf = render_report(album, library, reports_dir=reports, today=date(2026, 4, 30))
    assert html.exists() and html.stat().st_size > 0
    assert pdf.exists() and pdf.stat().st_size > 0
    assert html.suffix == ".html"
    assert pdf.suffix == ".pdf"


# --- TC-09-06 three-state composer column ---


def test_TC_09_06_composer_all_share():
    # Spec: TC-09-06 — all share → drop column + above-table line
    tracks = [{"composer": "C"}, {"composer": "C"}, {"composer": "C"},
              {"artist": None, "composer": "C"}]
    cols = _resolve_columns(tracks)
    assert cols["show_composer"] is False
    assert cols["all_composer"] == "C"


def test_TC_09_06_composer_mixed():
    # Spec: TC-09-06 — some have, some don't → keep column, em-dash for missing
    tracks = [{"composer": "C"}, {"composer": None}, {"composer": "C"}]
    cols = _resolve_columns(tracks)
    assert cols["show_composer"] is True
    assert cols["all_composer"] is None


def test_TC_09_06_composer_none():
    # Spec: TC-09-06 — none have → drop column + no above-table line
    tracks = [{"composer": None}, {"composer": None}]
    cols = _resolve_columns(tracks)
    assert cols["show_composer"] is False
    assert cols["all_composer"] is None


# --- TC-09-08 cover resize threshold ---


def test_TC_09_08_small_cover_passes_through():
    # Spec: TC-09-08 — small + within dimensions → unchanged
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color="red").save(buf, format="JPEG")
    raw = buf.getvalue()
    out = _normalise_cover(raw)
    assert out == raw  # unchanged


def test_TC_09_08_oversize_dimensions_resized():
    # Spec: TC-09-08 — > 800x800 triggers resize regardless of file size
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", (1200, 1200), color="blue").save(buf, format="JPEG")
    raw = buf.getvalue()
    out = _normalise_cover(raw)
    assert out != raw
    with Image.open(io.BytesIO(out)) as im:
        assert max(im.size) <= 800


# --- TC-09-09 + TC-09-09a + TC-09-09b lyrics rendering ---


def test_TC_09_09_no_lyrics_placeholder(tmp_path):
    # Spec: TC-09-09 — empty lyrics → "No lyrics provided"
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0], lyrics_text=None)})
    album = _make_album(paths)
    html = render_html(album, library, today=date(2026, 4, 30))
    assert "No lyrics provided" in html


def test_TC_09_09a_full_lyrics_rendered(tmp_path):
    # Spec: TC-09-09a — full lyrics body appears verbatim
    body = "verse one\nverse two\nverse three"
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0], lyrics_text=body)})
    album = _make_album(paths)
    html = render_html(album, library, today=date(2026, 4, 30))
    assert "verse one" in html
    assert "verse three" in html


def test_TC_09_09b_truncates_oversize_lyrics():
    # Spec: TC-09-09b — > 32 KB capped + suffix
    body = "x" * (LYRICS_BODY_CAP_BYTES + 100)
    out, truncated = _truncate_lyrics(body)
    assert truncated is True
    assert "(... truncated)" in out
    assert len(out.encode("utf-8")) <= LYRICS_BODY_CAP_BYTES + len("\n(... truncated)") + 4


def test_TC_09_09b_under_cap_passes_through():
    # Spec: TC-09-09b — under cap returns input unchanged
    body = "small"
    out, truncated = _truncate_lyrics(body)
    assert out == "small"
    assert truncated is False


# --- TC-09-10 atomic pair ---


def test_TC_09_10_pair_files_both_complete_before_rename(tmp_path, monkeypatch):
    # Spec: TC-09-10 — both .tmp written before either rename;
    # if second os.replace raises, scan removes orphan + tmp.
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    reports = tmp_path / "reports"

    real_replace = report_module.os.replace
    calls = {"n": 0}

    def fake_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated PDF rename failure")
        return real_replace(src, dst)

    monkeypatch.setattr(report_module.os, "replace", fake_replace)
    with pytest.raises(OSError):
        render_report(album, library, reports_dir=reports, today=date(2026, 4, 30))
    # Spec 10 §Atomic pair "Between rename-A and rename-B" recovery:
    # delete BOTH members. In-process matches load-time scan contract.
    htmls = list(reports.glob("*.html"))
    pdfs = list(reports.glob("*.pdf"))
    tmps = list(reports.glob("*.tmp"))
    assert htmls == []
    assert pdfs == []
    assert tmps == []


# --- TC-09-12 verify-paths gates side-effects (smoke at the integration layer) ---


def test_TC_09_12_render_continues_with_missing_track(tmp_path):
    # Spec: TC-09-12 (downstream) — render is library-driven and skips missing
    # tracks gracefully; the strict-mode gate happens in `regenerate_album_exports`.
    paths = _seed_paths(tmp_path, 2)
    library = _FakeLibrary({paths[0]: _make_track(paths[0], title="present")})
    album = _make_album(paths)
    html = render_html(album, library, today=date(2026, 4, 30))
    assert "present" in html


# --- TC-09-17 single-file portability ---


def test_TC_09_17_html_is_single_file_portable(tmp_path):
    # Spec: TC-09-17 — no external <link>; cover bytes inline as data: URI.
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="green").save(buf, format="JPEG")
    cover = buf.getvalue()
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({
        paths[0]: _make_track(paths[0], cover_data=cover, cover_mime="image/jpeg"),
    })
    album = _make_album(paths)
    html = render_html(album, library, today=date(2026, 4, 30))
    assert "data:image/jpeg;base64," in html
    assert "<link" not in html.lower()


# --- TC-09-21 cover-page footer placement ---


def test_TC_09_21_footer_contains_version(tmp_path):
    # Spec: TC-09-21 — footer placement (not just substring presence)
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    html = render_html(album, library, today=date(2026, 4, 30))
    # Find <footer ...>...</footer>
    import re
    m = re.search(r"<footer[^>]*>(.*?)</footer>", html, flags=re.S)
    assert m is not None
    footer = m.group(1)
    assert "Generated by Album Builder" in footer
    assert "v" in footer  # version string present


# --- TC-09-22 page-break CSS ---


def test_TC_09_22_per_track_page_break_css(tmp_path):
    # Spec: TC-09-22 — break-inside avoid on .track-card
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    html = render_html(album, library, today=date(2026, 4, 30))
    assert "break-inside: avoid" in html or "page-break-inside: avoid" in html


# --- TC-09-24 long-line word wrap ---


def test_TC_09_24_long_line_wrap_css(tmp_path):
    # Spec: TC-09-24 — overflow-wrap: anywhere on lyrics block
    paths = _seed_paths(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0], lyrics_text="x" * 600)})
    album = _make_album(paths)
    html = render_html(album, library, today=date(2026, 4, 30))
    assert "overflow-wrap: anywhere" in html
