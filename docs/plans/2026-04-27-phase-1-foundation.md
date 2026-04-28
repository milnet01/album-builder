# Album Builder — Phase 1: Foundation Implementation Plan

> **Historical note (2026-04-28):** This is a frozen-in-time plan, retained for reference. Two field renames happened during Phase 1 hardening that are not back-ported into the steps below:
> - `cover_png` field → `cover_data` + `cover_mime` (Tier 2.D, commit `cd829d4`). Wherever you see `cover_png` in the steps below, the shipped code uses `cover_data` (bytes) + `cover_mime` (string). Spec 01 §Data shape is the source of truth.
> - The Phase-2-deferred items (`tracks_changed` signal + `QFileSystemWatcher`) carry stable IDs `TC-01-P2-01..04` and ship in Phase 2, not Phase 1.
>
> Refer to `docs/plans/2026-04-28-phase-2-albums.md` for the next-phase plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable, installable PyQt6 desktop app that opens to a themed three-pane main window, scans `Tracks/` and displays the library list with full metadata (title, artist, composer, album, duration), is launchable from the KDE app menu via a `.desktop` entry, and has a clean uninstall path. No albums functionality yet — that's Phase 2.

**Architecture:** Layered Python project (UI / domain / persistence). PyQt6 in the UI layer; domain layer is pure Python and unit-testable without a display. Atomic-write helper underpins all persistence work. Single-instance launcher ensures one window even when the user clicks the launcher twice.

**Tech Stack:** Python 3.11+, PyQt6 6.6+, mutagen 1.47+, pytest 8+, pytest-qt 4+, ruff, venv-based packaging.

**Specs covered:** 00 (App overview), 01 (Track library & metadata), 10 (Persistence atomic-write skeleton — full schema versioning is Phase 2), 11 (Theme & icon), 12 (Packaging & launcher).

---

## File structure to be created

```
src/album_builder/
├── __init__.py                        # version export
├── __main__.py                        # python -m album_builder entry
├── version.py                         # __version__ = "0.1.0"
├── app.py                             # QApplication setup, single-instance
├── domain/
│   ├── __init__.py
│   ├── track.py                       # Track dataclass + from_path
│   └── library.py                     # Library class (scan/search/sort)
├── persistence/
│   ├── __init__.py
│   └── atomic_io.py                   # atomic_write_text/bytes
└── ui/
    ├── __init__.py
    ├── theme.py                       # Palette + qt_stylesheet()
    ├── main_window.py                 # QMainWindow + 3-pane splitter
    └── library_pane.py                # search box + sortable QTableView

tests/
├── __init__.py
├── conftest.py                        # shared fixtures (tmp_tracks_dir, etc.)
├── fixtures/
│   └── silent_1s.mp3                  # tiny silent MP3, retagged per test
├── domain/
│   ├── test_track.py
│   └── test_library.py
├── persistence/
│   └── test_atomic_io.py
└── ui/
    ├── test_theme.py
    ├── test_main_window.py
    └── test_library_pane.py

packaging/
└── album-builder.desktop.in           # template, paths patched at install

assets/
└── album-builder.svg                  # vinyl icon (Tabler MIT)

requirements.txt
requirements-dev.txt
pyproject.toml
README.md
install.sh
uninstall.sh
.python-version                        # "3.11"
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.python-version`
- Create: `src/album_builder/__init__.py`
- Create: `src/album_builder/version.py`
- Create: `src/album_builder/domain/__init__.py`
- Create: `src/album_builder/persistence/__init__.py`
- Create: `src/album_builder/ui/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/domain/__init__.py`
- Create: `tests/persistence/__init__.py`
- Create: `tests/ui/__init__.py`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p src/album_builder/{domain,persistence,ui} \
         tests/{domain,persistence,ui,fixtures} \
         packaging assets
touch src/album_builder/__init__.py \
      src/album_builder/domain/__init__.py \
      src/album_builder/persistence/__init__.py \
      src/album_builder/ui/__init__.py \
      tests/__init__.py \
      tests/domain/__init__.py \
      tests/persistence/__init__.py \
      tests/ui/__init__.py
```

- [ ] **Step 2: Write `.python-version`**

File: `.python-version`
```
3.11
```

- [ ] **Step 3: Write `requirements.txt`**

File: `requirements.txt`
```
PyQt6>=6.6,<7
mutagen>=1.47,<2
```

(Phase 1 only needs PyQt6 and mutagen. Whisper, WeasyPrint etc. arrive in later phases.)

- [ ] **Step 4: Write `requirements-dev.txt`**

File: `requirements-dev.txt`
```
-r requirements.txt
pytest>=8,<9
pytest-qt>=4.4,<5
ruff>=0.5
```

- [ ] **Step 5: Write `pyproject.toml`**

File: `pyproject.toml`
```toml
[project]
name = "album-builder"
version = "0.1.0"
description = "Curate albums from a folder of audio recordings"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "RUF"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q"
qt_api = "pyqt6"
```

- [ ] **Step 6: Write `src/album_builder/version.py`**

File: `src/album_builder/version.py`
```python
__version__ = "0.1.0"
```

- [ ] **Step 7: Update `src/album_builder/__init__.py`**

File: `src/album_builder/__init__.py`
```python
from album_builder.version import __version__

__all__ = ["__version__"]
```

- [ ] **Step 8: Create venv and install deps**

```bash
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
```

Expected: pip installs PyQt6, mutagen, pytest, pytest-qt, ruff without error.

- [ ] **Step 9: Verify the import works**

Run: `.venv/bin/python -c "import album_builder; print(album_builder.__version__)"`
Expected output: `0.1.0`

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml requirements.txt requirements-dev.txt .python-version \
        src/album_builder tests packaging assets
git commit -m "feat: scaffold project structure and dependencies"
```

(`.venv/` is already gitignored.)

---

## Task 2: Atomic write utility

**Files:**
- Create: `src/album_builder/persistence/atomic_io.py`
- Create: `tests/persistence/test_atomic_io.py`

- [ ] **Step 1: Write the failing test for `atomic_write_text`**

File: `tests/persistence/test_atomic_io.py`
```python
from pathlib import Path
import os

import pytest

from album_builder.persistence.atomic_io import atomic_write_text


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    atomic_write_text(target, '{"hello": "world"}')
    assert target.read_text(encoding="utf-8") == '{"hello": "world"}'


def test_atomic_write_text_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text("old content", encoding="utf-8")
    atomic_write_text(target, "new content")
    assert target.read_text(encoding="utf-8") == "new content"


def test_atomic_write_text_no_tmp_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    atomic_write_text(target, "content")
    siblings = list(tmp_path.iterdir())
    assert siblings == [target]


def test_atomic_write_text_failure_keeps_original(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "config.json"
    target.write_text("original", encoding="utf-8")

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "original"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/persistence/test_atomic_io.py -v`
Expected: 4 errors with "ModuleNotFoundError: No module named 'album_builder.persistence.atomic_io'".

- [ ] **Step 3: Implement `atomic_write_text`**

File: `src/album_builder/persistence/atomic_io.py`
```python
"""Atomic file write helpers — write-to-tmp + rename for crash safety."""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
```

- [ ] **Step 4: Configure PYTHONPATH so tests find the source**

File: `pyproject.toml` — add to the existing `[tool.pytest.ini_options]` section:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q"
qt_api = "pyqt6"
pythonpath = ["src"]
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/pytest tests/persistence/test_atomic_io.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/persistence/atomic_io.py \
        tests/persistence/test_atomic_io.py \
        pyproject.toml
git commit -m "feat(persistence): add atomic_write_text/bytes helpers"
```

---

## Task 3: Track fixture + Track dataclass

**Files:**
- Create: `tests/fixtures/silent_1s.mp3` (a 1-second silent MP3, ~5 KB)
- Create: `tests/conftest.py`
- Create: `tests/domain/test_track.py`
- Create: `src/album_builder/domain/track.py`

- [ ] **Step 1: Generate the silent MP3 fixture**

We need a tiny real MP3 file to exercise tag parsing. Use ffmpeg (already installed on the user's openSUSE system per the CLAUDE.md context).

Run:
```bash
ffmpeg -y -f lavfi -i "anullsrc=r=22050:cl=mono" -t 1 -ac 1 -b:a 32k -codec:a libmp3lame tests/fixtures/silent_1s.mp3
```

Expected: `tests/fixtures/silent_1s.mp3` exists and is between 3 KB and 10 KB.

If ffmpeg is not available, fall back to:
```bash
.venv/bin/pip install pydub
.venv/bin/python -c "
from pydub import AudioSegment
silence = AudioSegment.silent(duration=1000, frame_rate=22050)
silence.export('tests/fixtures/silent_1s.mp3', format='mp3', bitrate='32k')
"
```

- [ ] **Step 2: Write `tests/conftest.py` with a tagged-track fixture**

File: `tests/conftest.py`
```python
"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from mutagen.id3 import APIC, COMM, ID3, TALB, TCOM, TIT2, TPE1, TPE2, USLT


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SILENT_MP3 = FIXTURES_DIR / "silent_1s.mp3"

DEFAULT_TAGS = {
    "title": "something more (calm)",
    "artist": "18 Down",
    "album_artist": "18 Down",
    "album": "Memoirs of a Sinner",
    "composer": "Charl Jordaan",
    "comment": "Copyright 2026 Charl Jordaan",
    "lyrics": "[Intro]\nwalking the line again\nfeeling the weight of every word",
}


def _write_tags(path: Path, **tags: str) -> None:
    audio = ID3(path)
    audio.delete()
    audio = ID3()
    if "title" in tags:
        audio.add(TIT2(encoding=3, text=tags["title"]))
    if "artist" in tags:
        audio.add(TPE1(encoding=3, text=tags["artist"]))
    if "album_artist" in tags:
        audio.add(TPE2(encoding=3, text=tags["album_artist"]))
    if "album" in tags:
        audio.add(TALB(encoding=3, text=tags["album"]))
    if "composer" in tags:
        audio.add(TCOM(encoding=3, text=tags["composer"]))
    if "comment" in tags:
        audio.add(COMM(encoding=3, lang="eng", desc="", text=tags["comment"]))
    if "lyrics" in tags:
        audio.add(USLT(encoding=3, lang="eng", desc="", text=tags["lyrics"]))
    if "cover_png" in tags:
        audio.add(APIC(encoding=3, mime="image/png", type=3, desc="cover",
                       data=tags["cover_png"]))
    audio.save(path, v2_version=3)


@pytest.fixture
def tagged_track(tmp_path: Path):
    """Return a callable that writes a tagged copy of silent_1s.mp3 into tmp_path."""

    def _make(name: str = "track.mp3", **overrides: str) -> Path:
        target = tmp_path / name
        shutil.copy(SILENT_MP3, target)
        tags = {**DEFAULT_TAGS, **overrides}
        _write_tags(target, **tags)
        return target

    return _make


@pytest.fixture
def tracks_dir(tmp_path: Path, tagged_track):
    """A directory with three tagged tracks."""
    tagged_track("01-intro.mp3", title="memoirs intro")
    tagged_track("02-something-more.mp3", title="something more (calm)")
    tagged_track("03-drift.mp3", title="drift", artist="Other Artist")
    return tmp_path
```

- [ ] **Step 3: Write the failing tests for `Track`**

File: `tests/domain/test_track.py`
```python
from pathlib import Path

from album_builder.domain.track import Track


def test_track_from_path_parses_tags(tagged_track) -> None:
    path = tagged_track()
    track = Track.from_path(path)
    assert track.title == "something more (calm)"
    assert track.artist == "18 Down"
    assert track.album_artist == "18 Down"
    assert track.album == "Memoirs of a Sinner"
    assert track.composer == "Charl Jordaan"
    assert track.comment == "Copyright 2026 Charl Jordaan"
    assert track.lyrics_text is not None and "walking the line" in track.lyrics_text
    assert track.duration_seconds > 0.5
    assert not track.is_missing


def test_track_from_path_with_minimal_tags(tagged_track) -> None:
    path = tagged_track(title="only title")
    # Re-tag stripping everything but title (override tagged_track defaults)
    from tests.conftest import _write_tags
    _write_tags(path, title="only title")
    track = Track.from_path(path)
    assert track.title == "only title"
    assert track.artist == "Unknown artist"
    assert track.album == ""
    assert track.composer == ""


def test_track_from_path_missing_file(tmp_path: Path) -> None:
    track = Track.from_path(tmp_path / "nonexistent.mp3", allow_missing=True)
    assert track.is_missing
    assert track.title == "nonexistent.mp3"


def test_track_album_artist_falls_back_to_artist(tagged_track) -> None:
    path = tagged_track()
    from tests.conftest import _write_tags
    _write_tags(path, title="x", artist="Solo Artist")
    track = Track.from_path(path)
    assert track.artist == "Solo Artist"
    assert track.album_artist == "Solo Artist"


def test_track_with_embedded_cover(tagged_track) -> None:
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    path = tagged_track(cover_png=fake_png)
    track = Track.from_path(path)
    assert track.cover_png is not None
    assert track.cover_png.startswith(b"\x89PNG")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/domain/test_track.py -v`
Expected: ImportError on `album_builder.domain.track`.

- [ ] **Step 5: Implement `Track`**

File: `src/album_builder/domain/track.py`
```python
"""Track domain object — read-only view of an audio file's metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import APIC, COMM, ID3, ID3NoHeaderError, USLT


@dataclass(frozen=True)
class Track:
    path: Path
    title: str
    artist: str
    album_artist: str
    composer: str
    album: str
    comment: str
    lyrics_text: str | None
    cover_png: bytes | None
    duration_seconds: float
    file_size_bytes: int
    is_missing: bool

    @classmethod
    def from_path(cls, path: Path, *, allow_missing: bool = False) -> "Track":
        path = Path(path).resolve()
        if not path.exists():
            if not allow_missing:
                raise FileNotFoundError(path)
            return cls._missing(path)

        size = path.stat().st_size
        try:
            mf = MutagenFile(path)
        except Exception:
            mf = None

        duration = float(mf.info.length) if mf and mf.info else 0.0

        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            id3 = None
        except Exception:
            id3 = None

        title = _text(id3, "TIT2") or path.name
        artist = _text(id3, "TPE1") or "Unknown artist"
        album_artist = _text(id3, "TPE2") or artist
        album = _text(id3, "TALB") or ""
        composer = _text(id3, "TCOM") or ""
        comment = _comment_text(id3)
        lyrics_text = _lyrics_text(id3)
        cover_png = _first_apic_png(id3)

        return cls(
            path=path,
            title=title,
            artist=artist,
            album_artist=album_artist,
            composer=composer,
            album=album,
            comment=comment,
            lyrics_text=lyrics_text,
            cover_png=cover_png,
            duration_seconds=duration,
            file_size_bytes=size,
            is_missing=False,
        )

    @classmethod
    def _missing(cls, path: Path) -> "Track":
        return cls(
            path=path,
            title=path.name,
            artist="Unknown artist",
            album_artist="Unknown artist",
            composer="",
            album="",
            comment="",
            lyrics_text=None,
            cover_png=None,
            duration_seconds=0.0,
            file_size_bytes=0,
            is_missing=True,
        )


def _text(id3: ID3 | None, key: str) -> str:
    if id3 is None or key not in id3:
        return ""
    frame = id3[key]
    text = " / ".join(str(t) for t in frame.text) if hasattr(frame, "text") else str(frame)
    return text.strip()


def _comment_text(id3: ID3 | None) -> str:
    if id3 is None:
        return ""
    for key in id3.keys():
        if key.startswith("COMM"):
            frame = id3[key]
            if isinstance(frame, COMM):
                return " / ".join(str(t) for t in frame.text).strip()
    return ""


def _lyrics_text(id3: ID3 | None) -> str | None:
    if id3 is None:
        return None
    for key in id3.keys():
        if key.startswith("USLT"):
            frame = id3[key]
            if isinstance(frame, USLT):
                value = " / ".join(str(t) for t in frame.text) if isinstance(frame.text, list) else str(frame.text)
                return value if value.strip() else None
    return None


def _first_apic_png(id3: ID3 | None) -> bytes | None:
    if id3 is None:
        return None
    for key in id3.keys():
        if key.startswith("APIC"):
            frame = id3[key]
            if isinstance(frame, APIC):
                return frame.data
    return None
```

- [ ] **Step 6: Run tests to verify pass**

Run: `.venv/bin/pytest tests/domain/test_track.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/album_builder/domain/track.py tests/domain/test_track.py \
        tests/conftest.py tests/fixtures/silent_1s.mp3
git commit -m "feat(domain): add Track dataclass with mutagen ID3 parsing"
```

---

## Task 4: Library class — scan, search, sort

**Files:**
- Create: `src/album_builder/domain/library.py`
- Create: `tests/domain/test_library.py`

- [ ] **Step 1: Write the failing tests**

File: `tests/domain/test_library.py`
```python
from pathlib import Path

from album_builder.domain.library import Library, SortKey


def test_library_scan_empty_dir(tmp_path: Path) -> None:
    lib = Library.scan(tmp_path)
    assert lib.tracks == []


def test_library_scan_finds_three_tracks(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    titles = sorted(t.title for t in lib.tracks)
    assert titles == ["drift", "memoirs intro", "something more (calm)"]


def test_library_search_by_title(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    results = lib.search("intro")
    assert len(results) == 1
    assert results[0].title == "memoirs intro"


def test_library_search_case_insensitive(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    assert len(lib.search("INTRO")) == 1
    assert len(lib.search("18 down")) == 2  # default artist; drift overrides


def test_library_search_empty_query_returns_all(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    assert len(lib.search("")) == 3


def test_library_sort_by_title_ascending(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    sorted_tracks = lib.sorted(SortKey.TITLE, ascending=True)
    titles = [t.title for t in sorted_tracks]
    assert titles == sorted(titles)


def test_library_sort_by_title_descending(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    sorted_tracks = lib.sorted(SortKey.TITLE, ascending=False)
    titles = [t.title for t in sorted_tracks]
    assert titles == sorted(titles, reverse=True)


def test_library_find_by_path(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    one = lib.tracks[0]
    assert lib.find(one.path) is one
    assert lib.find(tracks_dir / "nonexistent.mp3") is None


def test_library_skips_unsupported_files(tmp_path: Path, tagged_track) -> None:
    tagged_track("song.mp3")
    (tmp_path / "readme.txt").write_text("not audio")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    lib = Library.scan(tmp_path)
    assert len(lib.tracks) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/domain/test_library.py -v`
Expected: ImportError on `album_builder.domain.library`.

- [ ] **Step 3: Implement `Library`**

File: `src/album_builder/domain/library.py`
```python
"""Library — the in-memory set of tracks discovered in the source folder."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from album_builder.domain.track import Track


SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".mp3", ".mpeg", ".m4a", ".flac", ".ogg", ".opus", ".wav",
})


class SortKey(str, Enum):
    TITLE = "title"
    ARTIST = "artist"
    ALBUM = "album"
    COMPOSER = "composer"
    DURATION = "duration"


@dataclass(frozen=True)
class Library:
    folder: Path
    tracks: list[Track] = field(default_factory=list)

    @classmethod
    def scan(cls, folder: Path) -> "Library":
        folder = Path(folder).resolve()
        if not folder.exists():
            return cls(folder=folder, tracks=[])
        tracks: list[Track] = []
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    tracks.append(Track.from_path(entry))
                except Exception:
                    # malformed file: skip silently in v1
                    continue
        return cls(folder=folder, tracks=tracks)

    def find(self, path: Path) -> Track | None:
        target = Path(path).resolve()
        for t in self.tracks:
            if t.path == target:
                return t
        return None

    def search(self, query: str) -> list[Track]:
        q = query.strip().lower()
        if not q:
            return list(self.tracks)
        return [
            t for t in self.tracks
            if q in t.title.lower()
            or q in t.artist.lower()
            or q in t.album_artist.lower()
            or q in t.composer.lower()
            or q in t.album.lower()
        ]

    def sorted(self, key: SortKey, *, ascending: bool = True) -> list[Track]:
        attr = {
            SortKey.TITLE: lambda t: t.title.lower(),
            SortKey.ARTIST: lambda t: t.artist.lower(),
            SortKey.ALBUM: lambda t: t.album.lower(),
            SortKey.COMPOSER: lambda t: t.composer.lower(),
            SortKey.DURATION: lambda t: t.duration_seconds,
        }[key]
        return sorted(self.tracks, key=attr, reverse=not ascending)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/domain/test_library.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/domain/library.py tests/domain/test_library.py
git commit -m "feat(domain): add Library with scan/search/sort"
```

---

## Task 5: Theme module — palette + Qt stylesheet

**Files:**
- Create: `src/album_builder/ui/theme.py`
- Create: `tests/ui/test_theme.py`

- [ ] **Step 1: Write the failing tests**

File: `tests/ui/test_theme.py`
```python
from album_builder.ui.theme import Palette, qt_stylesheet


def test_palette_has_required_tokens() -> None:
    p = Palette.dark_colourful()
    # Spot-check tokens defined in spec 11
    assert p.bg_base == "#15161c"
    assert p.bg_pane == "#1a1b22"
    assert p.accent_primary_1 == "#6e3df0"
    assert p.accent_primary_2 == "#c635a6"
    assert p.success == "#10b981"
    assert p.danger == "#ef4444"


def test_palette_tokens_are_valid_hex() -> None:
    p = Palette.dark_colourful()
    for name, value in vars(p).items():
        assert isinstance(value, str), name
        assert value.startswith("#") and len(value) == 7, f"{name}={value}"


def test_qt_stylesheet_returns_non_empty_string() -> None:
    qss = qt_stylesheet(Palette.dark_colourful())
    assert isinstance(qss, str)
    assert len(qss) > 100
    # The window background must be set
    assert "#15161c" in qss
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_theme.py -v`
Expected: ImportError on `album_builder.ui.theme`.

- [ ] **Step 3: Implement the theme module**

File: `src/album_builder/ui/theme.py`
```python
"""Dark + colourful theme — palette and Qt stylesheet."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg_base: str
    bg_pane: str
    bg_elevated: str
    border: str
    border_strong: str
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_disabled: str
    accent_primary_1: str
    accent_primary_2: str
    accent_warm: str
    success: str
    success_dark: str
    warning: str
    danger: str

    @classmethod
    def dark_colourful(cls) -> "Palette":
        return cls(
            bg_base="#15161c",
            bg_pane="#1a1b22",
            bg_elevated="#1f2029",
            border="#262830",
            border_strong="#383a47",
            text_primary="#e8e9ee",
            text_secondary="#8a8d9a",
            text_tertiary="#6e717c",
            text_disabled="#4a4d5a",
            accent_primary_1="#6e3df0",
            accent_primary_2="#c635a6",
            accent_warm="#f6c343",
            success="#10b981",
            success_dark="#059669",
            warning="#f97316",
            danger="#ef4444",
        )


def qt_stylesheet(p: Palette) -> str:
    return f"""
    QMainWindow, QWidget {{
        background-color: {p.bg_base};
        color: {p.text_primary};
        font-family: "Inter", "Cantarell", "Segoe UI", system-ui, sans-serif;
        font-size: 11pt;
    }}
    QFrame#Pane {{
        background-color: {p.bg_pane};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    QFrame#TopBar {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    QLabel#PaneTitle {{
        color: {p.accent_warm};
        font-size: 9pt;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding-bottom: 6px;
        border-bottom: 1px solid {p.border};
    }}
    QLineEdit {{
        background-color: {p.bg_base};
        border: 1px solid {p.border_strong};
        border-radius: 5px;
        padding: 4px 8px;
        color: {p.text_primary};
        selection-background-color: {p.accent_primary_1};
    }}
    QLineEdit:focus {{
        border-color: {p.accent_primary_1};
    }}
    QHeaderView::section {{
        background-color: {p.bg_elevated};
        color: {p.text_secondary};
        padding: 6px 8px;
        border: none;
        border-right: 1px solid {p.border};
    }}
    QTableView {{
        background-color: {p.bg_pane};
        alternate-background-color: {p.bg_elevated};
        gridline-color: {p.border};
        selection-background-color: {p.accent_primary_1};
        selection-color: {p.text_primary};
    }}
    QTableView::item {{
        padding: 6px;
        border: none;
    }}
    QSplitter::handle {{
        background-color: {p.border};
    }}
    QSplitter::handle:horizontal {{
        width: 2px;
    }}
    QPushButton {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border_strong};
        border-radius: 6px;
        padding: 5px 12px;
        color: {p.text_primary};
    }}
    QPushButton:hover {{
        background-color: {p.bg_pane};
    }}
    QPushButton:disabled {{
        color: {p.text_disabled};
        border-color: {p.border};
    }}
    """.strip()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/ui/test_theme.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/theme.py tests/ui/test_theme.py
git commit -m "feat(ui): add dark+colourful Palette and Qt stylesheet"
```

---

## Task 6: Library pane widget

**Files:**
- Create: `src/album_builder/ui/library_pane.py`
- Create: `tests/ui/test_library_pane.py`

- [ ] **Step 1: Write the failing test**

File: `tests/ui/test_library_pane.py`
```python
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.library import Library
from album_builder.ui.library_pane import LibraryPane


@pytest.fixture
def populated_pane(qtbot, tracks_dir: Path):
    lib = Library.scan(tracks_dir)
    pane = LibraryPane()
    pane.set_library(lib)
    qtbot.addWidget(pane)
    return pane, lib


def test_library_pane_shows_all_tracks(populated_pane) -> None:
    pane, lib = populated_pane
    assert pane.row_count() == len(lib.tracks)


def test_library_pane_search_filters(populated_pane, qtbot) -> None:
    pane, _lib = populated_pane
    pane.search_box.setText("intro")
    qtbot.wait(50)
    assert pane.row_count() == 1


def test_library_pane_search_clear_restores_all(populated_pane, qtbot) -> None:
    pane, lib = populated_pane
    pane.search_box.setText("nope-nothing-matches")
    qtbot.wait(50)
    assert pane.row_count() == 0
    pane.search_box.setText("")
    qtbot.wait(50)
    assert pane.row_count() == len(lib.tracks)


def test_library_pane_sort_by_title(populated_pane) -> None:
    pane, lib = populated_pane
    pane.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    titles = [pane.title_at(i) for i in range(pane.row_count())]
    assert titles == sorted(titles, key=str.lower)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_library_pane.py -v`
Expected: ImportError on `album_builder.ui.library_pane`.

- [ ] **Step 3: Implement `LibraryPane`**

File: `src/album_builder/ui/library_pane.py`
```python
"""Library pane — search box + sortable table of tracks."""

from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtWidgets import QFrame, QHeaderView, QLabel, QLineEdit, QTableView, QVBoxLayout

from album_builder.domain.library import Library
from album_builder.domain.track import Track


COLUMNS: list[tuple[str, str]] = [
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Composer", "composer"),
    ("Duration", "duration_seconds"),
]


class TrackTableModel(QAbstractTableModel):
    def __init__(self, tracks: list[Track]):
        super().__init__()
        self._tracks: list[Track] = list(tracks)

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        self.endResetModel()

    def track_at(self, row: int) -> Track:
        return self._tracks[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        track = self._tracks[index.row()]
        attr = COLUMNS[index.column()][1]
        value = getattr(track, attr)
        if role == Qt.ItemDataRole.DisplayRole:
            if attr == "duration_seconds":
                return _format_duration(float(value))
            return str(value)
        if role == Qt.ItemDataRole.UserRole:
            return value  # raw value for sort comparison
        return None


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class LibraryPane(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Library", objectName="PaneTitle")
        layout.addWidget(title)

        self.search_box = QLineEdit(placeholderText="🔍  search title / artist / album / composer")
        self.search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_box)

        self._model = TrackTableModel([])
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # all columns
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def set_library(self, library: Library) -> None:
        self._model.set_tracks(library.tracks)

    def row_count(self) -> int:
        return self._proxy.rowCount()

    def title_at(self, view_row: int) -> str:
        idx = self._proxy.index(view_row, 0)
        return self._proxy.data(idx, Qt.ItemDataRole.DisplayRole)

    def _on_search_changed(self, text: str) -> None:
        self._proxy.setFilterFixedString(text.strip())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/ui/test_library_pane.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_library_pane.py
git commit -m "feat(ui): add LibraryPane with search and sortable columns"
```

---

## Task 7: Main window — three-pane skeleton

**Files:**
- Create: `src/album_builder/ui/main_window.py`
- Create: `tests/ui/test_main_window.py`

- [ ] **Step 1: Write the failing test**

File: `tests/ui/test_main_window.py`
```python
from pathlib import Path

import pytest

from album_builder.domain.library import Library
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot, tracks_dir: Path):
    lib = Library.scan(tracks_dir)
    win = MainWindow(library=lib)
    qtbot.addWidget(win)
    return win


def test_main_window_has_three_panes(main_window) -> None:
    assert main_window.splitter.count() == 3


def test_main_window_library_pane_populated(main_window) -> None:
    assert main_window.library_pane.row_count() == 3


def test_main_window_top_bar_present(main_window) -> None:
    assert main_window.top_bar is not None
    assert main_window.top_bar.objectName() == "TopBar"


def test_main_window_title_includes_app_name(main_window) -> None:
    assert "Album Builder" in main_window.windowTitle()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_main_window.py -v`
Expected: ImportError on `album_builder.ui.main_window`.

- [ ] **Step 3: Implement `MainWindow`**

File: `src/album_builder/ui/main_window.py`
```python
"""Main window — top bar + three-pane horizontal splitter."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from album_builder.domain.library import Library
from album_builder.ui.library_pane import LibraryPane
from album_builder.ui.theme import Palette, qt_stylesheet
from album_builder.version import __version__


class MainWindow(QMainWindow):
    def __init__(self, library: Library):
        super().__init__()
        self.setWindowTitle(f"Album Builder {__version__}")
        self.resize(1400, 900)
        self.setStyleSheet(qt_stylesheet(Palette.dark_colourful()))

        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.top_bar = self._build_top_bar()
        outer.addWidget(self.top_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.library_pane = LibraryPane()
        self.library_pane.set_library(library)
        self.splitter.addWidget(self.library_pane)

        # Phase 1 stubs — Phase 2 fills these in
        self.album_order_pane = self._build_placeholder_pane("Album order")
        self.now_playing_pane = self._build_placeholder_pane("Now playing")
        self.splitter.addWidget(self.album_order_pane)
        self.splitter.addWidget(self.now_playing_pane)

        self.splitter.setSizes([500, 350, 550])
        outer.addWidget(self.splitter, stretch=1)

    def _build_top_bar(self) -> QFrame:
        bar = QFrame(objectName="TopBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Phase 1: placeholder dropdown stub. Phase 2 wires the real switcher.
        album_btn = QPushButton("▾ No albums (Phase 2)")
        album_btn.setEnabled(False)
        layout.addWidget(album_btn)

        layout.addStretch(1)

        approve_btn = QPushButton("✓ Approve…")
        approve_btn.setEnabled(False)
        layout.addWidget(approve_btn)

        return bar

    def _build_placeholder_pane(self, title: str) -> QFrame:
        pane = QFrame(objectName="Pane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(10, 10, 10, 10)
        title_label = QLabel(title, objectName="PaneTitle")
        layout.addWidget(title_label)
        layout.addStretch(1)
        empty = QLabel("(coming in Phase 2)")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("color: #6e717c;")
        layout.addWidget(empty)
        layout.addStretch(2)
        return pane
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/ui/test_main_window.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat(ui): add MainWindow with top bar and three-pane splitter"
```

---

## Task 8: Application entry + single-instance lock

**Files:**
- Create: `src/album_builder/app.py`
- Create: `src/album_builder/__main__.py`

- [ ] **Step 1: Write the application module**

File: `src/album_builder/app.py`
```python
"""QApplication setup and single-instance enforcement."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSharedMemory
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from album_builder.domain.library import Library
from album_builder.ui.main_window import MainWindow

DEFAULT_TRACKS_DIR = Path("/mnt/Storage/Scripts/Linux/Music_Production/Tracks")
SHARED_KEY = "album-builder-single-instance-v1"


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Album Builder")
    app.setApplicationVersion("0.1.0")
    app.setDesktopFileName("album-builder")

    icon_path = Path.home() / ".local/share/icons/hicolor/scalable/apps/album-builder.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    lock = QSharedMemory(SHARED_KEY)
    if not lock.create(1):
        QMessageBox.information(
            None, "Album Builder",
            "Album Builder is already running. Switch to its window via the taskbar.",
        )
        return 0

    tracks_dir = _resolve_tracks_dir()
    library = Library.scan(tracks_dir)
    window = MainWindow(library=library)
    window.show()

    return app.exec()


def _resolve_tracks_dir() -> Path:
    if DEFAULT_TRACKS_DIR.exists():
        return DEFAULT_TRACKS_DIR
    cwd_tracks = Path.cwd() / "Tracks"
    if cwd_tracks.exists():
        return cwd_tracks
    return DEFAULT_TRACKS_DIR
```

- [ ] **Step 2: Write the entry-point module**

File: `src/album_builder/__main__.py`
```python
"""python -m album_builder entry point."""

from __future__ import annotations

import sys

from album_builder.app import run


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 3: Smoke test — run the app**

Run (in a graphical session, not over plain SSH):
```bash
.venv/bin/python -m album_builder
```

Expected: a window opens within 1–2 seconds. The library pane is populated with the WhatsApp Audio tracks from `Tracks/`. Top bar shows the disabled "▾ No albums (Phase 2)" pill and disabled "✓ Approve…" button. Album-order and now-playing panes show "(coming in Phase 2)". Close the window — the process exits cleanly.

- [ ] **Step 4: Smoke test — single-instance**

Open the app, then in another terminal:
```bash
.venv/bin/python -m album_builder
```

Expected: a `QMessageBox` appears saying "Album Builder is already running"; the second invocation exits with code 0; the original window is unaffected.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/app.py src/album_builder/__main__.py
git commit -m "feat(app): add entry point with single-instance lock"
```

---

## Task 9: Icon asset + .desktop template

**Files:**
- Create: `assets/album-builder.svg` (Tabler "vinyl" icon, MIT)
- Create: `packaging/album-builder.desktop.in`

- [ ] **Step 1: Source the icon SVG**

Run:
```bash
curl -fsSL "https://raw.githubusercontent.com/tabler/tabler-icons/v3.5.0/icons/outline/vinyl.svg" -o assets/album-builder.svg
```

Expected: `assets/album-builder.svg` exists, ~1 KB, valid SVG. Verify:
```bash
head -2 assets/album-builder.svg
```
Expected first line: `<svg xmlns="http://www.w3.org/2000/svg" ...`

- [ ] **Step 2: Recolor the icon to use the theme accent gradient**

Open `assets/album-builder.svg` and replace the default `stroke="currentColor"` with a gradient. The Tabler outline icon has multiple paths; we add a `<defs>` with a linear gradient and reference it.

Edit `assets/album-builder.svg`. Replace its content with:
```xml
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#6e3df0"/>
      <stop offset="100%" stop-color="#c635a6"/>
    </linearGradient>
  </defs>
  <g stroke="url(#g)">
    <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/>
    <path d="M12 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/>
    <path d="M12 7a5 5 0 0 1 5 5"/>
    <path d="M12 17a5 5 0 0 1 -5 -5"/>
  </g>
</svg>
```

(This is a 24×24 vinyl-disc outline using the theme's primary gradient. License: derived from Tabler Icons MIT.)

- [ ] **Step 3: Verify the SVG renders**

Run:
```bash
.venv/bin/python -c "
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
icon = QIcon('assets/album-builder.svg')
pix = icon.pixmap(256, 256)
assert not pix.isNull(), 'SVG failed to render'
pix.save('/tmp/icon-test.png')
print('OK — saved /tmp/icon-test.png')
"
```

Expected output: `OK — saved /tmp/icon-test.png`. Open the PNG to eyeball it (use any image viewer).

- [ ] **Step 4: Write the .desktop template**

File: `packaging/album-builder.desktop.in`
```ini
[Desktop Entry]
Type=Application
Version=1.0
Name=Album Builder
GenericName=Music Album Curator
Comment=Curate albums from a folder of recordings
Exec=@@LAUNCHER@@ %F
Icon=album-builder
Terminal=false
Categories=AudioVideo;Audio;Music;Qt;
StartupWMClass=album-builder
StartupNotify=true
SingleMainWindow=true
Keywords=album;music;curate;tracks;
```

- [ ] **Step 5: Validate the .desktop file**

Run (after install — but we can sanity-check syntax now by substituting a dummy path):
```bash
sed 's|@@LAUNCHER@@|/usr/bin/true|g' packaging/album-builder.desktop.in > /tmp/test.desktop
desktop-file-validate /tmp/test.desktop && echo OK
```

Expected: `OK`. (Install `desktop-file-utils` if not present: `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A -p "Claude Code: install desktop-file-utils" zypper install desktop-file-utils`.)

- [ ] **Step 6: Commit**

```bash
git add assets/album-builder.svg packaging/album-builder.desktop.in
git commit -m "feat(packaging): add vinyl icon SVG and .desktop template"
```

---

## Task 10: Installer + uninstaller scripts

**Files:**
- Create: `install.sh`
- Create: `uninstall.sh`
- Create: `README.md`

- [ ] **Step 1: Write `install.sh`**

File: `install.sh`
```bash
#!/usr/bin/env bash
# Album Builder installer — per-user, no sudo.
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
    echo "Run as your user, not root. Album Builder is per-user." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_PREFIX="${HOME}/.local"
APP_DIR="${INSTALL_PREFIX}/share/album-builder"
VENV_DIR="${APP_DIR}/.venv"
DESKTOP_DIR="${INSTALL_PREFIX}/share/applications"
ICON_DIR_PNG="${INSTALL_PREFIX}/share/icons/hicolor/256x256/apps"
ICON_DIR_SVG="${INSTALL_PREFIX}/share/icons/hicolor/scalable/apps"
BIN_DIR="${INSTALL_PREFIX}/bin"

# 1. Python version check
PY=$(command -v python3.11 || command -v python3 || true)
if [[ -z "$PY" ]]; then
    echo "Python 3.11+ not found. On openSUSE: zypper install python311" >&2
    exit 1
fi
PY_VER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if ! python3 -c "v='$PY_VER'.split('.'); exit(0 if int(v[0])>3 or (int(v[0])==3 and int(v[1])>=11) else 1)"; then
    echo "Python 3.11 or newer required (found $PY_VER)." >&2
    exit 1
fi

# 2. Refuse to run while the app is open (single-instance lock)
if pgrep -f "python.* -m album_builder" >/dev/null; then
    echo "Quit Album Builder first; it is currently running." >&2
    exit 1
fi

mkdir -p "$APP_DIR" "$DESKTOP_DIR" "$ICON_DIR_PNG" "$ICON_DIR_SVG" "$BIN_DIR"

# 3. venv
if [[ ! -d "$VENV_DIR" ]] || ! diff -q "$REPO_DIR/requirements.txt" "$APP_DIR/.requirements.txt.cached" >/dev/null 2>&1; then
    echo "Setting up venv…"
    rm -rf "$VENV_DIR"
    "$PY" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
    "$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"
    cp "$REPO_DIR/requirements.txt" "$APP_DIR/.requirements.txt.cached"
fi

# 4. Source files
echo "Copying source…"
rsync -a --delete "$REPO_DIR/src/" "$APP_DIR/src/"

# 5. Icon
echo "Installing icon…"
install -m 0644 "$REPO_DIR/assets/album-builder.svg" "$ICON_DIR_SVG/album-builder.svg"
if command -v inkscape >/dev/null; then
    inkscape "$ICON_DIR_SVG/album-builder.svg" \
        --export-type=png --export-width=256 \
        --export-filename="$ICON_DIR_PNG/album-builder.png" >/dev/null 2>&1
elif command -v rsvg-convert >/dev/null; then
    rsvg-convert -w 256 -h 256 "$ICON_DIR_SVG/album-builder.svg" -o "$ICON_DIR_PNG/album-builder.png"
else
    "$VENV_DIR/bin/pip" install --quiet cairosvg
    "$VENV_DIR/bin/python" -c "
import cairosvg
cairosvg.svg2png(url='$ICON_DIR_SVG/album-builder.svg',
                 write_to='$ICON_DIR_PNG/album-builder.png',
                 output_width=256, output_height=256)
"
fi

# 6. Launcher script
cat > "$BIN_DIR/album-builder" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$APP_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$VENV_DIR/bin/python" -m album_builder "\$@"
EOF
chmod +x "$BIN_DIR/album-builder"

# 7. .desktop file
sed "s|@@LAUNCHER@@|$BIN_DIR/album-builder|g" \
    "$REPO_DIR/packaging/album-builder.desktop.in" \
    > "$DESKTOP_DIR/album-builder.desktop"
chmod 0644 "$DESKTOP_DIR/album-builder.desktop"

# 8. Refresh caches
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -t "$INSTALL_PREFIX/share/icons/hicolor" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 2>/dev/null || true

echo
echo "Installed."
echo "Launch from the K Menu (Multimedia → Album Builder) or run 'album-builder' from a terminal."

if ! echo "$PATH" | tr ':' '\n' | grep -q "^$BIN_DIR\$"; then
    echo
    echo "NOTE: $BIN_DIR is not on PATH. Add this to ~/.bashrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
```

- [ ] **Step 2: Write `uninstall.sh`**

File: `uninstall.sh`
```bash
#!/usr/bin/env bash
# Album Builder uninstaller. Removes installed files; preserves user data.
set -euo pipefail

PURGE=0
if [[ "${1:-}" == "--purge" ]]; then
    PURGE=1
fi

INSTALL_PREFIX="${HOME}/.local"
APP_DIR="${INSTALL_PREFIX}/share/album-builder"
DESKTOP_FILE="${INSTALL_PREFIX}/share/applications/album-builder.desktop"
ICON_PNG="${INSTALL_PREFIX}/share/icons/hicolor/256x256/apps/album-builder.png"
ICON_SVG="${INSTALL_PREFIX}/share/icons/hicolor/scalable/apps/album-builder.svg"
BIN="${INSTALL_PREFIX}/bin/album-builder"

if pgrep -f "python.* -m album_builder" >/dev/null; then
    echo "Quit Album Builder first." >&2
    exit 1
fi

rm -rf "$APP_DIR"
rm -f "$DESKTOP_FILE" "$ICON_PNG" "$ICON_SVG" "$BIN"

if [[ $PURGE -eq 1 ]]; then
    rm -rf "${HOME}/.config/album-builder" "${HOME}/.cache/album-builder"
    echo "Removed user settings and cache (--purge)."
fi

update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
gtk-update-icon-cache -t "$INSTALL_PREFIX/share/icons/hicolor" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 2>/dev/null || true

echo "Uninstalled."
[[ $PURGE -eq 0 ]] && echo "User settings preserved at ~/.config/album-builder (use --purge to remove)."
```

- [ ] **Step 3: Make the scripts executable**

Run:
```bash
chmod +x install.sh uninstall.sh
```

- [ ] **Step 4: Lint the scripts**

Run:
```bash
shellcheck install.sh uninstall.sh
```

Expected: no warnings. (If `shellcheck` is missing: `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A -p "Claude Code: install shellcheck" zypper install ShellCheck`.)

- [ ] **Step 5: Write `README.md`**

File: `README.md`
````markdown
# Album Builder

A small PyQt6 desktop app for curating albums from a folder of audio recordings, designed for Linux/KDE.

## Status

Phase 1 — Foundation. The app opens, scans `Tracks/`, and shows the library list. Album CRUD, playback, and report generation arrive in subsequent phases (see `docs/plans/`).

## Install (openSUSE Tumbleweed + KDE Plasma)

```bash
./install.sh
```

Then launch from the K Menu under Multimedia → Album Builder, or run `album-builder` from a terminal.

### System dependencies

The installer assumes these are present:

- Python 3.11+ (`zypper install python311`)
- GStreamer audio plugins (`zypper install gstreamer-plugins-good gstreamer-plugins-bad gstreamer-plugins-libav`)
- desktop-file-utils (for validation; optional)
- Inkscape OR rsvg-convert OR cairosvg (for icon PNG generation; the installer falls back to cairosvg via pip if the others are missing)

## Uninstall

```bash
./uninstall.sh           # removes app, preserves user settings
./uninstall.sh --purge   # also removes ~/.config/album-builder and ~/.cache/album-builder
```

## Develop

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/python -m album_builder      # run from source
```

## Layout

- `src/album_builder/` — application source
- `tests/` — pytest suite (domain + UI)
- `docs/specs/` — per-feature specifications
- `docs/plans/` — phased implementation plans
- `packaging/` — `.desktop` template
- `assets/` — icon
- `install.sh` / `uninstall.sh` — per-user installer
````

- [ ] **Step 6: Commit**

```bash
git add install.sh uninstall.sh README.md
git commit -m "feat(packaging): add install/uninstall scripts and README"
```

---

## Task 11: End-to-end install + smoke test

This task is **manual** — no test code. Verifies the full install path works on the user's actual system.

- [ ] **Step 1: Run the installer**

Run:
```bash
./install.sh
```

Expected: terminal output progressing through the eight steps; final line `Installed.` with no error.

- [ ] **Step 2: Verify installed files exist**

Run:
```bash
ls -la "$HOME/.local/bin/album-builder" \
       "$HOME/.local/share/album-builder/.venv" \
       "$HOME/.local/share/applications/album-builder.desktop" \
       "$HOME/.local/share/icons/hicolor/scalable/apps/album-builder.svg" \
       "$HOME/.local/share/icons/hicolor/256x256/apps/album-builder.png"
```

Expected: all five paths exist.

- [ ] **Step 3: Validate the installed .desktop file**

Run:
```bash
desktop-file-validate "$HOME/.local/share/applications/album-builder.desktop"
```

Expected: no output (valid).

- [ ] **Step 4: Launch from terminal**

Run:
```bash
album-builder
```

Expected: window opens within 2 s; library pane lists all the WhatsApp Audio tracks; close the window cleanly.

- [ ] **Step 5: Launch from K Menu**

Open KDE's K Menu → Multimedia → Album Builder. Click. Expected: same window opens. Close it.

- [ ] **Step 6: Pin to taskbar**

Right-click the running app's taskbar icon → "Pin to Task Manager". Confirm the icon (vinyl disc with magenta/purple gradient) is recognisable. Close the app, click the pinned icon — app reopens.

- [ ] **Step 7: Single-instance check**

With the app open, run `album-builder` from another terminal. Expected: a "Already running" dialog; second invocation exits 0.

- [ ] **Step 8: Run the full test suite**

Run:
```bash
.venv/bin/pytest -v
```

Expected: all tests pass. Approximate test count: ~30 (4 atomic_io + 5 track + 9 library + 3 theme + 4 library_pane + 4 main_window).

- [ ] **Step 9: Run the linter**

Run:
```bash
.venv/bin/ruff check src tests
```

Expected: `All checks passed!`. If lint warnings appear, fix them and re-run before committing.

- [ ] **Step 10: Tag the milestone**

```bash
git tag -a v0.1.0-phase1 -m "Phase 1 complete — foundation"
```

(Don't push — local commits per the CLAUDE.md rule. The user gates pushes.)

---

## Self-review

I checked the plan against Spec 00 (overview), 01 (library), 10 (atomic write skeleton), 11 (theme), 12 (packaging):

- ✓ **00 — Project layout** — Task 1 creates the prescribed `src/album_builder/{domain,persistence,ui}` structure.
- ✓ **00 — Pure-Python domain layer** — Tasks 3, 4 import nothing from PyQt; tests run without a Qt application.
- ✓ **01 — Track from path** — Task 3 implements `Track.from_path` with all eight fields plus cover bytes.
- ✓ **01 — Library scan/search/sort** — Task 4 implements all three; tests cover empty dir, three tracks, search, sort, find, unsupported-file skip.
- ✓ **01 — Supported extensions** — `SUPPORTED_EXTENSIONS` matches the spec list verbatim.
- ✓ **01 — Missing tracks marked** — covered by `Track._missing` and `is_missing`. Live-watcher behaviour deferred to Phase 2 (out of Phase 1 scope, called out in plan goal).
- ✓ **10 — Atomic write protocol** — Task 2 implements `atomic_write_text` exactly per spec (write→fsync→replace, tmp cleanup on failure).
- ✓ **10 — Schema versioning** — deferred to Phase 2 (no album JSONs written in Phase 1; only `state.json` would be in scope and that's also Phase 2). Documented as "Phase 2" in the goal.
- ✓ **11 — Palette tokens** — Task 5 verifies six tokens against spec hex values; the implementation defines all 16.
- ✓ **11 — Qt stylesheet** — implemented for QFrame#Pane, #TopBar, QLabel#PaneTitle, QLineEdit, QHeaderView, QTableView, QSplitter, QPushButton — covers the widgets used in Phase 1.
- ✓ **11 — Icon SVG with transparent background + theme gradient** — Task 9 sources Tabler vinyl, recolours to the theme gradient.
- ✓ **12 — venv install layout** — Task 10 install.sh matches the spec's `~/.local/share/album-builder/.venv/` exactly.
- ✓ **12 — .desktop file fields** — Task 9 template matches Spec 12 byte-for-byte (Type, Categories, StartupWMClass, etc.).
- ✓ **12 — Single-instance** — Task 8 implements via `QSharedMemory` per spec.
- ✓ **12 — Uninstaller preserves user data; --purge removes it** — Task 10 uninstall.sh follows spec exactly.

**Placeholder scan:** none of "TBD", "TODO", "fill in", or "appropriate error handling" — every step has concrete code or commands.

**Type consistency:** `Track` defined in Task 3 (`title`, `artist`, `album_artist`, `composer`, `album`, `comment`, `lyrics_text`, `cover_png`, `duration_seconds`, `path`, `is_missing`, `file_size_bytes`) is used identically in Task 4 (`Library`), Task 6 (`LibraryPane.COLUMNS` references `title`, `artist`, `album`, `composer`, `duration_seconds`), and Task 7 (`MainWindow`). `SortKey` enum members in Task 4 match the column attributes in Task 6. `Palette` field names in Task 5 are referenced by `qt_stylesheet` exactly. No drift.

**Out-of-Phase-1 spec content** (acknowledged, deferred):
- Spec 01 file-watcher — Phase 2 (we don't need live updates while there's no album editing).
- Spec 10 schema migration / `.bak` files — Phase 2 (no JSON files persisted yet).
- Spec 11 light theme / accessibility — roadmap (out of v1).
- Spec 12 manual smoke tests for KDE menu integration — Task 11 covers them.

Plan is internally consistent and covers every Phase-1 requirement from the specs.
