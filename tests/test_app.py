"""Tests for app.py module-level helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PyQt6.QtCore import QSharedMemory
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QMainWindow

from album_builder import app


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "album-builder"


def test_resolve_tracks_dir_prefers_settings(
    xdg_config: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    user_tracks = tmp_path / "MyMusic"
    user_tracks.mkdir()
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": str(user_tracks)})
    )
    assert app._resolve_tracks_dir() == user_tracks
    # No warning emitted when settings.json wins
    assert "using dev-tree path" not in capsys.readouterr().err


def test_resolve_tracks_dir_warns_when_falling_back_to_dev(
    xdg_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """When settings.json is absent and the dev path exists, the function
    returns the dev path BUT prints a warning so the user knows their
    install is mis-configured."""
    fake_dev = tmp_path / "dev_tracks"
    fake_dev.mkdir()
    monkeypatch.setattr(app, "DEFAULT_TRACKS_DIR", fake_dev)
    assert app._resolve_tracks_dir() == fake_dev
    assert "using dev-tree path" in capsys.readouterr().err


def test_resolve_tracks_dir_settings_wins_over_dev_path(
    xdg_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Even when both settings.json and the dev path exist, settings wins.
    This is the regression we are fixing — installed users were silently
    scanning the dev tree instead of their own folder."""
    fake_dev = tmp_path / "dev_tracks"
    fake_dev.mkdir()
    monkeypatch.setattr(app, "DEFAULT_TRACKS_DIR", fake_dev)
    user_tracks = tmp_path / "user_tracks"
    user_tracks.mkdir()
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": str(user_tracks)})
    )
    assert app._resolve_tracks_dir() == user_tracks
    assert "using dev-tree path" not in capsys.readouterr().err


# --- Project-root resolution (L8-C1) ----------------------------------------

# Spec: L8-C1 (Tier 1 indie-review 2026-04-30)
def test_resolve_project_root_reads_albums_folder_setting(
    xdg_config: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Installed users with ``albums_folder`` configured get the parent of that
    folder as their project root — Albums/ + state.json land there, not in
    whatever CWD Plasma inherited at launch."""
    user_albums = tmp_path / "MyMusic" / "Albums"
    user_albums.mkdir(parents=True)
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"albums_folder": str(user_albums)})
    )
    # CWD is irrelevant when settings.json wins.
    monkeypatch.chdir(tmp_path)
    assert app._resolve_project_root() == user_albums.parent


def test_resolve_project_root_falls_back_to_repo_root_in_dev_tree(
    xdg_config: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Running from the source checkout (no settings.json) returns the repo
    root, not whatever CWD the test runner started in. This is the path
    used by `python -m album_builder` from arbitrary terminals."""
    monkeypatch.chdir(tmp_path)  # not the repo root
    monkeypatch.setenv("ALBUM_BUILDER_DEV_MODE", "1")
    repo_root = Path(app.__file__).resolve().parent.parent.parent
    assert app._resolve_project_root() == repo_root


def test_resolve_project_root_warns_on_installed_no_config(
    xdg_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Installed launcher with no settings.json must surface a warning so the
    user knows their Albums/ location is CWD-dependent. Without this the
    silent fallback would write to ``~/Albums/`` on Plasma sessions
    (the L8-C1 ship-blocker)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALBUM_BUILDER_DEV_MODE", raising=False)
    monkeypatch.setattr(app, "_running_from_source_tree", lambda: False)
    result = app._resolve_project_root()
    assert result == tmp_path
    err = capsys.readouterr().err
    assert "albums_folder" in err
    assert "settings.json" in err


# --- Single-instance lock + raise handshake ---------------------------------

@pytest.fixture
def isolated_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Per-test SHM/socket key so concurrent runs don't collide and an
    abnormally-exited prior test can't lock us out."""
    key = f"album-builder-test-{os.getpid()}-{id(object())}"
    monkeypatch.setattr(app, "SHARED_KEY", key)
    # Make sure no stale socket lingers from a previous failed run.
    QLocalServer.removeServer(key)
    yield key
    QLocalServer.removeServer(key)


def test_acquire_single_instance_lock_succeeds_when_unheld(
    qtbot, isolated_key: str
) -> None:
    lock = app.acquire_single_instance_lock()
    try:
        assert lock is not None
        assert lock.isAttached()
    finally:
        if lock is not None:
            lock.detach()


def test_acquire_single_instance_lock_fails_when_held(
    qtbot, isolated_key: str
) -> None:
    first = app.acquire_single_instance_lock()
    try:
        assert first is not None
        # A second acquisition from the same process must fail — the first
        # call still owns the segment. This is the invariant that prevents
        # a second `album-builder` process from also opening a window.
        second = app.acquire_single_instance_lock()
        assert second is None
    finally:
        if first is not None:
            first.detach()


def test_acquire_single_instance_lock_recovers_from_orphaned_segment(
    qtbot, isolated_key: str
) -> None:
    """Stale-segment recovery: simulate a previous process that created the
    SHM segment and exited without detaching cleanly. The next acquire()
    must reclaim it, not lock the user out forever."""
    orphan = QSharedMemory(isolated_key)
    assert orphan.create(1)
    # Drop our last reference WITHOUT calling detach() the way a clean shutdown
    # would — the way SIGKILL/OOM/power-loss would leave it. Note: in the same
    # Python process Qt does track this object, so this is a best-effort
    # simulation of the kernel-level orphan condition.
    del orphan

    lock = app.acquire_single_instance_lock()
    try:
        assert lock is not None, "stale-segment recovery failed; user is locked out"
    finally:
        if lock is not None:
            lock.detach()


def test_raise_server_brings_window_to_front(qtbot, isolated_key: str) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    window.hide()
    server = app.start_raise_server(window)
    try:
        # Connect a client socket and send the raise message, mimicking what
        # signal_raise_existing_instance() does from a second process.
        client = QLocalSocket()
        client.connectToServer(isolated_key)
        assert client.waitForConnected(1000)
        client.write(app.RAISE_MESSAGE)
        client.flush()
        client.waitForBytesWritten(1000)

        # Poll until the server has handled the connection and shown the window.
        qtbot.waitUntil(window.isVisible, timeout=2000)
        assert window.isVisible()
        client.disconnectFromServer()
    finally:
        server.close()


def test_signal_raise_existing_instance_is_silent_when_no_server(
    qtbot, isolated_key: str
) -> None:
    """If no instance is listening (e.g. the user typed `album-builder` on a
    fresh boot), the signal helper must return cleanly — not crash, not hang."""
    # No server has been started — the call should time out quietly.
    app.signal_raise_existing_instance()


# --- Icon single-source ----------------------------------------------------

def test_resolve_app_icon_returns_none_when_no_theme_no_dev_svg(
    qtbot, tmp_path: Path
) -> None:
    """When neither the icon theme nor the dev SVG is present, resolution
    must return None (not an empty QIcon) so the caller can skip
    setWindowIcon entirely."""
    nonexistent_theme = "album-builder-test-no-such-icon-zzz"
    fake_svg_path = tmp_path / "missing.svg"  # does NOT exist
    assert app.resolve_app_icon(nonexistent_theme, fake_svg_path) is None


def test_resolve_app_icon_falls_back_to_dev_svg(qtbot, tmp_path: Path) -> None:
    """When no icon theme matches, resolution falls back to the explicit
    dev path. This is the path used when running from source pre-install."""
    nonexistent_theme = "album-builder-test-no-such-icon-zzz"
    svg = tmp_path / "fake.svg"
    svg.write_text(
        '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" '
        'width="16" height="16"><rect width="16" height="16" fill="red"/></svg>'
    )
    icon = app.resolve_app_icon(nonexistent_theme, svg)
    assert icon is not None
    assert not icon.isNull()
