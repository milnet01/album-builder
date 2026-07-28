"""TC-22-* — Spec 22 Portability groundwork.

Covers the three POSIX chokepoints made cross-platform: symlink-or-playlist
export + capability probe (`services/export.py`), capability-aware drift parity
(`services/album_store.py` + `is_export_fresh`), cross-platform config dir
(`persistence/settings.py`), and cross-platform folder-open (`ui/main_window.py`).

The no-symlink case is forced by monkeypatching `_supports_symlinks` (or
`Path.symlink_to`) since the CI filesystem supports symlinks; every test is
audio-free and bus-free.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from album_builder.persistence import settings
from album_builder.services import album_store, export
from album_builder.services.export import (
    PLAYLIST_FILENAME,
    _supports_symlinks,
    is_export_fresh,
    regenerate_album_exports,
)
from album_builder.ui.main_window import MainWindow

# --- helpers (duck-typed, mirrors test_TC_08_export.py) ---


def _make_track(path: Path, *, title: str = "T", is_missing: bool = False):
    return SimpleNamespace(
        path=path, title=title, artist="A", album_artist="A", composer=None,
        duration_seconds=30.0, is_missing=is_missing,
        lyrics_text=None, cover_data=None, cover_mime=None,
    )


class _FakeLibrary:
    def __init__(self, tracks: dict[Path, object]):
        self._tracks = tracks

    def find(self, path: Path):
        return self._tracks.get(Path(path))

    def refresh(self):
        pass


def _make_album(track_paths: list[Path], *, name: str = "Album One"):
    return SimpleNamespace(
        name=name,
        target_count=max(1, len(track_paths)),
        track_paths=[str(p) for p in track_paths],
    )


def _seed(tmp_path: Path, n: int) -> list[Path]:
    paths = []
    for i in range(n):
        p = tmp_path / f"src_{i:03d}.mp3"
        p.write_bytes(b"X" * 128)
        paths.append(p)
    return paths


def _album_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "album"
    folder.mkdir()
    return folder


# --- TC-22-01: symlink-capable export unchanged ---


def test_TC_22_01_symlink_capable_export_unchanged(tmp_path):
    # Spec: TC-22-01
    paths = _seed(tmp_path, 3)
    folder = _album_folder(tmp_path)
    library = _FakeLibrary({p: _make_track(p, title="track A") for p in paths})
    album = _make_album(paths)

    regenerate_album_exports(album, library, folder)

    symlinks = [p for p in folder.iterdir() if p.is_symlink()]
    assert len(symlinks) == 3
    assert (folder / PLAYLIST_FILENAME).exists()
    # a regenerated entry reads the target's bytes
    assert symlinks[0].read_bytes() == b"X" * 128


# --- TC-22-02: playlist-only export ---


def test_TC_22_02_playlist_only_export(tmp_path, monkeypatch):
    # Spec: TC-22-02
    monkeypatch.setattr(export, "_supports_symlinks", lambda d: False)
    paths = _seed(tmp_path, 3)
    folder = _album_folder(tmp_path)
    library = _FakeLibrary({p: _make_track(p) for p in paths})
    album = _make_album(paths)

    created, warnings = regenerate_album_exports(album, library, folder)

    # zero numbered entries, playlist still written listing every track
    assert created == 0
    assert not any(p.is_symlink() for p in folder.iterdir())
    body = (folder / PLAYLIST_FILENAME).read_text(encoding="utf-8")
    for p in paths:
        assert p.name in body
    # exactly one playlist-only warning, not one-per-track
    assert sum("playlist-only" in w for w in warnings) == 1


# --- TC-22-03: capability-aware drift ---


def test_TC_22_03_drift_playlist_only_reads_fresh(tmp_path, monkeypatch):
    # Spec: TC-22-03 — no symlink support, zero entries -> fresh (not stale)
    monkeypatch.setattr(export, "_supports_symlinks", lambda d: False)
    monkeypatch.setattr(album_store, "_supports_symlinks", lambda d: False)
    paths = _seed(tmp_path, 3)
    folder = _album_folder(tmp_path)
    library = _FakeLibrary({p: _make_track(p) for p in paths})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)  # playlist-only, 0 symlinks

    assert is_export_fresh(album, folder, library) is True
    assert album_store._symlink_count_matches(album, folder) is True


def test_TC_22_03_drift_linux_missing_entry_reads_stale(tmp_path, monkeypatch):
    # Spec: TC-22-03 — symlink support + a missing entry -> stale (both False)
    monkeypatch.setattr(export, "_supports_symlinks", lambda d: True)
    monkeypatch.setattr(album_store, "_supports_symlinks", lambda d: True)
    paths = _seed(tmp_path, 3)
    folder = _album_folder(tmp_path)
    library = _FakeLibrary({p: _make_track(p) for p in paths})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)
    # delete one live symlink to simulate drift
    next(p for p in folder.iterdir() if p.is_symlink()).unlink()

    assert is_export_fresh(album, folder, library) is False
    assert album_store._symlink_count_matches(album, folder) is False


# --- TC-22-04: probe ---


def test_TC_22_04_probe_true_and_cleans_up(tmp_path):
    # Spec: TC-22-04
    before = set(tmp_path.iterdir())
    assert _supports_symlinks(tmp_path) is True
    after = set(tmp_path.iterdir())
    assert before == after  # throwaway symlink removed
    assert not any(p.name.startswith(".symlink-probe-") for p in tmp_path.iterdir())


def test_TC_22_04_probe_false_on_oserror(tmp_path, monkeypatch):
    # Spec: TC-22-04
    def _boom(self, *a, **k):
        raise OSError("no symlinks here")

    monkeypatch.setattr(Path, "symlink_to", _boom)
    assert _supports_symlinks(tmp_path) is False


# --- TC-22-05: regression (symlink round-trip + drift/commit invariants) ---


def test_TC_22_05_regression_symlink_round_trip(tmp_path):
    # Spec: TC-22-05
    paths = _seed(tmp_path, 2)
    folder = _album_folder(tmp_path)
    library = _FakeLibrary({p: _make_track(p) for p in paths})
    album = _make_album(paths)

    regenerate_album_exports(album, library, folder)

    assert any(p.is_symlink() for p in folder.iterdir())
    assert is_export_fresh(album, folder, library) is True


# --- TC-22-06: settings_dir on Linux (INV-22-2) ---


def test_TC_22_06_settings_dir_absolute_xdg(tmp_path, monkeypatch):
    # Spec: TC-22-06
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert settings.settings_dir() == tmp_path / "album-builder"


def test_TC_22_06_settings_dir_unset_falls_back_home(monkeypatch):
    # Spec: TC-22-06
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert settings.settings_dir() == Path.home() / ".config" / "album-builder"


def test_TC_22_06_settings_dir_relative_falls_back_home(monkeypatch):
    # Spec: TC-22-06 — freedesktop mandate; guard precedes platformdirs
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")
    assert settings.settings_dir() == Path.home() / ".config" / "album-builder"


# --- TC-22-07: cross-platform folder-open (INV-22-4) ---


def test_TC_22_07_open_folder_passes_local_file_url(tmp_path, monkeypatch):
    # Spec: TC-22-07
    captured = []
    monkeypatch.setattr(
        "album_builder.ui.main_window.QDesktopServices.openUrl",
        lambda url: captured.append(url) or True,
    )
    MainWindow._open_in_file_manager(SimpleNamespace(), tmp_path)
    assert len(captured) == 1
    assert Path(captured[0].toLocalFile()) == tmp_path


def test_TC_22_07_open_folder_false_does_not_propagate(tmp_path, monkeypatch):
    # Spec: TC-22-07 — a False (no handler) result is logged, never raised
    monkeypatch.setattr(
        "album_builder.ui.main_window.QDesktopServices.openUrl",
        lambda url: False,
    )
    MainWindow._open_in_file_manager(SimpleNamespace(), tmp_path)  # no exception


def test_TC_22_07_open_folder_raise_does_not_propagate(tmp_path, monkeypatch):
    # Spec: TC-22-07 — a raising handler is caught, never propagates (INV-22-4)
    def _raise(url):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "album_builder.ui.main_window.QDesktopServices.openUrl", _raise
    )
    MainWindow._open_in_file_manager(SimpleNamespace(), tmp_path)  # no exception
