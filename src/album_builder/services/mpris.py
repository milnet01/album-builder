"""MPRIS2 D-Bus service - Spec 20 (Phase G).

Exposes the running app as an `org.mpris.MediaPlayer2` player on the session
bus so KDE Plasma's media controller, the lock screen, and hardware media keys
drive the *same* `Player` + `PlaybackController` as the in-app surfaces (no
second playback pipeline). Zero new dependencies: `PyQt6.QtDBus` ships with
PyQt6.

Three layers:
  - **Pure mapping helpers** (`playback_status`, `loop_status`, `repeat_mode`,
    `track_metadata`, `_metadata_variant_map`) - value translations between the
    app domain and MPRIS wire types, unit-tested without a bus.
  - **Two `QDBusAbstractAdaptor` subclasses** on one host `QObject` - the root
    (`org.mpris.MediaPlayer2`) and player (`.Player`) interfaces. Property reads
    pull live from the services (no shadow state); writes forward to the same
    setters the in-app transport uses.
  - **`MprisService`** - owns the host + adaptors, the bus registration (guarded
    by `available`), the cover-art temp file, and the `PropertiesChanged` /
    `Seeked` emit chokepoints wired to the Spec 18 broadcast signals.

D-Bus type pinning is load-bearing: PyQt6 marshals a Python `int` value-
dependently (a short length is `i`/int32, only past ~71 min does it reach
`x`/int64) and a plain `list` as `av` not `as`. Every `x` / `o` / `as` wire
value is pinned to its Qt type. Critically, the `Metadata` getter returns a
**plain dict** with per-value typed carriers - returning a whole-map
`QDBusArgument` hard-aborts the process (SIGABRT) on client read (verified over
a live bus 2026-07-18).
"""

from __future__ import annotations

import logging
import os
import tempfile

from PyQt6.QtCore import (
    QMetaType,
    QObject,
    pyqtClassInfo,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusArgument,
    QDBusConnection,
    QDBusMessage,
    QDBusObjectPath,
    QDBusVariant,
)
from PyQt6.QtWidgets import QApplication

from album_builder.domain.play_queue import RepeatMode
from album_builder.domain.track import Track
from album_builder.services.player import Player, PlayerState

logger = logging.getLogger(__name__)

OBJECT_PATH = "/org/mpris/MediaPlayer2"
BUS_NAME = "org.mpris.MediaPlayer2.albumbuilder"
_TRACKID_PREFIX = "/org/mpris/MediaPlayer2/albumbuilder/track/"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_ROOT_IFACE = "org.mpris.MediaPlayer2"
_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"

# MIME types the library can scan (domain/library.py extensions). Advisory only:
# OpenUri is a no-op, so this just declares what the app *could* accept.
_SUPPORTED_MIME_TYPES = [
    "audio/mpeg", "audio/mp4", "audio/flac", "audio/ogg", "audio/opus",
    "audio/x-wav",
]

# Cover-art temp-file suffix per image MIME. A recognisable extension helps
# some controllers pick a decoder; anything unknown falls back to .img.
_MIME_SUFFIX = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/gif": ".gif", "image/webp": ".webp", "image/bmp": ".bmp",
}


# ---- Pure mapping helpers (unit-tested without a bus) ------------------------


def playback_status(state: PlayerState) -> str:
    """MPRIS `PlaybackStatus`. MPRIS has no error state - ERROR reads Stopped."""
    match state:
        case PlayerState.PLAYING:
            return "Playing"
        case PlayerState.PAUSED:
            return "Paused"
        case _:
            return "Stopped"


def loop_status(mode: RepeatMode) -> str:
    """MPRIS `LoopStatus` from the app's RepeatMode."""
    match mode:
        case RepeatMode.ONE:
            return "Track"
        case RepeatMode.ALL:
            return "Playlist"
        case _:
            return "None"


def repeat_mode(status: str) -> RepeatMode:
    """Inverse of `loop_status`; an unknown/out-of-enum string -> OFF (defensive:
    a client may send a value outside the MPRIS set)."""
    match status:
        case "Track":
            return RepeatMode.ONE
        case "Playlist":
            return RepeatMode.ALL
        case _:
            return RepeatMode.OFF


def track_metadata(track: Track | None, art_url: str | None, track_no: int) -> dict:
    """Build the MPRIS `a{sv}` metadata map as a plain Python dict.

    On `None` track: an **empty map** `{}` (the MPRIS "no current track"
    convention - a NoTrack sentinel path would render a phantom track in some
    controllers). On a track: `mpris:trackid` as a `QDBusObjectPath` (a bare
    `str` marshals as `s`, not the required `o`, and breaks SetPosition's
    object-path compare), plus `mpris:length` (microseconds, plain int here -
    pinned to int64 by `_metadata_variant_map`), `xesam:title`, `xesam:artist`
    (a `[str]` list, pinned to `as` by `_metadata_variant_map`), `xesam:album`,
    and `mpris:artUrl` iff `art_url` is set.

    The trackid path is `/org/mpris/MediaPlayer2/albumbuilder/track/<track_no>`,
    where `track_no` is a service-owned monotonic counter that changes per
    track-*instance* (not per queue slot) for the SetPosition race-guard.
    """
    if track is None:
        return {}
    meta: dict = {
        "mpris:trackid": QDBusObjectPath(_TRACKID_PREFIX + str(track_no)),
        "mpris:length": round(track.duration_seconds * 1_000_000),
        "xesam:title": track.title,
        "xesam:artist": [track.artist],
        "xesam:album": track.album,
    }
    if art_url is not None:
        meta["mpris:artUrl"] = art_url
    return meta


def _metadata_variant_map(meta: dict) -> dict:
    """Re-wrap `track_metadata`'s logical values in their typed D-Bus carriers.

    Returns a new plain dict (never a whole-map `QDBusArgument` - that aborts the
    process on read) with `mpris:length` as an int64 `QDBusArgument`,
    `xesam:artist` as an `as` `QDBusArgument`, and `mpris:trackid` passed through
    as its `QDBusObjectPath`. String values stay plain `str` (`s`). This is the
    value the `Metadata` getter returns and the `PropertiesChanged{Metadata}`
    emit carries.
    """
    out = dict(meta)
    if "mpris:length" in out:
        length = QDBusArgument()
        length.add(int(out["mpris:length"]), QMetaType.Type.LongLong.value)
        out["mpris:length"] = length
    if "xesam:artist" in out:
        artist = QDBusArgument()
        artist.beginArray(QMetaType.Type.QString.value)
        for name in meta["xesam:artist"]:
            artist.add(name)
        artist.endArray()
        out["xesam:artist"] = artist
    return out


def _cover_suffix(cover_mime: str | None) -> str:
    if not cover_mime:
        return ".img"
    return _MIME_SUFFIX.get(cover_mime.lower(), ".img")


# ---- Adaptors ---------------------------------------------------------------


@pyqtClassInfo("D-Bus Interface", _ROOT_IFACE)
class MediaPlayer2Adaptor(QDBusAbstractAdaptor):
    """Root `org.mpris.MediaPlayer2` interface - app identity + Raise/Quit."""

    def __init__(self, host: QObject, window, app: QApplication) -> None:
        super().__init__(host)
        self._window = window
        self._app = app

    @pyqtSlot()
    def Raise(self) -> None:
        from album_builder.ui.window_util import bring_to_front
        bring_to_front(self._window)

    @pyqtSlot()
    def Quit(self) -> None:
        self._app.quit()

    @pyqtProperty(bool)
    def CanQuit(self) -> bool:
        return True

    @pyqtProperty(bool)
    def CanRaise(self) -> bool:
        return True

    @pyqtProperty(bool)
    def HasTrackList(self) -> bool:
        return False

    @pyqtProperty(str)
    def Identity(self) -> str:
        name = self._app.applicationName() if self._app else ""
        return name or "Album Builder"

    @pyqtProperty(str)
    def DesktopEntry(self) -> str:
        entry = self._app.desktopFileName() if self._app else ""
        return entry or "album-builder"

    @pyqtProperty("QStringList")
    def SupportedUriSchemes(self) -> list[str]:
        return ["file"]

    @pyqtProperty("QStringList")
    def SupportedMimeTypes(self) -> list[str]:
        return list(_SUPPORTED_MIME_TYPES)


@pyqtClassInfo("D-Bus Interface", _PLAYER_IFACE)
class MediaPlayer2PlayerAdaptor(QDBusAbstractAdaptor):
    """Player `org.mpris.MediaPlayer2.Player` interface - transport + state.

    Holds no shadow state: property reads pull live from `Player` /
    `PlaybackController`, and the cover-art URL + trackid counter are read
    through the `art_url` / `track_no` callables bound to `MprisService`.
    """

    # Pinned to `x` (int64) via 'qlonglong' - a plain pyqtSignal(int) marshals
    # int32 and overflows past ~35.8 min.
    Seeked = pyqtSignal("qlonglong")

    def __init__(self, host: QObject, player: Player, controller, art_url, track_no) -> None:
        super().__init__(host)
        self._player = player
        self._controller = controller
        self.art_url = art_url
        self.track_no = track_no

    # -- Methods --

    @pyqtSlot()
    def Next(self) -> None:
        self._controller.next()

    @pyqtSlot()
    def Previous(self) -> None:
        self._controller.previous()

    @pyqtSlot()
    def Pause(self) -> None:
        self._player.pause()

    @pyqtSlot()
    def Play(self) -> None:
        self._player.play()

    @pyqtSlot()
    def PlayPause(self) -> None:
        self._player.toggle()

    @pyqtSlot()
    def Stop(self) -> None:
        self._player.stop()

    @pyqtSlot("qlonglong")
    def Seek(self, offset: int) -> None:
        # offset is signed microseconds; Player.seek clamps to [0, dur-1].
        self._player.seek(self._player.position() + offset / 1_000_000)

    @pyqtSlot(QDBusObjectPath, "qlonglong")
    def SetPosition(self, track_id: QDBusObjectPath, position: int) -> None:
        # MPRIS race-guard: drop a stale request against a track that already
        # changed. Range-check here (a no-op, not a clamp) rather than delegating
        # to Player.seek's clamp; position is us, duration() is seconds.
        if track_id.path() != _TRACKID_PREFIX + str(self.track_no()):
            return
        if not 0 <= position <= self._player.duration() * 1_000_000:
            return
        self._player.seek(position / 1_000_000)

    @pyqtSlot(str)
    def OpenUri(self, uri: str) -> None:
        # No-op: the app plays only its own library (Spec 20 §Out of scope).
        # SupportedUriSchemes lists 'file' for honesty, but no load path is wired.
        pass

    # -- Properties --

    @pyqtProperty(str)
    def PlaybackStatus(self) -> str:
        return playback_status(self._player.state())

    @pyqtProperty(str)
    def LoopStatus(self) -> str:
        return loop_status(self._controller.repeat_mode())

    @LoopStatus.setter
    def LoopStatus(self, value: str) -> None:
        self._controller.set_repeat(repeat_mode(value))

    @pyqtProperty(float)
    def Rate(self) -> float:
        return 1.0

    @Rate.setter
    def Rate(self, value: float) -> None:
        # Accepted and ignored - the app has no rate control.
        pass

    @pyqtProperty(float)
    def MinimumRate(self) -> float:
        return 1.0

    @pyqtProperty(float)
    def MaximumRate(self) -> float:
        return 1.0

    @pyqtProperty(bool)
    def Shuffle(self) -> bool:
        return self._controller.shuffle_enabled()

    @Shuffle.setter
    def Shuffle(self, value: bool) -> None:
        self._controller.set_shuffle(bool(value))

    @pyqtProperty("QVariantMap")
    def Metadata(self) -> dict:
        return _metadata_variant_map(
            track_metadata(self._controller.current_track(), self.art_url(), self.track_no())
        )

    @pyqtProperty(float)
    def Volume(self) -> float:
        return self._player.volume() / 100.0

    @Volume.setter
    def Volume(self, value: float) -> None:
        self._player.set_volume(round(value * 100))

    @pyqtProperty("qlonglong")
    def Position(self) -> int:
        return round(self._player.position() * 1_000_000)

    @pyqtProperty(bool)
    def CanGoNext(self) -> bool:
        return len(self._controller.play_order()) > 0

    @pyqtProperty(bool)
    def CanGoPrevious(self) -> bool:
        return len(self._controller.play_order()) > 0

    @pyqtProperty(bool)
    def CanPlay(self) -> bool:
        return self._controller.current_track() is not None

    @pyqtProperty(bool)
    def CanPause(self) -> bool:
        return self._controller.current_track() is not None

    @pyqtProperty(bool)
    def CanSeek(self) -> bool:
        return self._player.duration() > 0

    @pyqtProperty(bool)
    def CanControl(self) -> bool:
        return True


# ---- Service ----------------------------------------------------------------


class MprisService(QObject):
    """Owns the MPRIS host object, its two adaptors, the bus registration, the
    cover-art temp file, and the emit chokepoints. Signal handlers connect
    unconditionally (that is what makes the wiring testable without a bus); only
    the actual D-Bus send is gated by `available`.
    """

    def __init__(self, player: Player, controller, window, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._controller = controller
        self._window = window

        self._art_url: str | None = None
        self._art_path: str | None = None
        self._track_no = 0

        # Host object + adaptors. The adaptors read the service's rolling art
        # url + trackid counter through bound getters (one source of truth).
        self._host = QObject(self)
        self._root_adaptor = MediaPlayer2Adaptor(
            self._host, window, QApplication.instance()
        )
        self._player_adaptor = MediaPlayer2PlayerAdaptor(
            self._host, player, controller,
            lambda: self._art_url, lambda: self._track_no,
        )

        # Bus registration (guarded). self._bus always exists so a test can force
        # available=True and inject a fake bus at the send seam.
        self._bus = QDBusConnection.sessionBus()
        self.available = self._register()

        # Handlers connect unconditionally; the bus gate lives at the chokepoint.
        self._connect_handlers()

    # -- Registration --

    def _register(self) -> bool:
        if not self._bus.isConnected():
            logger.info("MPRIS: no session bus; running without desktop integration")
            return False
        if not self._bus.registerService(BUS_NAME):
            logger.info("MPRIS: bus name %s unavailable; not registering", BUS_NAME)
            return False
        if not self._bus.registerObject(
            OBJECT_PATH, self._host,
            QDBusConnection.RegisterOption.ExportAdaptors,
        ):
            logger.info("MPRIS: object registration failed at %s", OBJECT_PATH)
            self._bus.unregisterService(BUS_NAME)
            return False
        return True

    def unregister(self) -> None:
        """Drop the bus name + object so a relaunch is clean, and remove the
        cover-art temp file. Idempotent; safe on the unavailable path."""
        if self.available:
            self._bus.unregisterObject(OBJECT_PATH)
            self._bus.unregisterService(BUS_NAME)
            self.available = False
        self._clear_art()

    # -- Signal wiring --

    def _connect_handlers(self) -> None:
        self._player.state_changed.connect(self._on_state_changed)
        self._player.duration_changed.connect(self._on_duration_changed)
        self._player.volume_changed.connect(self._on_volume_changed)
        self._player.seeked.connect(self._on_seeked)
        self._controller.current_changed.connect(self._on_current_changed)
        self._controller.queue_changed.connect(self._on_queue_changed)
        self._controller.shuffle_changed.connect(self._on_shuffle_changed)
        self._controller.repeat_changed.connect(self._on_repeat_changed)

    def _on_state_changed(self, *_a) -> None:
        self._emit_properties_changed(
            _PLAYER_IFACE,
            {"PlaybackStatus": playback_status(self._player.state())}, [],
        )

    def _on_duration_changed(self, *_a) -> None:
        # CanSeek only - QMediaPlayer reports duration asynchronously (0 at
        # current_changed time), so this re-emits once the real duration lands
        # and Plasma's seek bar enables. mpris:length is NOT recomputed here: it
        # comes from track.duration_seconds (mutagen, correct at current_changed).
        self._emit_properties_changed(
            _PLAYER_IFACE, {"CanSeek": self._player.duration() > 0}, [],
        )

    def _on_volume_changed(self, *_a) -> None:
        self._emit_properties_changed(
            _PLAYER_IFACE, {"Volume": self._player.volume() / 100.0}, [],
        )

    def _on_shuffle_changed(self, *_a) -> None:
        self._emit_properties_changed(
            _PLAYER_IFACE, {"Shuffle": self._controller.shuffle_enabled()}, [],
        )

    def _on_repeat_changed(self, *_a) -> None:
        self._emit_properties_changed(
            _PLAYER_IFACE,
            {"LoopStatus": loop_status(self._controller.repeat_mode())}, [],
        )

    def _on_queue_changed(self, *_a) -> None:
        has = len(self._controller.play_order()) > 0
        self._emit_properties_changed(
            _PLAYER_IFACE, {"CanGoNext": has, "CanGoPrevious": has}, [],
        )

    def _on_current_changed(self, track) -> None:
        # Refresh art first (bumps the trackid counter), then broadcast Metadata
        # + the Can* flags that depend on having a current track.
        self._refresh_art(track)
        current = self._controller.current_track() is not None
        self._emit_properties_changed(
            _PLAYER_IFACE,
            {
                "Metadata": _metadata_variant_map(
                    track_metadata(
                        self._controller.current_track(), self._art_url, self._track_no
                    )
                ),
                "CanGoNext": len(self._controller.play_order()) > 0,
                "CanGoPrevious": len(self._controller.play_order()) > 0,
                "CanPlay": current,
                "CanPause": current,
                "CanSeek": self._player.duration() > 0,
            },
            [],
        )

    def _on_seeked(self, seconds: float) -> None:
        self._emit_seeked(round(seconds * 1_000_000))

    # -- Cover-art temp file (connected unconditionally, bus-independent) --

    def _refresh_art(self, track) -> None:
        if track is not None:
            self._track_no += 1
        self._clear_art()
        if track is None or not getattr(track, "cover_data", None):
            return
        try:
            fd, path = tempfile.mkstemp(
                prefix="album-builder-cover-", suffix=_cover_suffix(track.cover_mime)
            )
            with os.fdopen(fd, "wb") as fh:
                fh.write(track.cover_data)
        except OSError as exc:
            logger.warning("MPRIS: could not write cover-art temp file: %s", exc)
            return
        self._art_path = path
        self._art_url = "file://" + path

    def _clear_art(self) -> None:
        if self._art_path:
            try:
                os.unlink(self._art_path)
            except OSError:
                pass
        self._art_path = None
        self._art_url = None

    # -- Emit chokepoints (the bus gate + the spied send seam) --

    def _emit_properties_changed(self, interface: str, changed: dict, invalidated: list) -> None:
        if not self.available:
            return
        msg = QDBusMessage.createSignal(OBJECT_PATH, _PROPS_IFACE, "PropertiesChanged")
        changed_variants = {k: QDBusVariant(v) for k, v in changed.items()}
        msg.setArguments([interface, changed_variants, invalidated])
        self._send(msg)

    def _send(self, msg: QDBusMessage) -> None:
        """Low-level bus send - the seam TC-20-09 spies to verify the guard."""
        self._bus.send(msg)

    def _emit_seeked(self, position_us: int) -> None:
        if not self.available:
            return
        # Emit the adaptor's 'qlonglong'-typed pyqtSignal (exported to the bus by
        # registerObject(ExportAdaptors)), so it reaches D-Bus pinned to `x`.
        self._player_adaptor.Seeked.emit(position_us)
