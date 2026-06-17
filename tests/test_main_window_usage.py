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


def _make_window(qtbot, project_root) -> MainWindow:
    store = AlbumStore(project_root / "Albums")
    library_watcher = LibraryWatcher(project_root / "Tracks")
    window = MainWindow(store, library_watcher, _make_state(), project_root)
    qtbot.addWidget(window)
    return window


# Spec: TC-13-05 setup - MainWindow constructs UsageIndex with the right wiring.
def test_main_window_constructs_usage_index(qtbot, project_root) -> None:
    window = _make_window(qtbot, project_root)
    assert hasattr(window, "_usage_index")
    assert isinstance(window._usage_index, UsageIndex)
    # The library pane has the index injected.
    assert window.library_pane._model._usage_index is window._usage_index


# Spec: TC-13-05 / TC-13-06 — the actual Spec 13 §Behavior contract is an
# ORDERING rule: the usage index must be rebuilt BEFORE the pane-refresh chain,
# so the Used column paints once with correct counts (not stale then fresh
# across two frames). Exercise `_refresh_panes_after_lifecycle_change` directly
# with order-recording spies so the ordering itself is verified - something a
# source-text grep can never check.
def test_refresh_after_lifecycle_change_rebuilds_before_pane_refresh(
    qtbot, project_root, monkeypatch,
) -> None:
    window = _make_window(qtbot, project_root)
    album = window._store.create(name="Order Probe", target_count=3)

    calls: list[str] = []
    monkeypatch.setattr(window._usage_index, "rebuild",
                        lambda: calls.append("rebuild"))
    monkeypatch.setattr(window.top_bar, "set_current",
                        lambda _id: calls.append("top_bar"))
    monkeypatch.setattr(window.library_pane, "set_current_album",
                        lambda _a: calls.append("library_pane"))
    monkeypatch.setattr(window.album_order_pane, "set_album",
                        lambda _a, _tracks: calls.append("album_order_pane"))

    window._refresh_panes_after_lifecycle_change(album.id)

    assert "rebuild" in calls, "usage index must be rebuilt on a lifecycle change"
    # Rebuild strictly precedes every pane refresh.
    assert calls.index("rebuild") < calls.index("top_bar")
    assert calls.index("rebuild") < calls.index("library_pane")
    assert calls.index("rebuild") < calls.index("album_order_pane")


# Spec: TC-13-05 / TC-13-06 — both lifecycle handlers must route their
# post-success pane refresh through `_refresh_panes_after_lifecycle_change`
# (whose rebuild-before-refresh ordering is verified behaviourally above).
# Driving the full handlers here would require a real approve (symlink export +
# WeasyPrint PDF) just to reach the refresh, so a wiring check on the delegation
# call is the proportionate guard against someone deleting it.
@pytest.mark.parametrize("method_name", ["_on_approve", "_on_reopen"])
def test_lifecycle_handlers_delegate_to_refresh_helper(method_name: str) -> None:
    src = inspect.getsource(getattr(MainWindow, method_name))
    assert "self._refresh_panes_after_lifecycle_change(album_id)" in src, (
        f"MainWindow.{method_name} must delegate its post-success pane refresh "
        f"to _refresh_panes_after_lifecycle_change (Spec 13 §Behavior)"
    )
