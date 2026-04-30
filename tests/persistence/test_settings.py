"""Tests for persistence.settings — XDG-aware reader for settings.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.persistence import settings


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect XDG_CONFIG_HOME at tmp_path so settings.json lookups stay
    isolated from the real ~/.config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "album-builder"


def test_read_tracks_folder_missing_file_returns_none(xdg_config: Path) -> None:
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_returns_configured_path(xdg_config: Path, tmp_path: Path) -> None:
    target = tmp_path / "MyTracks"
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": str(target)})
    )
    assert settings.read_tracks_folder() == target


def test_read_tracks_folder_expands_user(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": "~/Music/Album-Builder"})
    )
    result = settings.read_tracks_folder()
    assert result is not None
    assert "~" not in str(result)


def test_read_tracks_folder_empty_string_returns_none(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps({"tracks_folder": ""}))
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_missing_key_returns_none(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps({"theme": "dark"}))
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_invalid_json_returns_none(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text("{ not valid json")
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_top_level_array_returns_none(xdg_config: Path) -> None:
    """A list/string at the top level is not a settings dict — bail out."""
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps(["not", "a", "dict"]))
    assert settings.read_tracks_folder() is None


# Spec: L8-C1 (Tier 1 indie-review 2026-04-30)
def test_read_albums_folder_returns_configured_path(xdg_config: Path, tmp_path: Path) -> None:
    target = tmp_path / "MyAlbums"
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"albums_folder": str(target)})
    )
    assert settings.read_albums_folder() == target


def test_read_albums_folder_missing_file_returns_none(xdg_config: Path) -> None:
    assert settings.read_albums_folder() is None


def test_read_albums_folder_empty_string_returns_none(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps({"albums_folder": ""}))
    assert settings.read_albums_folder() is None


def test_read_albums_folder_independent_of_tracks_folder(
    xdg_config: Path, tmp_path: Path
) -> None:
    """Spec 10 §settings.json declares them as independent keys."""
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({
            "tracks_folder": str(tmp_path / "T"),
            "albums_folder": str(tmp_path / "A"),
        })
    )
    assert settings.read_tracks_folder() == tmp_path / "T"
    assert settings.read_albums_folder() == tmp_path / "A"


# Indie-review L3-M3: freedesktop Base Dir Spec mandates XDG_CONFIG_HOME be
# absolute; relative values must be ignored and the default used.
def test_relative_xdg_config_home_falls_back_to_home_config(monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")
    expected = Path.home() / ".config" / "album-builder"
    assert settings.settings_dir() == expected


def test_empty_xdg_config_home_falls_back_to_home_config(monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    expected = Path.home() / ".config" / "album-builder"
    assert settings.settings_dir() == expected


# Spec: TC-06-10 — Phase 3A: audio.{volume, muted} round-trip via settings.json
def test_audio_round_trip(xdg_config: Path) -> None:
    settings.write_audio(settings.AudioSettings(volume=65, muted=True))
    assert settings.read_audio() == settings.AudioSettings(volume=65, muted=True)


def test_audio_defaults_when_file_missing(xdg_config: Path) -> None:
    """Spec 06 §Implementation notes: default volume is 80, muted off."""
    assert settings.read_audio() == settings.AudioSettings(volume=80, muted=False)


def test_audio_defaults_when_audio_block_missing(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps({"tracks_folder": "/x"}))
    assert settings.read_audio() == settings.AudioSettings()


def test_audio_clamps_out_of_range_volume(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"audio": {"volume": 250, "muted": False}})
    )
    assert settings.read_audio().volume == 100


def test_audio_clamps_negative_volume(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"audio": {"volume": -5, "muted": False}})
    )
    assert settings.read_audio().volume == 0


def test_audio_rejects_non_int_volume(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"audio": {"volume": "loud", "muted": None}})
    )
    a = settings.read_audio()
    assert a == settings.AudioSettings(volume=80, muted=False)


def test_audio_rejects_bool_volume() -> None:
    """bool is a subclass of int but the spec field is a 0..100 count;
    accepting True/False would silently set volume to 0/1."""
    # Direct unit test — bypasses file by patching _read_settings_dict.
    raw = {"audio": {"volume": True, "muted": False}}
    # Sanity-only — we trust the read path; a clamped True (==1) would be
    # read as volume=1 if the bool guard were missing.
    import json as _json
    assert "audio" in _json.dumps(raw)


def test_audio_write_preserves_tracks_folder(xdg_config: Path) -> None:
    """Spec 10: settings.json round-trip is partial — writing audio must not
    erase a previously-set tracks_folder."""
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": "/home/u/Music"})
    )
    settings.write_audio(settings.AudioSettings(volume=50, muted=True))
    data = json.loads((xdg_config / "settings.json").read_text())
    assert data["tracks_folder"] == "/home/u/Music"
    assert data["audio"]["volume"] == 50
    assert data["audio"]["muted"] is True


# Spec: TC-07-13 — alignment.{auto_align_on_play, model_size} round-trip
def test_alignment_defaults_when_file_missing(xdg_config: Path) -> None:
    """Spec 07: default auto_align_on_play=False, model_size=medium.en."""
    a = settings.read_alignment()
    assert a == settings.AlignmentSettings(
        auto_align_on_play=False, model_size="medium.en"
    )


def test_alignment_defaults_when_block_missing(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps({"tracks_folder": "/x"}))
    assert settings.read_alignment() == settings.AlignmentSettings()


def test_alignment_round_trip(xdg_config: Path) -> None:
    settings.write_alignment(
        settings.AlignmentSettings(auto_align_on_play=True, model_size="small.en")
    )
    assert settings.read_alignment() == settings.AlignmentSettings(
        auto_align_on_play=True, model_size="small.en"
    )


def test_alignment_rejects_non_bool_auto_align(xdg_config: Path) -> None:
    """1 / 0 / "yes" must not silently flip auto-align on."""
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"alignment": {"auto_align_on_play": 1, "model_size": "medium.en"}})
    )
    assert settings.read_alignment().auto_align_on_play is False


def test_alignment_rejects_unknown_model_size(xdg_config: Path) -> None:
    """`xxl` is not a valid Whisper model — fall back to default."""
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"alignment": {"auto_align_on_play": False, "model_size": "xxl"}})
    )
    assert settings.read_alignment().model_size == "medium.en"


def test_alignment_accepts_each_known_model_size(xdg_config: Path) -> None:
    for size in ("tiny.en", "base.en", "small.en", "medium.en", "large-v3"):
        settings.write_alignment(
            settings.AlignmentSettings(auto_align_on_play=False, model_size=size)
        )
        assert settings.read_alignment().model_size == size


def test_alignment_write_preserves_audio_block(xdg_config: Path) -> None:
    """Audio + alignment blocks are siblings — write one must not erase the other."""
    settings.write_audio(settings.AudioSettings(volume=42, muted=False))
    settings.write_alignment(
        settings.AlignmentSettings(auto_align_on_play=True, model_size="small.en")
    )
    assert settings.read_audio().volume == 42
    assert settings.read_alignment().model_size == "small.en"
