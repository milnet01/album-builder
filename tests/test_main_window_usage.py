"""MainWindow integration with UsageIndex (Spec 13 TC-13-05/06 setup)."""

from __future__ import annotations

import inspect

import pytest

from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.usage_index import UsageIndex
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "Tracks").mkdir()
    (tmp_path / "Albums").mkdir()
    return tmp_path


def _make_state():
    """Minimal AppState shim for MainWindow construction."""
    from album_builder.persistence.state_io import AppState, WindowState
    win = WindowState(x=100, y=100, width=1200, height=800,
                      splitter_sizes=[5, 3, 5])
    return AppState(
        current_album_id=None,
        last_played_track_path=None,
        window=win,
    )


# Spec: TC-13-05 setup - MainWindow constructs UsageIndex with the right wiring.
def test_main_window_constructs_usage_index(qapp, project_root) -> None:
    store = AlbumStore(project_root / "Albums")
    library_watcher = LibraryWatcher(project_root / "Tracks")
    state = _make_state()
    window = MainWindow(store, library_watcher, state, project_root)
    assert hasattr(window, "_usage_index")
    assert isinstance(window._usage_index, UsageIndex)
    # The library pane has the index injected.
    assert window.library_pane._model._usage_index is window._usage_index


# Spec: TC-13-05 - _on_approve calls usage_index.rebuild() in its body.
def test_on_approve_inserts_rebuild_call(qapp) -> None:
    src = inspect.getsource(MainWindow._on_approve)
    assert "self._usage_index.rebuild()" in src


# Spec: TC-13-06 - _on_reopen calls usage_index.rebuild() in its body.
def test_on_reopen_inserts_rebuild_call(qapp) -> None:
    src = inspect.getsource(MainWindow._on_reopen)
    assert "self._usage_index.rebuild()" in src
