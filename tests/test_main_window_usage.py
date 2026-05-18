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
def test_main_window_constructs_usage_index(qtbot, project_root) -> None:
    store = AlbumStore(project_root / "Albums")
    library_watcher = LibraryWatcher(project_root / "Tracks")
    state = _make_state()
    window = MainWindow(store, library_watcher, state, project_root)
    qtbot.addWidget(window)
    assert hasattr(window, "_usage_index")
    assert isinstance(window._usage_index, UsageIndex)
    # The library pane has the index injected.
    assert window.library_pane._model._usage_index is window._usage_index


# Spec: TC-13-05 / TC-13-06 — _on_approve and _on_reopen must call
# `self._usage_index.rebuild()` between the success guard and the pane-refresh
# chain. This is a Spec 13 §Behavior rule (rebuild before pane refresh so
# the Used column paints once with correct counts), not an implementation
# detail. Source-text inspection is the right tool here: a full behavioural
# test would have to mock the modal QMessageBox + report generation + file
# manager open, all of which are tested separately. A source grep catches a
# regression where someone deletes the explicit rebuild call.
@pytest.mark.parametrize("method_name", ["_on_approve", "_on_reopen"])
def test_approve_and_reopen_handlers_call_usage_index_rebuild(method_name: str) -> None:
    src = inspect.getsource(getattr(MainWindow, method_name))
    assert "self._usage_index.rebuild()" in src, (
        f"MainWindow.{method_name} must call self._usage_index.rebuild() "
        f"per Spec 13 §Behavior (rebuild before pane refresh)"
    )
