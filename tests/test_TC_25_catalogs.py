"""Translation catalogs and the translated report - Spec 25 TC-25-03/04/10/12."""

from __future__ import annotations

import json
import string
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from album_builder import i18n
from tests.i18n.keys import collect

CATALOGS = {c: i18n.CATALOG_DIR / f"{c}.json" for c in i18n.SUPPORTED if c != "en"}


def _load(code: str) -> dict[str, str]:
    return json.loads(CATALOGS[code].read_text(encoding="utf-8"))


def _fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


# Spec: TC-25-03
def test_catalogs_cover_exactly_the_source_strings() -> None:
    keys, problems = collect()
    assert not problems, problems
    assert keys, "no tr()/N_() source strings found"
    for code in CATALOGS:
        have = set(_load(code)) - {i18n.LANGUAGE_NAME_KEY}
        assert not keys - have, f"{code}: missing {sorted(keys - have)[:20]}"
        assert not have - keys, f"{code}: stale {sorted(have - keys)[:20]}"
        assert _load(code).get(i18n.LANGUAGE_NAME_KEY), f"{code}: no @language_name"


# Spec: TC-25-04
def test_translations_keep_their_placeholders() -> None:
    for code in CATALOGS:
        for source, text in _load(code).items():
            if source == i18n.LANGUAGE_NAME_KEY:
                continue
            assert _fields(text) == _fields(source), f"{code}: {source!r} -> {text!r}"


# Spec: TC-25-12
def test_bundled_font_draws_every_catalog_character() -> None:
    try:
        font_file = subprocess.run(
            ["fc-match", "-f", "%{file}", "DejaVu Sans"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("fontconfig not available to locate DejaVu Sans")
    if "DejaVuSans" not in Path(font_file).name:
        pytest.skip(f"DejaVu Sans is not installed (fc-match gave {font_file!r})")
    from fontTools.ttLib import TTFont

    cmap = TTFont(font_file).getBestCmap()
    for code in CATALOGS:
        chars = {ch for text in _load(code).values() for ch in text if not ch.isspace()}
        missing = sorted(ch for ch in chars if ord(ch) not in cmap)
        assert not missing, f"{code}: DejaVu Sans lacks {missing[:20]}"


# Spec: TC-25-10
def test_report_renders_right_to_left_in_hebrew(tmp_path: Path) -> None:
    from album_builder.services.report import render_html, render_pdf_from_html

    track_path = tmp_path / "a.mp3"
    track_path.write_bytes(b"x")
    track = SimpleNamespace(
        path=track_path, title="T", artist="A", album_artist="A", composer=None,
        comment=None, lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=120.0, is_missing=False,
    )
    library = SimpleNamespace(find=lambda p: track if Path(p) == track_path else None)
    album = SimpleNamespace(
        name="Album", target_count=1, track_paths=[str(track_path)], cover_override=None,
    )
    i18n.set_language("he")
    try:
        html = render_html(album, library, today=date(2026, 9, 8))
        assert '<html lang="he" dir="rtl">' in html
        assert _load("he")["Title"] in html
        assert render_pdf_from_html(html)
    finally:
        i18n.set_language("en")
