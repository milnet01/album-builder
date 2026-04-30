"""User settings persisted at ``$XDG_CONFIG_HOME/album-builder/settings.json``."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from album_builder.persistence.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)


DEFAULT_VOLUME = 80
DEFAULT_MUTED = False

DEFAULT_AUTO_ALIGN_ON_PLAY = False
DEFAULT_MODEL_SIZE = "medium.en"
# Spec 07 §Alignment job: WhisperX model sizes the worker recognises. Anything
# outside this set falls back to the default; v1 doesn't enforce GPU-vs-CPU
# distinctions because alignment is opt-in and the cost of a too-large model
# is borne by the user (long alignment, big disk hit), not by app stability.
ALLOWED_MODEL_SIZES = frozenset({"tiny.en", "base.en", "small.en", "medium.en", "large-v3"})


@dataclass(frozen=True)
class AudioSettings:
    """Spec 06 §Implementation notes: volume 0..100 default 80; muted bool."""

    volume: int = DEFAULT_VOLUME
    muted: bool = DEFAULT_MUTED


@dataclass(frozen=True)
class AlignmentSettings:
    """Spec 07 §Alignment job: opt-in auto-align + Whisper model size."""

    auto_align_on_play: bool = DEFAULT_AUTO_ALIGN_ON_PLAY
    model_size: str = DEFAULT_MODEL_SIZE


@dataclass(frozen=True)
class UiSettings:
    """Spec 09 §The approve flow + Spec 10 §`settings.json` schema.

    `open_report_folder_on_approve` defaults True so a fresh install opens
    the reports folder after the first approve; users who find that
    intrusive flip it off and the post-approve flow stays silent.
    """

    open_report_folder_on_approve: bool = True
    theme: str = "dark-colourful"


def settings_dir() -> Path:
    """Return the directory that holds settings.json.

    Honours ``XDG_CONFIG_HOME`` per the freedesktop Base Directory Spec; falls
    back to ``~/.config`` when unset, empty, or set to a relative path
    (the spec mandates absolute values; relative ones must be ignored).
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and Path(xdg).is_absolute():
        base = Path(xdg)
    else:
        base = Path.home() / ".config"
    return base / "album-builder"


def settings_path() -> Path:
    return settings_dir() / "settings.json"


def _read_settings_dict() -> dict:
    """Read settings.json as a dict; return ``{}`` on any failure.

    Single source of malformed-JSON / missing-file handling for every
    `read_*` helper in this module.
    """
    path = settings_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning("settings.json: unreadable (%s); falling back to default", exc)
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("settings.json: malformed JSON (%s); falling back to default", exc)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "settings.json: top-level value is not an object (%r); falling back",
            type(data).__name__,
        )
        return {}
    return data


def read_tracks_folder() -> Path | None:
    """Return the user-configured tracks folder, or ``None`` if unset.

    Returns ``None`` for any of: file missing, unreadable JSON, missing
    ``tracks_folder`` key, empty string. Callers fall back to a default.
    """
    return _read_path_key("tracks_folder")


def read_albums_folder() -> Path | None:
    """Return the user-configured albums folder, or ``None`` if unset.

    Spec 10 §settings.json schema lists ``albums_folder`` alongside
    ``tracks_folder``. Same self-heal contract as :func:`read_tracks_folder`.
    """
    return _read_path_key("albums_folder")


def _read_path_key(key: str) -> Path | None:
    data = _read_settings_dict()
    folder = data.get(key)
    if not isinstance(folder, str) or not folder.strip():
        return None
    return Path(folder).expanduser()


def read_audio() -> AudioSettings:
    """Return audio block (volume, muted), defaults if absent or malformed."""
    data = _read_settings_dict()
    audio = data.get("audio")
    if not isinstance(audio, dict):
        return AudioSettings()
    raw_vol = audio.get("volume", DEFAULT_VOLUME)
    # bool is a subclass of int — reject explicitly so True/False don't
    # silently become volume=1/0.
    if isinstance(raw_vol, bool) or not isinstance(raw_vol, int):
        volume = DEFAULT_VOLUME
    else:
        volume = max(0, min(100, raw_vol))
    raw_muted = audio.get("muted", DEFAULT_MUTED)
    muted = raw_muted if isinstance(raw_muted, bool) else DEFAULT_MUTED
    return AudioSettings(volume=volume, muted=muted)


def write_audio(audio: AudioSettings) -> None:
    """Write audio block to settings.json, preserving other top-level keys."""
    data = _read_settings_dict()
    data["audio"] = {"volume": audio.volume, "muted": audio.muted}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))


def read_alignment() -> AlignmentSettings:
    """Return alignment block (auto_align_on_play, model_size), defaults if absent.

    Spec 07: defaults are auto_align_on_play=False (alignment is opt-in) and
    model_size="medium.en" (the canonical pair faster-whisper / wav2vec2 use).
    Bool guard on auto_align_on_play; whitelist guard on model_size.
    """
    data = _read_settings_dict()
    block = data.get("alignment")
    if not isinstance(block, dict):
        return AlignmentSettings()
    raw_auto = block.get("auto_align_on_play", DEFAULT_AUTO_ALIGN_ON_PLAY)
    auto = raw_auto if isinstance(raw_auto, bool) else DEFAULT_AUTO_ALIGN_ON_PLAY
    raw_size = block.get("model_size", DEFAULT_MODEL_SIZE)
    if isinstance(raw_size, str) and raw_size in ALLOWED_MODEL_SIZES:
        size = raw_size
    else:
        size = DEFAULT_MODEL_SIZE
    return AlignmentSettings(auto_align_on_play=auto, model_size=size)


def write_alignment(alignment: AlignmentSettings) -> None:
    """Write alignment block to settings.json, preserving other top-level keys."""
    data = _read_settings_dict()
    data["alignment"] = {
        "auto_align_on_play": alignment.auto_align_on_play,
        "model_size": alignment.model_size,
    }
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))


ALLOWED_THEMES = frozenset({"dark-colourful"})
"""Spec 10 §`settings.json` schema row `ui.theme`: only `"dark-colourful"`
is valid in v1. A hand-edited `"theme": "light"` falls back to the
default rather than propagating an unknown value into the UI layer."""


def read_ui() -> UiSettings:
    """Return UI block (open_report_folder_on_approve, theme), defaults if absent.

    Spec 10 §`settings.json` schema. `open_report_folder_on_approve`
    defaults True; `theme` defaults to `"dark-colourful"` (only valid v1).
    Bool guard on `open_report_folder_on_approve` (rejects 0/1 sneaking in);
    whitelist guard on `theme` via `ALLOWED_THEMES`.
    """
    data = _read_settings_dict()
    block = data.get("ui")
    if not isinstance(block, dict):
        return UiSettings()
    raw_open = block.get("open_report_folder_on_approve", True)
    open_flag = raw_open if isinstance(raw_open, bool) else True
    raw_theme = block.get("theme", "dark-colourful")
    if isinstance(raw_theme, str) and raw_theme in ALLOWED_THEMES:
        theme = raw_theme
    else:
        theme = "dark-colourful"
    return UiSettings(open_report_folder_on_approve=open_flag, theme=theme)


def write_ui(ui: UiSettings) -> None:
    """Write UI block to settings.json, preserving other top-level keys."""
    data = _read_settings_dict()
    data["ui"] = {
        "open_report_folder_on_approve": ui.open_report_folder_on_approve,
        "theme": ui.theme,
    }
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))
