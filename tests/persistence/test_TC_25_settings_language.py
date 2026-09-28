"""settings.json `ui.language` - Spec 25 §Public API `persistence/settings.py`, TC-25-06."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from album_builder.persistence import settings
from album_builder.persistence.settings import UiSettings, read_ui, write_ui


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


# Spec: TC-25-06
def test_language_defaults_to_system() -> None:
    assert read_ui().language == "system"


# Spec: TC-25-06
def test_language_round_trips_beside_theme() -> None:
    write_ui(UiSettings(theme="light", language="he"))
    ui = read_ui()
    assert (ui.language, ui.theme) == ("he", "light")


# Spec: TC-25-06
@pytest.mark.parametrize("raw", ["klingon", 7, None, "EN"])
def test_unknown_language_reads_as_system(raw) -> None:
    path = settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ui": {"theme": "light", "language": raw}}))
    assert read_ui().language == "system"
    assert read_ui().theme == "light"


# Spec: TC-25-06
def test_file_without_language_key_reads_system() -> None:
    path = settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ui": {"theme": "light"}}))
    assert read_ui().language == "system"
    write_ui(replace(read_ui(), language="de"))
    assert read_ui().theme == "light"
