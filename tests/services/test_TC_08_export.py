"""TC-08-* — Spec 08 Album Export pipeline tests.

Pure-Python tests against the export pipeline. The fixtures use a
duck-typed `_FakeTrack` and `_FakeLibrary` so we can exercise edge cases
(missing tracks, mutagen-empty titles, mixed artists) without depending
on a real audio file for every case.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from album_builder.services.export import (
    PLAYLIST_FILENAME,
    STAGING_DIRNAME,
    _render_m3u,
    cleanup_stale_staging,
    is_export_fresh,
    regenerate_album_exports,
    sanitise_title,
)

# --- helpers ---


def _make_track(path: Path, *, title: str | None = "T", artist: str | None = "A",
                duration_seconds: float | None = 30.0, is_missing: bool = False):
    return SimpleNamespace(
        path=path, title=title, artist=artist, album_artist=artist,
        composer=None, duration_seconds=duration_seconds, is_missing=is_missing,
        lyrics_text=None, cover_data=None, cover_mime=None,
    )


class _FakeLibrary:
    def __init__(self, tracks: dict[Path, object]):
        self._tracks = tracks
        self.refresh_calls = 0

    def find(self, path: Path):
        return self._tracks.get(Path(path))

    def refresh(self):
        self.refresh_calls += 1


def _make_album(track_paths: list[Path], *, name: str = "Album One",
                target_count: int | None = None):
    tc = target_count if target_count is not None else max(1, len(track_paths))
    return SimpleNamespace(
        name=name,
        target_count=tc,
        track_paths=[str(p) for p in track_paths],
    )


def _seed_real_files(tmp_path: Path, n: int) -> list[Path]:
    """Produce N small files inside `tmp_path` so symlink-target sanity reads
    can return non-zero bytes without depending on a real audio fixture."""
    paths: list[Path] = []
    for i in range(n):
        p = tmp_path / f"src_{i:03d}.mpeg"
        p.write_bytes(b"X" * 128)
        paths.append(p)
    return paths


# --- TC-08-01 sanitise_title ---


def test_TC_08_01_sanitise_title_replaces_forbidden():
    # Spec: TC-08-01
    assert sanitise_title("foo/bar:baz") == "foo_bar_baz"
    assert sanitise_title('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_TC_08_01_sanitise_title_trim_dots_until_stable():
    # Spec: TC-08-01 — repeat trim until stable
    assert sanitise_title(". foo .") == "foo"
    assert sanitise_title(" .foo. ") == "foo"


def test_TC_08_01_sanitise_title_strips_control_chars():
    # Spec: TC-08-01 — control char stripping
    assert sanitise_title("foo\nbar\tbaz") == "foobarbaz"


def test_TC_08_01_sanitise_title_codepoint_truncation():
    # Spec: TC-08-01 — 100 codepoint cap
    long_name = "x" * 200
    assert len(sanitise_title(long_name)) == 100


def test_TC_08_01_sanitise_title_byte_safety():
    # Spec: TC-08-01 — UTF-8 byte length under 240
    # Each "🎵" is 4 bytes in UTF-8; 100 codepoints = 400 bytes, must trim further.
    long_emoji = "🎵" * 100
    out = sanitise_title(long_emoji)
    assert len(out.encode("utf-8")) <= 240


# --- TC-08-02 / TC-08-02a M3U render ---


def test_TC_08_02_render_m3u_basic(tmp_path):
    # Spec: TC-08-02 — basic M3U body
    paths = _seed_real_files(tmp_path, 2)
    library = _FakeLibrary({
        p: _make_track(p, title=f"Track {i}", artist="A", duration_seconds=120 + i)
        for i, p in enumerate(paths)
    })
    album = _make_album(paths, name="My Album")
    body = _render_m3u(album, library)
    assert body.startswith("#EXTM3U\n")
    assert "#PLAYLIST:My Album" in body
    assert "#EXTART:A" in body  # all share
    assert "#EXTINF:120,A - Track 0" in body
    assert str(paths[0]) in body
    assert body.endswith("\n")


def test_TC_08_02_render_m3u_empty_album():
    # Spec: TC-08-02 — empty album → single-line `#EXTM3U\n`
    library = _FakeLibrary({})
    album = _make_album([], name="Empty")
    body = _render_m3u(album, library)
    assert body == "#EXTM3U\n"


def test_TC_08_02_render_m3u_unknown_artist_fallback(tmp_path):
    # Spec: TC-08-02 — artist None → "Unknown Artist"
    paths = _seed_real_files(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0], artist=None, duration_seconds=None)})
    album = _make_album(paths)
    body = _render_m3u(album, library)
    assert "#EXTINF:0,Unknown Artist - T" in body


def test_TC_08_02a_extart_emit_predicate(tmp_path):
    # Spec: TC-08-02a — #EXTART only when all tracks share artist
    paths = _seed_real_files(tmp_path, 2)
    library = _FakeLibrary({
        paths[0]: _make_track(paths[0], artist="A"),
        paths[1]: _make_track(paths[1], artist="B"),
    })
    album = _make_album(paths)
    body = _render_m3u(album, library)
    assert "#EXTART:" not in body  # mixed artists


def test_TC_08_02a_extart_empty_artist_excludes_emit(tmp_path):
    # Spec: TC-08-02a — empty artist disqualifies the shared-artist case
    paths = _seed_real_files(tmp_path, 2)
    library = _FakeLibrary({
        paths[0]: _make_track(paths[0], artist="A"),
        paths[1]: _make_track(paths[1], artist=None),
    })
    album = _make_album(paths)
    body = _render_m3u(album, library)
    assert "#EXTART:" not in body


# --- TC-08-03 symlink filename + width ---


def test_TC_08_03_symlink_names_2_digit(tmp_path):
    # Spec: TC-08-03 — 2-digit prefix, dedup before ext
    paths = _seed_real_files(tmp_path, 3)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({p: _make_track(p, title="track A") for p in paths})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)
    names = sorted(p.name for p in folder.iterdir() if p.is_symlink())
    assert names == [
        "01 - track A.mp3",
        "02 - track A (2).mp3",
        "03 - track A (3).mp3",
    ]


def test_TC_08_03_symlink_extension_rule(tmp_path):
    # Spec: TC-08-03 — .mpeg → .mp3; .flac passes through.
    src1 = tmp_path / "a.mpeg"
    src1.write_bytes(b"X" * 128)
    src2 = tmp_path / "b.flac"
    src2.write_bytes(b"X" * 128)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({
        src1: _make_track(src1, title="alpha"),
        src2: _make_track(src2, title="bravo"),
    })
    album = _make_album([src1, src2])
    regenerate_album_exports(album, library, folder)
    names = sorted(p.name for p in folder.iterdir() if p.is_symlink())
    assert names == ["01 - alpha.mp3", "02 - bravo.flac"]


# --- TC-08-04 idempotence ---


def test_TC_08_04_regenerate_idempotent(tmp_path):
    # Spec: TC-08-04 — running twice produces byte-identical M3U + same symlink set.
    paths = _seed_real_files(tmp_path, 3)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({p: _make_track(p, title=f"t{i}") for i, p in enumerate(paths)})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)
    body1 = (folder / PLAYLIST_FILENAME).read_text(encoding="utf-8")
    set1 = sorted(p.name for p in folder.iterdir() if p.is_symlink())
    regenerate_album_exports(album, library, folder)
    body2 = (folder / PLAYLIST_FILENAME).read_text(encoding="utf-8")
    set2 = sorted(p.name for p in folder.iterdir() if p.is_symlink())
    assert body1 == body2
    assert set1 == set2


# --- TC-08-05 / TC-08-05a missing track behaviours ---


def test_TC_08_05_missing_track_skipped_in_loose_mode(tmp_path):
    # Spec: TC-08-05 — non-strict skips missing track; M3U omits entry
    paths = _seed_real_files(tmp_path, 2)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({
        paths[0]: _make_track(paths[0]),
        # paths[1] absent → library.find returns None
    })
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder, strict=False)
    names = [p.name for p in folder.iterdir() if p.is_symlink()]
    assert len(names) == 1
    assert names[0].startswith("01 -")  # gap visible: only position 1 present


def test_TC_08_05a_strict_mode_raises_on_missing(tmp_path):
    # Spec: TC-08-05a — strict mode raises FileNotFoundError; live folder unchanged.
    paths = _seed_real_files(tmp_path, 2)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    with pytest.raises(FileNotFoundError):
        regenerate_album_exports(album, library, folder, strict=True)
    assert not (folder / PLAYLIST_FILENAME).exists()


# --- TC-08-07 real files preserved ---


def test_TC_08_07_real_files_preserved(tmp_path):
    # Spec: TC-08-07 — `_commit_export` only mutates symlinks + M3U
    paths = _seed_real_files(tmp_path, 1)
    folder = tmp_path / "album"
    folder.mkdir()
    (folder / "album.json").write_text("{}")
    (folder / ".approved").touch()
    (folder / "notes.txt").write_text("manual notes")
    (folder / "reports").mkdir()
    (folder / "reports" / "old.pdf").write_bytes(b"\x00")
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)
    regenerate_album_exports(album, library, folder)  # twice
    assert (folder / "album.json").exists()
    assert (folder / ".approved").exists()
    assert (folder / "notes.txt").read_text() == "manual notes"
    assert (folder / "reports" / "old.pdf").exists()


# --- TC-08-09 staging-build crash leaves live folder unchanged ---


def test_TC_08_09_partial_staging_does_not_touch_live(tmp_path):
    # Spec: TC-08-09 — kill mid-staging-build leaves live folder untouched.
    paths = _seed_real_files(tmp_path, 2)
    folder = tmp_path / "album"
    folder.mkdir()
    # Pre-existing live state — confirm it is not mutated by a failed pass.
    pre_existing = folder / "01 - prior.mp3"
    pre_existing.symlink_to(paths[0])
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    # Force build_staging to raise mid-loop by rejecting strict mode.
    with pytest.raises(FileNotFoundError):
        regenerate_album_exports(album, library, folder, strict=True)
    # Pre-existing symlink survived; no .export.new dir leaks (pipeline cleans
    # staging in finally even on exception).
    assert pre_existing.is_symlink()
    assert not (folder / STAGING_DIRNAME).exists()


# --- TC-08-11 stale-staging cleanup ---


def test_TC_08_11_cleanup_stale_staging(tmp_path):
    # Spec: TC-08-11 — leftover .export.new is wiped by `cleanup_stale_staging`.
    folder = tmp_path / "album"
    folder.mkdir()
    staging = folder / STAGING_DIRNAME
    staging.mkdir()
    (staging / "leftover").write_text("crash debris")
    assert cleanup_stale_staging(folder) is True
    assert not staging.exists()
    # Calling again is a no-op.
    assert cleanup_stale_staging(folder) is False


# --- TC-08-13 reorder produces renumbered names ---


def test_TC_08_13_reorder_renumbers(tmp_path):
    # Spec: TC-08-13 — reorder renumbers symlinks; no leftovers.
    paths = _seed_real_files(tmp_path, 3)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({p: _make_track(p, title=f"t{i}") for i, p in enumerate(paths)})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)
    # Reorder: swap 0 and 2.
    album.track_paths = [str(paths[2]), str(paths[1]), str(paths[0])]
    regenerate_album_exports(album, library, folder)
    names = sorted(p.name for p in folder.iterdir() if p.is_symlink())
    assert names == ["01 - t2.mp3", "02 - t1.mp3", "03 - t0.mp3"]


# --- TC-08-14 library.refresh() once per pass ---


def test_TC_08_14_library_refresh_once(tmp_path):
    # Spec: TC-08-14 — library.refresh() runs exactly once per pass.
    paths = _seed_real_files(tmp_path, 1)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)
    assert library.refresh_calls == 1
    regenerate_album_exports(album, library, folder)
    assert library.refresh_calls == 2


# --- TC-08-15 64-byte sanity check (warning, no abort) ---


def test_TC_08_15_zero_byte_target_logs_but_completes(tmp_path):
    # Spec: TC-08-15 — zero-byte target produces warning; export still completes.
    src = tmp_path / "empty.mpeg"
    src.write_bytes(b"")
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({src: _make_track(src, title="empty")})
    album = _make_album([src])
    regenerate_album_exports(album, library, folder)
    assert any(p.name.startswith("01 -") for p in folder.iterdir() if p.is_symlink())
    log = (folder / ".export-log").read_text(encoding="utf-8")
    assert log  # at least one entry written


# --- TC-08-16 .export-log rotation ---


def test_TC_08_16_export_log_rotation(tmp_path):
    # Spec: TC-08-16 — .export-log keeps last 10 entries.
    paths = _seed_real_files(tmp_path, 1)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    for _ in range(15):
        regenerate_album_exports(album, library, folder)
    log = (folder / ".export-log").read_text(encoding="utf-8")
    lines = [ln for ln in log.splitlines() if ln.strip()]
    assert len(lines) == 10


# --- TC-08-17 dangling symlinks after source move (re-export non-strict) ---


def test_TC_08_17_re_export_skips_dangling(tmp_path):
    # Spec: TC-08-17 — non-strict re-export over dangling links omits missing
    # entries instead of aborting.
    src = tmp_path / "source.mpeg"
    src.write_bytes(b"X" * 128)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({src: _make_track(src)})
    album = _make_album([src])
    regenerate_album_exports(album, library, folder, strict=False)
    src.unlink()
    library._tracks.clear()
    regenerate_album_exports(album, library, folder, strict=False)
    body = (folder / PLAYLIST_FILENAME).read_text(encoding="utf-8")
    assert body == "#EXTM3U\n"
    # Stale symlink swept by `_commit_export`'s `existing - new` unlink loop.
    assert not any(p.is_symlink() for p in folder.iterdir())


# --- TC-08-18 control-character path is rejected ---


def test_TC_08_18_control_char_path_rejected(tmp_path):
    # Spec: TC-08-18 — path containing control char is skipped with toast.
    bad = tmp_path / "with\nnewline.mpeg"
    # Some filesystems actually allow newlines; create a stub directly.
    try:
        bad.write_bytes(b"X")
    except OSError:
        pytest.skip("filesystem does not allow newlines in filenames")
    good = tmp_path / "ok.mpeg"
    good.write_bytes(b"X" * 128)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({bad: _make_track(bad), good: _make_track(good)})
    album = _make_album([bad, good])
    regenerate_album_exports(album, library, folder, strict=False)
    names = [p.name for p in folder.iterdir() if p.is_symlink()]
    assert all("newline" not in n for n in names)
    assert len(names) == 1


# --- TC-08-19 drift-detection invariant ---


def test_TC_08_19_drift_detection(tmp_path):
    # Spec: TC-08-19 — symlink count mismatch flagged via `is_export_fresh`.
    paths = _seed_real_files(tmp_path, 2)
    folder = tmp_path / "album"
    folder.mkdir()
    library = _FakeLibrary({p: _make_track(p) for p in paths})
    album = _make_album(paths)
    regenerate_album_exports(album, library, folder)
    assert is_export_fresh(album, folder, library) is True
    # Simulate partial-commit crash: unlink one of the live symlinks.
    for p in folder.iterdir():
        if p.is_symlink():
            p.unlink()
            break
    assert is_export_fresh(album, folder, library) is False


# --- TC-08-07 album folder missing aborts ---


def test_album_folder_missing_aborts(tmp_path):
    # Spec 08 §Errors row "Album folder deleted mid-session"
    paths = _seed_real_files(tmp_path, 1)
    library = _FakeLibrary({paths[0]: _make_track(paths[0])})
    album = _make_album(paths)
    nonexistent = tmp_path / "gone"
    with pytest.raises(FileNotFoundError):
        regenerate_album_exports(album, library, nonexistent)
