"""TC-20-17 - closing the window sends nothing on the MPRIS bus.

MUSI-0367: the pre-push gate hung in MainWindow.closeEvent, blocked in
MprisService._send while Player.stop() announced the STOPPED state. Closing
must drop the bus registration before stopping the player, so shutdown
never waits on a bus send.
"""

from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtMultimedia import QMediaPlayer

from album_builder.services.player import PlayerState


def test_TC_20_17_close_while_playing_sends_nothing(main_window) -> None:
    # Spec: TC-20-17
    win = main_window
    mpris = win._mpris
    mpris.available = True
    mpris._bus = SimpleNamespace(unregisterObject=lambda path: None,
                                 unregisterService=lambda name: None)
    sent: list = []
    mpris._send = lambda msg: sent.append(msg)

    # Playing, and stop() announces STOPPED through the real handler chain.
    player = win._player
    player._state = PlayerState.PLAYING
    player.stop = lambda: player._on_playback_state(QMediaPlayer.PlaybackState.StoppedState)

    win.close()

    assert player.state() == PlayerState.STOPPED, "stop() must still run on close"
    assert sent == [], f"closeEvent sent {len(sent)} MPRIS message(s)"
    assert mpris.available is False
