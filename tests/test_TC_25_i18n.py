"""i18n helper - Spec 25 §Public API `i18n.py`, TC-25-01/02/05."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder import i18n


@pytest.fixture(autouse=True)
def _english_after():
    yield
    i18n.set_language("en")


# Spec: TC-25-01
def test_english_is_identity_and_formats_fields() -> None:
    i18n.set_language("en")
    assert i18n.tr("New Album") == "New Album"
    assert i18n.tr("Restored '{name}'.", name="X") == "Restored 'X'."
    assert i18n.N_("Title") == "Title"


# Spec: TC-25-02
def test_set_language_loads_catalog_and_falls_back(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "de.json").write_text(
        json.dumps({"@language_name": "Deutsch", "New Album": "Neues Album"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "CATALOG_DIR", tmp_path)
    i18n.set_language("de")
    assert i18n.current_language() == "de"
    assert i18n.tr("New Album") == "Neues Album"
    assert i18n.tr("Not in catalog") == "Not in catalog"
    assert i18n.language_name("de") == "Deutsch"

    i18n.set_language("xx")                      # unsupported code
    assert i18n.current_language() == "en"
    assert i18n.tr("New Album") == "New Album"

    i18n.set_language("fr")                      # supported, but no file here
    assert i18n.current_language() == "en"
    assert i18n.tr("New Album") == "New Album"


# Spec: TC-25-02
def test_set_catalog_installs_mapping() -> None:
    i18n.set_catalog({"New Album": "[New Album]"})
    assert i18n.tr("New Album") == "[New Album]"


# Spec: TC-25-05
@pytest.mark.parametrize(("setting", "system", "expected"), [
    ("system", "de", "de"),
    ("system", "ja", "en"),
    ("fr", "de", "fr"),
    ("klingon", "de", "de"),
])
def test_resolve(setting: str, system: str, expected: str) -> None:
    assert i18n.resolve(setting, system) == expected


# Spec: TC-25-08
def test_rtl_set() -> None:
    assert i18n.RTL == frozenset({"ar", "he"})
    assert set(i18n.RTL) <= set(i18n.SUPPORTED)
