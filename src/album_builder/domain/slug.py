"""Slug derivation for album folder names.

Names are user-supplied free-text (1–80 chars, validated by Album.create);
slugs are URL/filesystem-safe ASCII. Derivation rules:
- Lowercase
- Non-[a-z0-9] runs collapse to a single '-'
- Leading / trailing '-' stripped
- Empty result falls back to the literal string 'album'

Collision resolution is folder-aware (suffix ' (2)', ' (3)', …) and lives
in `unique_slug` so both `Album.create` and `Album.rename` share the rule.
"""

from __future__ import annotations

import re
from pathlib import Path

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _NON_SLUG.sub("-", name.lower()).strip("-")
    return s or "album"


def unique_slug(albums_dir: Path, base: str) -> str:
    if not (albums_dir / base).exists():
        return base
    n = 2
    while (albums_dir / f"{base} ({n})").exists():
        n += 1
    return f"{base} ({n})"
