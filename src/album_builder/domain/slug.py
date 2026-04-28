"""Slug derivation for album folder names.

Names are user-supplied free-text (1-80 chars, validated by Album.create);
slugs are URL/filesystem-safe ASCII. Derivation rules:
- NFKD-normalise + strip combining marks so accented Latin chars survive
  ("Émile" -> "emile" rather than "album")
- Lowercase
- Non-[a-z0-9] runs collapse to a single '-'
- Leading / trailing '-' stripped
- Empty result (e.g. CJK-only input "東京") falls back to the literal
  string 'album'; collision resolution adds " (2)", " (3)" suffixes

Collision resolution is folder-aware and lives in `unique_slug` so both
`Album.create` and `Album.rename` share the rule.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    # NFKD splits an accented character into base + combining mark; the
    # ASCII-encode then drops the combining marks (which all live above
    # U+007F). German "ß" stays as "ss" via NFKC's compatibility step
    # being a no-op here, so we apply str.casefold() last to fold those.
    folded = unicodedata.normalize("NFKD", name).casefold()
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    s = _NON_SLUG.sub("-", ascii_only).strip("-")
    return s or "album"


def unique_slug(albums_dir: Path, base: str) -> str:
    if not (albums_dir / base).exists():
        return base
    n = 2
    while (albums_dir / f"{base} ({n})").exists():
        n += 1
    return f"{base} ({n})"
