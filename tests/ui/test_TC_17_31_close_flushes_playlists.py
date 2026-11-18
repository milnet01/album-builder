"""TC-17-31 - closing the window writes a pending playlist change.

MUSI-0409: PlaylistStore saves through a 250 ms DebouncedWriter, and its
timer never fires once the app has quit. closeEvent must flush it, as it
does AlbumStore and PlayHistory.
"""

from __future__ import annotations

from album_builder.persistence.playlist_io import load_playlists


def test_TC_17_31_close_flushes_pending_playlist_write(main_window, tmp_path) -> None:
    # Spec: TC-17-31
    win = main_window
    created = win._playlist_store.create("Road trip")

    win.close()  # at once: the debounce timer has not fired

    on_disk = load_playlists(tmp_path)
    assert [pl.id for pl in on_disk] == [created.id]
    assert on_disk[0].name == "Road trip"
