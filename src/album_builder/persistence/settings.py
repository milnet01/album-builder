"""User settings persisted at ``$XDG_CONFIG_HOME/album-builder/settings.json``."""

from __future__ import annotations

import json
import os
from pathlib import Path


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


def read_tracks_folder() -> Path | None:
    """Return the user-configured tracks folder, or ``None`` if unset.

    Returns ``None`` for any of: file missing, unreadable JSON, missing
    ``tracks_folder`` key, empty string. Callers fall back to a default.
    """
    path = settings_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    folder = data.get("tracks_folder")
    if not isinstance(folder, str) or not folder.strip():
        return None
    return Path(folder).expanduser()
