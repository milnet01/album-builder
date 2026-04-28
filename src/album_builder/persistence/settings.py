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


@dataclass(frozen=True)
class AudioSettings:
    """Spec 06 §Implementation notes: volume 0..100 default 80; muted bool."""

    volume: int = DEFAULT_VOLUME
    muted: bool = DEFAULT_MUTED


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
    data = _read_settings_dict()
    folder = data.get("tracks_folder")
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
