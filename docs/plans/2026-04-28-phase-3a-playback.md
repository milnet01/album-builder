# Album Builder — Phase 3A: Audio Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring up audio playback. After this phase the user can click a per-row preview-play button on either the library pane or the album-order pane and hear the track through a transport bar in the right pane (now-playing). Volume + mute persist across launches; the last-played track is restored paused at zero. All Spec 00 keyboard shortcuts are wired (closing indie-review Theme E). The lyrics panel area is a placeholder — synchronized scrolling lyrics + alignment land in Phase 3B.

**Architecture:** Phase 3A adds **one new service** (`Player`, a `QMediaPlayer + QAudioOutput` wrapper that emits Qt signals normalised to seconds), **two new widgets** (`TransportBar` for the play/pause/scrubber/volume controls, `NowPlayingPane` for the right-pane composition with cover + metadata + transport + lyrics-placeholder), and **two surgical extensions** (preview-play button column on `LibraryPane` + button per row on `AlbumOrderPane`). `MainWindow` owns the `Player`; the now-playing pane is the only widget directly subscribed to `Player.position_changed`. State persists through the existing `settings.json` (volume + muted) and `state.json` (`last_played_track_path`). No new third-party dependencies — `QMediaPlayer` ships with PyQt6 and uses GStreamer on Linux.

**Tech Stack:** Python 3.11+, PyQt6 6.6+ (QtMultimedia bound), pytest 8 + pytest-qt 4. GStreamer plugin packages (`gstreamer-plugins-good`, `gstreamer-plugins-libav`) are runtime requirements on the host; Phase 3A surfaces a one-shot dialog with the install command on first decode failure. No new pip dependency.

**Specs covered:**

- **06** — Audio playback (TC-06-01 through TC-06-16).
- **00** — Keyboard shortcuts table fully wired (Ctrl+N, Ctrl+Q, F1, Space, Left/Right, Shift+Left/Right, M). Closes indie-review Theme E.
- **10** — `state.json.last_played_track_path` round-trip (already in `AppState`; just write/read). `settings.json.audio.volume` + `settings.json.audio.muted` added.
- **11** — Glyphs `PLAY` / `PAUSE` / `MUTE` / `UNMUTE` already in `theme.Glyphs`; consumed by `TransportBar`.

**Phase 3B (lyrics) explicitly deferred:** Spec 07's forced-alignment pipeline pulls in faster-whisper + wav2vec2 (~1 GB models, on-demand download, `QThread` workers). That's its own plan and its own release (v0.4.0). Phase 3A leaves a placeholder `QFrame` in the now-playing pane where the lyrics panel will go; `Player.position_changed` is fully exposed so the Phase 3B `LyricsTracker` can subscribe without refactoring. Original ROADMAP versioning slipped one notch: v0.3.0 = Phase 3A audio, v0.4.0 = Phase 3B lyrics, v0.5.0 = Phase 4 export.

**Test contract:** every TC-06-NN clause maps to one or more tests. Crosswalk lives at the bottom of this plan.

**Threat-model note (single-user desktop app, audio playback domain):**

- File access is read-only and goes through `QMediaPlayer` (no shell, no network beyond local filesystem).
- No new attack surface against `Tracks/` — the Player only ever calls `setSource(QUrl.fromLocalFile(str(path)))` on paths the library scanner already accepts.
- GStreamer is a separate trust boundary (process), already trusted by the openSUSE base install.

---

## File structure to be created or modified

```
src/album_builder/
├── persistence/
│   └── settings.py                     # MODIFY — add read_audio() / write_audio() helpers
├── services/
│   └── player.py                       # NEW — QMediaPlayer wrapper + signals
└── ui/
    ├── transport_bar.py                # NEW — play/pause + scrubber + volume widget
    ├── now_playing_pane.py             # NEW — right pane composition
    ├── toast.py                        # NEW — transient bottom-of-window error notice
    ├── library_pane.py                 # MODIFY — add preview-play column
    ├── album_order_pane.py             # MODIFY — add preview-play button per row
    ├── main_window.py                  # MODIFY — own Player, wire signals, keyboard shortcuts
    └── theme.py                        # MODIFY — QSS rules for TransportBar + Toast

tests/
├── persistence/
│   └── test_settings.py                # MODIFY (or NEW) — TC-06-10 audio round-trip
├── services/
│   └── test_player.py                  # NEW — TC-06-01..09
└── ui/
    ├── test_transport_bar.py           # NEW — TC-06-08, 14
    ├── test_now_playing_pane.py        # NEW — track display + transport composition
    ├── test_keyboard_shortcuts.py      # NEW — TC-06-12, 13 + Spec 00 table
    ├── test_toast.py                   # NEW — TC-06-05, 06, 07
    ├── test_library_pane.py            # MODIFY — preview-play column
    └── test_album_order_pane.py        # MODIFY — preview-play button

docs/specs/
└── 00-app-overview.md                  # MODIFY — flip "Wired?" column to ✓ for Phase 3A shortcuts

ROADMAP.md                              # MODIFY — close v0.3.0 block, close Theme E
src/album_builder/version.py            # MODIFY — 0.2.2 → 0.3.0
pyproject.toml                          # MODIFY — version 0.2.2 → 0.3.0
```

---

## Task 1: settings.json `audio` block

**Files:**
- Modify: `src/album_builder/persistence/settings.py`
- Create or modify: `tests/persistence/test_settings.py`

Spec 10 §`settings.json` schema names an `audio` object with `volume` (int 0–100) and `muted` (bool). Phase 3A is the first consumer; Phase 3B will add `alignment.{auto_align_on_play, model_size}` — they share the file but Phase 3A only owns the `audio` block. Bounds and type guards mirror the conservative pattern in `state_io._coerce_*`: malformed values fall back to defaults instead of raising.

- [ ] **Step 1: Write the failing tests**

```python
# tests/persistence/test_settings.py (add to or create)
from album_builder.persistence.settings import (
    AudioSettings, read_audio, write_audio, settings_path,
)

def test_audio_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    write_audio(AudioSettings(volume=65, muted=True))
    assert read_audio() == AudioSettings(volume=65, muted=True)

def test_audio_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert read_audio() == AudioSettings(volume=80, muted=False)

def test_audio_clamps_out_of_range_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"audio": {"volume": 250, "muted": false}}')
    a = read_audio()
    assert a.volume == 100  # clamped to upper bound

def test_audio_rejects_non_int_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"audio": {"volume": "loud", "muted": null}}')
    a = read_audio()
    assert a == AudioSettings(volume=80, muted=False)  # both fields default

def test_audio_write_preserves_tracks_folder(tmp_path, monkeypatch):
    """Spec 10: settings.json round-trip is partial — writing audio must not
    erase a previously-set tracks_folder."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"tracks_folder": "/home/u/Music"}')
    write_audio(AudioSettings(volume=50, muted=True))
    import json
    data = json.loads(p.read_text())
    assert data["tracks_folder"] == "/home/u/Music"
    assert data["audio"]["volume"] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/persistence/test_settings.py -v`
Expected: FAIL on `AudioSettings` import.

- [ ] **Step 3: Implement `AudioSettings` + `read_audio` + `write_audio`**

In `settings.py`:

```python
from dataclasses import dataclass

DEFAULT_VOLUME = 80
DEFAULT_MUTED = False

@dataclass(frozen=True)
class AudioSettings:
    volume: int = DEFAULT_VOLUME
    muted: bool = DEFAULT_MUTED


def _read_settings_dict() -> dict:
    """Internal — read settings.json as a dict, return {} on any failure.
    Single source of malformed-JSON handling for all readers."""
    path = settings_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning("settings.json: unreadable (%s); falling back", exc)
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("settings.json: malformed JSON (%s); falling back", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def read_audio() -> AudioSettings:
    data = _read_settings_dict()
    audio = data.get("audio")
    if not isinstance(audio, dict):
        return AudioSettings()
    raw_vol = audio.get("volume", DEFAULT_VOLUME)
    if isinstance(raw_vol, bool) or not isinstance(raw_vol, int):
        volume = DEFAULT_VOLUME
    else:
        volume = max(0, min(100, raw_vol))
    raw_muted = audio.get("muted", DEFAULT_MUTED)
    muted = raw_muted if isinstance(raw_muted, bool) else DEFAULT_MUTED
    return AudioSettings(volume=volume, muted=muted)


def write_audio(audio: AudioSettings) -> None:
    """Write audio block to settings.json, preserving other top-level keys."""
    data = _read_settings_dict()
    data["audio"] = {"volume": audio.volume, "muted": audio.muted}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    from album_builder.persistence.atomic_io import atomic_write_text
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))
```

Refactor `read_tracks_folder` to use `_read_settings_dict()` for DRY.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/persistence/test_settings.py -v`
Expected: PASS for all five.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/persistence/settings.py tests/persistence/test_settings.py
git commit -m "feat(persistence): add audio settings (volume, muted) round-trip"
```

---

## Task 2: Player service

**Files:**
- Create: `src/album_builder/services/player.py`
- Create: `tests/services/test_player.py`

The `Player` is a `QObject` wrapping `QMediaPlayer + QAudioOutput`. Domain-shaped API: methods take seconds (float) and 0–100 ints; signals emit seconds (float) and a `PlayerState` enum. The wrapper owns the unit-conversion (Qt deals in milliseconds and 0.0–1.0 floats) and the state-machine normalisation (Qt's `MediaStatus` and `PlaybackState` are two separate enums that we collapse for callers).

Test strategy: pytest-qt with `qtbot` + a 1-second silent-WAV fixture written to `tmp_path`. We avoid network or large fixtures by generating the WAV inline (44.1 kHz, 1 s of zeros — ~88 KB).

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_player.py
"""Tests for album_builder.services.player — Spec 06."""

import struct
import wave
from pathlib import Path

import pytest

from album_builder.services.player import Player, PlayerState


def _write_silent_wav(path: Path, seconds: float = 1.0) -> Path:
    sr = 44100
    n = int(sr * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return path


@pytest.fixture
def silent_wav(tmp_path: Path) -> Path:
    return _write_silent_wav(tmp_path / "silent.wav", seconds=2.0)


# Spec: TC-06-02
def test_volume_int_to_float_mapping(qtbot):
    p = Player()
    qtbot.addWidget(p)  # Player is QObject not QWidget — see step 3 note
    p.set_volume(50)
    assert p.volume() == 50
    # QAudioOutput.volume() exposes 0.0..1.0 internally
    assert abs(p._output.volume() - 0.5) < 0.01


# Spec: TC-06-08
def test_seek_clamps_beyond_duration(silent_wav, qtbot):
    p = Player()
    p.set_source(silent_wav)
    qtbot.waitUntil(lambda: p.duration() > 0, timeout=3000)
    p.seek(999.0)
    # Internal clamp: duration - 1.0
    assert p.position() <= p.duration() - 1.0 + 0.01


# Spec: TC-06-05
def test_missing_source_emits_error(qtbot, tmp_path):
    p = Player()
    errors = []
    p.error.connect(errors.append)
    p.set_source(tmp_path / "does-not-exist.wav")
    p.play()
    qtbot.waitUntil(lambda: errors, timeout=3000)
    assert errors  # at least one error message captured
    assert p.state() == PlayerState.ERROR


# Spec: TC-06-01
def test_set_source_play_reaches_playing(silent_wav, qtbot):
    p = Player()
    states = []
    p.state_changed.connect(states.append)
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(
        lambda: p.state() == PlayerState.PLAYING, timeout=2000,
    )
    assert PlayerState.PLAYING in states


# Spec: TC-06-04
def test_swap_source_mid_play_replaces(silent_wav, qtbot, tmp_path):
    other = _write_silent_wav(tmp_path / "other.wav", seconds=2.0)
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    p.set_source(other)
    p.play()
    qtbot.waitUntil(lambda: p.source() == other, timeout=2000)
    # only one playing state at any moment
    assert p.state() in (PlayerState.PLAYING, PlayerState.STOPPED)


# Spec: TC-06-09
def test_stop_after_play_is_synchronous(silent_wav, qtbot):
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    p.stop()
    assert p.state() == PlayerState.STOPPED


# Spec: TC-06-16
def test_end_of_track_does_not_auto_advance(silent_wav, qtbot):
    """v1 behaviour: end-of-track stops, no next-track autoload."""
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    qtbot.waitUntil(lambda: p.state() == PlayerState.STOPPED, timeout=5000)
    # Source unchanged after end-of-track.
    assert p.source() == silent_wav


def test_set_muted_round_trip(qtbot):
    p = Player()
    assert p.muted() is False
    p.set_muted(True)
    assert p.muted() is True
    assert p._output.isMuted() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/services/test_player.py -v`
Expected: ImportError on `Player`.

- [ ] **Step 3: Implement `Player`**

```python
# src/album_builder/services/player.py
"""Audio playback service — Spec 06.

Wraps QMediaPlayer + QAudioOutput. Emits domain-shaped signals (seconds as
float, normalised PlayerState enum) so widgets don't have to touch Qt's
two separate playback-state enums or the millisecond unit.

Player is a QObject, not a QWidget. pytest-qt's `qtbot.addWidget` accepts
QObject subclasses despite the name; if a future test framework rejects
that, switch to `qtbot.add_widget` explicit cleanup or call deleteLater
in test teardown.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

logger = logging.getLogger(__name__)


class PlayerState(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    ERROR = auto()


class Player(QObject):
    """Single-instance audio playback coordinator."""

    # Spec 06 §Outputs.
    # PyQt requires `pyqtSignal(...)` at class scope; `# Type: x(t: float)`
    # comments document the payload for IDEs and code review (matches the
    # AlbumStore docstring convention from Phase 2).
    position_changed = pyqtSignal(float)     # seconds
    duration_changed = pyqtSignal(float)     # seconds
    state_changed = pyqtSignal(object)       # PlayerState
    error = pyqtSignal(str)                  # human-readable message
    buffering_changed = pyqtSignal(bool)     # True when MediaStatus.BufferingMedia

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._source: Path | None = None
        self._duration_seconds = 0.0
        self._state = PlayerState.STOPPED
        # Track whether we've seen the first decode error this session so
        # the codec-missing dialog only surfaces once (Spec 06 TC-06-07).
        self._codec_dialog_shown = False

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

    # ---- Public API -------------------------------------------------

    def set_source(self, path: Path) -> None:
        self._source = Path(path)
        # Stop before swap so the previous track's playbackState transitions
        # cleanly to Stopped instead of fighting the loader.
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(self._source)))

    def source(self) -> Path | None:
        return self._source

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if self._state == PlayerState.PLAYING:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, seconds: float) -> None:
        if self._duration_seconds > 0:
            seconds = min(seconds, self._duration_seconds - 1.0)
        seconds = max(0.0, seconds)
        self._player.setPosition(int(seconds * 1000))

    def position(self) -> float:
        return self._player.position() / 1000.0

    def duration(self) -> float:
        return self._duration_seconds

    def state(self) -> PlayerState:
        return self._state

    def set_volume(self, vol: int) -> None:
        v = max(0, min(100, vol))
        self._output.setVolume(v / 100.0)

    def volume(self) -> int:
        return round(self._output.volume() * 100)

    def set_muted(self, m: bool) -> None:
        self._output.setMuted(bool(m))

    def muted(self) -> bool:
        return self._output.isMuted()

    def codec_dialog_shown(self) -> bool:
        return self._codec_dialog_shown

    def mark_codec_dialog_shown(self) -> None:
        self._codec_dialog_shown = True

    # ---- Qt signal handlers -----------------------------------------

    def _on_position_changed(self, ms: int) -> None:
        self.position_changed.emit(ms / 1000.0)

    def _on_duration_changed(self, ms: int) -> None:
        self._duration_seconds = ms / 1000.0
        self.duration_changed.emit(self._duration_seconds)

    def _on_playback_state(self, qstate) -> None:
        # Map Qt's PlaybackState -> our PlayerState. Don't override an ERROR
        # state with a STOPPED transition that follows naturally from the
        # error path; the controller is the only place that clears errors
        # (by calling set_source again).
        prior = self._state
        match qstate:
            case QMediaPlayer.PlaybackState.PlayingState:
                self._state = PlayerState.PLAYING
            case QMediaPlayer.PlaybackState.PausedState:
                self._state = PlayerState.PAUSED
            case QMediaPlayer.PlaybackState.StoppedState:
                if prior != PlayerState.ERROR:
                    self._state = PlayerState.STOPPED
        if self._state != prior:
            self.state_changed.emit(self._state)

    def _on_media_status(self, status) -> None:
        is_buffering = status == QMediaPlayer.MediaStatus.BufferingMedia
        self.buffering_changed.emit(is_buffering)

    def _on_error(self, error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        prior = self._state
        self._state = PlayerState.ERROR
        msg = message or str(error)
        logger.warning("Player error: %s (%s)", msg, error)
        self.error.emit(msg)
        if self._state != prior:
            self.state_changed.emit(self._state)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/services/test_player.py -v`
Expected: PASS for all eight (or skip on systems without GStreamer plugins; see step 5).

- [ ] **Step 5: Add codec-availability skip marker**

If tests fail on `set_source_play_reaches_playing` because the CI runner lacks GStreamer plugins, gate the integration tests:

```python
@pytest.fixture
def has_audio_decoder(silent_wav, qtbot):
    p = Player()
    errors = []
    p.error.connect(errors.append)
    p.set_source(silent_wav)
    p.play()
    qtbot.wait(500)
    if errors:
        pytest.skip("GStreamer audio decoder unavailable on this host")
```

Apply the fixture to the play-state tests; the volume/seek/mute round-trip tests don't need real decoding and stay unconditional.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/services/player.py tests/services/test_player.py
git commit -m "feat(services): add Player (QMediaPlayer wrapper) — Spec 06"
```

---

## Task 3: TransportBar widget

**Files:**
- Create: `src/album_builder/ui/transport_bar.py`
- Create: `tests/ui/test_transport_bar.py`

The transport bar is a horizontal strip with: large play/pause button (toggle glyph), current-time label `m:ss`, scrubber (seeks to second-granularity), total-duration label `m:ss`, mute button, volume slider (0–100). Buffering indicator is a small label hidden by default.

Subscribes to `Player` signals; emits no domain signals of its own — the buttons call `player.play()` / `player.pause()` directly. The widget is dumb-on-purpose: it reflects player state, the player is the source of truth.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_transport_bar.py
import struct
import wave
from pathlib import Path

import pytest

from album_builder.services.player import Player, PlayerState
from album_builder.ui.transport_bar import TransportBar


def _silent_wav(path: Path) -> Path:
    sr = 44100
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(struct.pack(f"<{sr*2}h", *([0] * sr * 2)))
    return path


@pytest.fixture
def player_and_bar(qtbot, tmp_path: Path):
    p = Player()
    b = TransportBar(p)
    qtbot.addWidget(b)
    return p, b


def test_play_button_glyph_reflects_state(player_and_bar, qtbot, tmp_path):
    p, b = player_and_bar
    p.set_source(_silent_wav(tmp_path / "x.wav"))
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    # Once playing, the button shows pause glyph (▶ becomes ⏸).
    from album_builder.ui.theme import Glyphs
    assert b.btn_play.text() == Glyphs.PAUSE


def test_initial_state_shows_play_glyph(player_and_bar):
    _, b = player_and_bar
    from album_builder.ui.theme import Glyphs
    assert b.btn_play.text() == Glyphs.PLAY


def test_scrubber_updates_on_position_change(player_and_bar, qtbot, tmp_path):
    p, b = player_and_bar
    p.set_source(_silent_wav(tmp_path / "x.wav"))
    p.play()
    qtbot.waitUntil(lambda: b.scrubber.maximum() > 0, timeout=2000)
    # scrubber max == duration in seconds (rounded)
    assert b.scrubber.maximum() == round(p.duration())


def test_buffering_label_hidden_by_default(player_and_bar):
    _, b = player_and_bar
    assert not b.buffering_label.isVisible()


# Spec: TC-06-14
def test_buffering_label_shown_on_buffering_signal(player_and_bar):
    _, b = player_and_bar
    b.show()
    from album_builder.services.player import Player as _P
    # Drive the signal directly — pytest-qt can't easily induce real
    # BufferingMedia status without a network source.
    b._on_buffering_changed(True)
    assert b.buffering_label.isVisible()
    b._on_buffering_changed(False)
    assert not b.buffering_label.isVisible()


def test_volume_slider_writes_to_player(player_and_bar):
    p, b = player_and_bar
    b.volume_slider.setValue(40)
    assert p.volume() == 40


def test_mute_button_toggles_player(player_and_bar):
    p, b = player_and_bar
    assert p.muted() is False
    b.btn_mute.click()
    assert p.muted() is True
    b.btn_mute.click()
    assert p.muted() is False


def test_time_label_format(player_and_bar):
    _, b = player_and_bar
    assert b._format_time(0) == "0:00"
    assert b._format_time(65) == "1:05"
    assert b._format_time(3600) == "1:00:00"  # hour boundary


def test_play_button_click_calls_play(player_and_bar, tmp_path):
    p, b = player_and_bar
    p.set_source(_silent_wav(tmp_path / "x.wav"))
    b.btn_play.click()
    # state is async, but the call landed
    # (we'll also trust TC-06-01 in test_player.py)
    from PyQt6.QtMultimedia import QMediaPlayer
    assert p._player.playbackState() in (
        QMediaPlayer.PlaybackState.PlayingState,
        QMediaPlayer.PlaybackState.StoppedState,  # may not have transitioned yet
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/ui/test_transport_bar.py -v`
Expected: ImportError on `TransportBar`.

- [ ] **Step 3: Implement TransportBar**

```python
# src/album_builder/ui/transport_bar.py
"""Transport bar — Spec 06 §user-visible behavior, transport bar elements."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from album_builder.services.player import Player, PlayerState
from album_builder.ui.theme import Glyphs


class TransportBar(QWidget):
    def __init__(self, player: Player, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self.setObjectName("TransportBar")

        self.btn_play = QPushButton(Glyphs.PLAY, objectName="TransportPlay")
        self.btn_play.setAccessibleName("Play")
        self.btn_play.setFixedWidth(48)
        self.btn_play.clicked.connect(self._on_play_clicked)

        self.lbl_current = QLabel("0:00", objectName="TransportTime")
        self.lbl_current.setAccessibleName("Current playback time")

        self.scrubber = QSlider(Qt.Orientation.Horizontal, objectName="TransportScrubber")
        self.scrubber.setRange(0, 0)
        self.scrubber.setAccessibleName("Playback position")
        self.scrubber.sliderMoved.connect(self._on_scrub)

        self.lbl_duration = QLabel("0:00", objectName="TransportTime")
        self.lbl_duration.setAccessibleName("Track duration")

        self.btn_mute = QPushButton(Glyphs.UNMUTE, objectName="TransportMute")
        self.btn_mute.setAccessibleName("Mute")
        self.btn_mute.setFixedWidth(36)
        self.btn_mute.clicked.connect(self._on_mute_clicked)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal, objectName="TransportVolume")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(player.volume())
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.setAccessibleName("Volume")
        self.volume_slider.valueChanged.connect(player.set_volume)

        self.buffering_label = QLabel("Buffering...", objectName="TransportBuffering")
        self.buffering_label.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.buffering_label)
        layout.addWidget(self.lbl_current)
        layout.addWidget(self.scrubber, stretch=1)
        layout.addWidget(self.lbl_duration)
        layout.addSpacing(12)
        layout.addWidget(self.btn_mute)
        layout.addWidget(self.volume_slider)

        # Subscribe to player.
        player.position_changed.connect(self._on_position_changed)
        player.duration_changed.connect(self._on_duration_changed)
        player.state_changed.connect(self._on_state_changed)
        player.buffering_changed.connect(self._on_buffering_changed)

    # ---- Slots ------------------------------------------------------

    def _on_play_clicked(self) -> None:
        self._player.toggle()

    def _on_mute_clicked(self) -> None:
        self._player.set_muted(not self._player.muted())
        self.btn_mute.setText(Glyphs.MUTE if self._player.muted() else Glyphs.UNMUTE)
        self.btn_mute.setAccessibleName("Unmute" if self._player.muted() else "Mute")

    def _on_scrub(self, value: int) -> None:
        self._player.seek(float(value))

    def _on_position_changed(self, seconds: float) -> None:
        # Don't fight the user mid-drag.
        if not self.scrubber.isSliderDown():
            self.scrubber.setValue(int(seconds))
        self.lbl_current.setText(self._format_time(seconds))

    def _on_duration_changed(self, seconds: float) -> None:
        self.scrubber.setRange(0, int(round(seconds)))
        self.lbl_duration.setText(self._format_time(seconds))

    def _on_state_changed(self, state) -> None:
        if state == PlayerState.PLAYING:
            self.btn_play.setText(Glyphs.PAUSE)
            self.btn_play.setAccessibleName("Pause")
        else:
            self.btn_play.setText(Glyphs.PLAY)
            self.btn_play.setAccessibleName("Play")

    def _on_buffering_changed(self, buffering: bool) -> None:
        self.buffering_label.setVisible(buffering)

    @staticmethod
    def _format_time(seconds: float) -> str:
        # Spec 06 §display: m:ss (no leading zero on minutes); h:mm:ss past
        # one hour. Classic half-up rounding via int(s + 0.5) — same as
        # _format_duration in library_pane (Tier 3 fix).
        s = int(seconds + 0.5)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ui/test_transport_bar.py -v`
Expected: 9/9 PASS (volume + buffering + state-glyph all green; integration tests skip on hosts without decoder).

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/transport_bar.py tests/ui/test_transport_bar.py
git commit -m "feat(ui): add TransportBar widget — play/pause/scrubber/volume"
```

---

## Task 4: NowPlayingPane widget

**Files:**
- Create: `src/album_builder/ui/now_playing_pane.py`
- Create: `tests/ui/test_now_playing_pane.py`

The right pane composition. Top: cover image (320 px wide; falls back to a placeholder block when track has no cover). Below: metadata block (title, album, artist, composer, comment — `QLabel`s, word-wrapped). Below: lyrics-panel placeholder `QFrame#LyricsPlaceholder` (Phase 3B will replace it). Bottom: `TransportBar`.

`set_track(Track | None)` updates everything. `Track | None` because at startup with no last-played track, the pane shows a "(nothing loaded)" placeholder — same convention as Phase 1's empty library.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_now_playing_pane.py
from pathlib import Path

import pytest

from album_builder.domain.track import Track
from album_builder.services.player import Player
from album_builder.ui.now_playing_pane import NowPlayingPane


@pytest.fixture
def pane(qtbot):
    player = Player()
    pane = NowPlayingPane(player)
    qtbot.addWidget(pane)
    return pane, player


def test_no_track_shows_placeholder(pane):
    p, _ = pane
    assert p.title_label.text() == ""
    assert p.placeholder_label.isVisible()


def test_set_track_shows_metadata(pane, tmp_path):
    p, _ = pane
    track = Track(
        path=tmp_path / "song.mpeg",
        title="Walking The Line",
        artist="18 Down",
        album_artist="18 Down",
        album="Memoirs of a Sinner",
        composer="A. Smith",
        comment="rough mix",
        lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=240.0, is_missing=False, file_size_bytes=1234,
    )
    p.set_track(track)
    assert p.title_label.text() == "Walking The Line"
    assert "18 Down" in p.artist_label.text()
    assert "Memoirs of a Sinner" in p.album_label.text()
    assert not p.placeholder_label.isVisible()


def test_set_track_none_clears(pane, tmp_path):
    p, _ = pane
    track = Track(
        path=tmp_path / "x.mpeg", title="x", artist="y", album_artist="y",
        album="z", composer=None, comment=None, lyrics_text=None,
        cover_data=None, cover_mime=None, duration_seconds=1.0,
        is_missing=False, file_size_bytes=1,
    )
    p.set_track(track)
    p.set_track(None)
    assert p.title_label.text() == ""
    assert p.placeholder_label.isVisible()


def test_lyrics_placeholder_present(pane):
    """Phase 3B will replace the LyricsPlaceholder QFrame with the real
    lyrics panel. This test pins the contract — the pane reserves space
    for the lyrics panel and exposes it as a child widget."""
    p, _ = pane
    assert p.lyrics_placeholder is not None
    assert p.lyrics_placeholder.objectName() == "LyricsPlaceholder"


def test_transport_bar_present(pane):
    p, _ = pane
    assert p.transport is not None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/ui/test_now_playing_pane.py -v`
Expected: ImportError on `NowPlayingPane`.

- [ ] **Step 3: Implement NowPlayingPane**

```python
# src/album_builder/ui/now_playing_pane.py
"""Right pane — cover + metadata + lyrics-panel placeholder + transport.

Lyrics panel area is a placeholder QFrame#LyricsPlaceholder; Phase 3B
will replace it with the synchronized scrolling lyrics widget.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from album_builder.domain.track import Track
from album_builder.services.player import Player
from album_builder.ui.transport_bar import TransportBar


class NowPlayingPane(QFrame):
    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Now playing", objectName="PaneTitle"))

        self.cover_label = QLabel(objectName="NowPlayingCover")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedHeight(280)
        self.cover_label.setMinimumWidth(280)
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("", objectName="NowPlayingTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.album_label = QLabel("", objectName="NowPlayingMeta")
        self.album_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.album_label)

        self.artist_label = QLabel("", objectName="NowPlayingMeta")
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.artist_label)

        self.composer_label = QLabel("", objectName="NowPlayingMetaSecondary")
        self.composer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.composer_label)

        self.comment_label = QLabel("", objectName="NowPlayingMetaSecondary")
        self.comment_label.setWordWrap(True)
        self.comment_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.comment_label)

        self.placeholder_label = QLabel("(nothing loaded)", objectName="PlaceholderText")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.placeholder_label)

        # Lyrics panel goes here — Phase 3B replaces it.
        self.lyrics_placeholder = QFrame(objectName="LyricsPlaceholder")
        self.lyrics_placeholder.setFixedHeight(120)
        layout.addWidget(self.lyrics_placeholder)

        layout.addStretch(1)

        self.transport = TransportBar(player)
        layout.addWidget(self.transport)

        self.set_track(None)

    def set_track(self, track: Track | None) -> None:
        if track is None:
            self.cover_label.clear()
            self.title_label.setText("")
            self.album_label.setText("")
            self.artist_label.setText("")
            self.composer_label.setText("")
            self.comment_label.setText("")
            self.placeholder_label.setVisible(True)
            return
        self.placeholder_label.setVisible(False)
        self._set_cover(track)
        self.title_label.setText(track.title or "")
        self.album_label.setText(track.album or "")
        self.artist_label.setText(track.artist or "")
        if track.composer:
            self.composer_label.setText(f"composer: {track.composer}")
        else:
            self.composer_label.setText("")
        if track.comment:
            self.comment_label.setText(track.comment)
        else:
            self.comment_label.setText("")

    def _set_cover(self, track: Track) -> None:
        if not track.cover_data:
            self.cover_label.clear()
            self.cover_label.setText("(no cover)")
            return
        pix = QPixmap()
        pix.loadFromData(track.cover_data)
        if pix.isNull():
            self.cover_label.clear()
            self.cover_label.setText("(cover unavailable)")
            return
        scaled = pix.scaledToHeight(
            260, Qt.TransformationMode.SmoothTransformation,
        )
        self.cover_label.setPixmap(scaled)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ui/test_now_playing_pane.py -v`
Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/now_playing_pane.py tests/ui/test_now_playing_pane.py
git commit -m "feat(ui): add NowPlayingPane with cover + metadata + transport"
```

---

## Task 5: Per-row preview-play column

**Files:**
- Modify: `src/album_builder/ui/library_pane.py`
- Modify: `src/album_builder/ui/album_order_pane.py`
- Modify: `tests/ui/test_library_pane.py`
- Modify: `tests/ui/test_album_order_pane.py`

LibraryPane: add a new column 0 (before the existing toggle column) — the play glyph (`▶`) as text-only with hover, click emits `preview_play_requested(Path)`. Width 28 px. Toggle becomes column 1.

AlbumOrderPane: each row has a left-aligned mini-button (`▶` glyph), `setFixedSize(20, 20)`. Click emits `preview_play_requested(Path)`. Drag handle stays where it is.

For LibraryPane, this is a new column in `COLUMNS`; the model's `data()` returns `Glyphs.PLAY` for `Qt.ItemDataRole.DisplayRole` on the new column, the click handler routes via `pane._on_cell_clicked`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_library_pane.py — append
def test_library_pane_emits_preview_play_request(populated_pane, qtbot) -> None:
    pane, lib = populated_pane
    captured = []
    pane.preview_play_requested.connect(captured.append)
    # Find the play column index
    from album_builder.ui.library_pane import COLUMNS
    play_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_play")
    qtbot.mouseClick(
        pane.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=pane.table.visualRect(pane.proxy.index(0, play_col)).center(),
    )
    assert captured
    assert isinstance(captured[0], Path)
```

```python
# tests/ui/test_album_order_pane.py — append
def test_album_order_pane_emits_preview_play(qtbot, populated_pane, ...):
    """Click a row's preview-play button → pane emits preview_play_requested
    with the row's track Path. (Pane already exists from Phase 2; we add the
    button per row in this task.)"""
    # uses the existing populated_pane fixture from the file
    pane, _album, lib = populated_pane
    captured = []
    pane.preview_play_requested.connect(captured.append)
    btn = pane._play_button_at_row(0)
    btn.click()
    assert captured == [lib.tracks[0].path]  # ordering depends on fixture
```

(Adjust the second test to match the fixture shape in the existing file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_library_pane.py tests/ui/test_album_order_pane.py -v`
Expected: AttributeError on `preview_play_requested`.

- [ ] **Step 3: Implement on LibraryPane**

In `library_pane.py`:

1. Add new tuple `("_play", "_play", 28)` as `COLUMNS[0]`. Shift toggle to column 1; titles to column 2; etc.
2. In `TrackTableModel.data()`, for `_play` column return `Glyphs.PLAY` for `DisplayRole`, `"Preview-play"` for `AccessibleTextRole`. Sort role: tuple `(False, casefolded-title)` so the column is sortable but doesn't do anything useful.
3. Add `pyqtSignal(object)` named `preview_play_requested` on `LibraryPane`.
4. In the existing cell-click handler, on `_play` column, emit the signal with `track.path`.

In `album_order_pane.py`:

1. Add `pyqtSignal(object)` named `preview_play_requested` on the pane.
2. In `_render_album` (or the per-row builder), wrap each `QListWidgetItem` text in a `QWidget` with horizontal layout: `QPushButton(Glyphs.PLAY)` + the existing label/handle. `QListWidget.setItemWidget` slots the widget in.
3. The play button captures the row's track path; `clicked` lambda emits `preview_play_requested`.

(Use existing renderer plumbing — Phase 2's `AlbumOrderPane` already supports custom row widgets via `setItemWidget`; keep changes additive.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ui/test_library_pane.py tests/ui/test_album_order_pane.py -v`
Expected: PASS, plus ALL existing tests still pass (the column shift breaks anything indexing by column number).

If a test references `COLUMNS[0]` expecting toggle, fix that test to use `next(i for i,c in enumerate(COLUMNS) if c[1] == "_toggle")` — name-based lookup is the long-term-stable form.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/library_pane.py src/album_builder/ui/album_order_pane.py \
        tests/ui/test_library_pane.py tests/ui/test_album_order_pane.py
git commit -m "feat(ui): add preview-play column on library + order panes (TC-06-15)"
```

---

## Task 6: Keyboard shortcuts (closes Theme E)

**Files:**
- Modify: `src/album_builder/ui/main_window.py`
- Create: `tests/ui/test_keyboard_shortcuts.py`
- Modify: `docs/specs/00-app-overview.md` (flip "Wired?" column)

All Spec 00 keyboard shortcuts wired. Transport shortcuts (Space / Left / Right / Shift+Left/Right / M) suppress when focus is in a `QLineEdit` / `QTextEdit` / `QSpinBox` so a user typing in the album-name editor or target-counter doesn't accidentally play music.

Implementation: an `eventFilter` on `QApplication` that catches `QKeyEvent` before delegation. The MainWindow installs the filter at construction and removes it at destruction.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_keyboard_shortcuts.py
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest

# Use the existing main_window fixture if there is one; otherwise build
# minimal MainWindow scaffolding inline.


def test_space_toggles_player(qtbot, fresh_main_window):
    """Spec 00 + TC-06-12: Space toggles play/pause when not in a text field."""
    mw = fresh_main_window
    assert mw._player.state().name == "STOPPED"
    QTest.keyClick(mw, Qt.Key.Key_Space)
    # State will only transition if a track is loaded — we test the dispatch.
    # Use a spy: the player's toggle() should fire.
    # Easier: pre-load a silent fixture and assert state cycles.
    ...


def test_space_suppressed_in_text_field(qtbot, fresh_main_window):
    """When focus is in a QLineEdit, Space inserts a space, not toggles play."""
    mw = fresh_main_window
    line = mw.top_bar.name_editor  # exists in TopBar
    line.setFocus()
    line.setText("hello")
    QTest.keyClick(line, Qt.Key.Key_Space)
    assert "hello " in line.text() or line.text() == "hello "  # space inserted


def test_left_arrow_seeks_minus_5(qtbot, fresh_main_window_playing):
    mw = fresh_main_window_playing  # fixture pre-loads + starts playback
    pos_before = mw._player.position()
    # Force a known position first
    mw._player.seek(10.0)
    qtbot.wait(100)
    QTest.keyClick(mw, Qt.Key.Key_Left)
    qtbot.wait(100)
    assert mw._player.position() < 10.0


def test_shift_left_seeks_minus_30(qtbot, fresh_main_window_playing):
    mw = fresh_main_window_playing
    mw._player.seek(60.0)
    qtbot.wait(100)
    QTest.keyClick(mw, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    qtbot.wait(100)
    pos = mw._player.position()
    assert pos <= 60.0 - 30.0 + 0.5  # approx within tick precision


def test_m_toggles_mute(qtbot, fresh_main_window):
    mw = fresh_main_window
    assert mw._player.muted() is False
    QTest.keyClick(mw, Qt.Key.Key_M)
    assert mw._player.muted() is True
    QTest.keyClick(mw, Qt.Key.Key_M)
    assert mw._player.muted() is False


def test_ctrl_n_triggers_new_album(qtbot, fresh_main_window, monkeypatch):
    mw = fresh_main_window
    called = []
    monkeypatch.setattr(mw, "_on_new_album", lambda: called.append(True))
    QTest.keyClick(mw, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
    assert called == [True]


def test_ctrl_q_closes_window(qtbot, fresh_main_window):
    mw = fresh_main_window
    QTest.keyClick(mw, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(50)
    assert not mw.isVisible() or mw.isHidden()


def test_f1_shows_help_dialog(qtbot, fresh_main_window, monkeypatch):
    mw = fresh_main_window
    called = []
    monkeypatch.setattr(mw, "_show_help", lambda: called.append(True))
    QTest.keyClick(mw, Qt.Key.Key_F1)
    assert called == [True]
```

(Define `fresh_main_window` and `fresh_main_window_playing` fixtures in `tests/ui/conftest.py` if not already present; reuse the test scaffolding from Phase 2's `test_main_window.py` if available.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_keyboard_shortcuts.py -v`
Expected: AttributeError on missing `_show_help` etc.

- [ ] **Step 3: Wire shortcuts in MainWindow**

Add at end of `MainWindow.__init__`:

```python
from PyQt6.QtGui import QShortcut, QKeySequence

QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_album)
QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
QShortcut(QKeySequence("F1"), self, activated=self._show_help)

# Transport shortcuts — context-suppressed (see _key_in_text_field).
QShortcut(QKeySequence("Space"), self, activated=self._space_pressed)
QShortcut(QKeySequence("Left"), self, activated=lambda: self._seek_relative(-5))
QShortcut(QKeySequence("Right"), self, activated=lambda: self._seek_relative(5))
QShortcut(QKeySequence("Shift+Left"), self, activated=lambda: self._seek_relative(-30))
QShortcut(QKeySequence("Shift+Right"), self, activated=lambda: self._seek_relative(30))
QShortcut(QKeySequence("M"), self, activated=self._toggle_mute)
```

```python
def _key_in_text_field(self) -> bool:
    from PyQt6.QtWidgets import QApplication, QLineEdit, QSpinBox, QTextEdit
    w = QApplication.focusWidget()
    return isinstance(w, (QLineEdit, QSpinBox, QTextEdit))

def _space_pressed(self) -> None:
    if self._key_in_text_field():
        return
    self._player.toggle()

def _seek_relative(self, delta: float) -> None:
    if self._key_in_text_field():
        return
    self._player.seek(self._player.position() + delta)

def _toggle_mute(self) -> None:
    if self._key_in_text_field():
        return
    self._player.set_muted(not self._player.muted())

def _show_help(self) -> None:
    QMessageBox.information(
        self,
        "Album Builder — Keyboard shortcuts",
        "Ctrl+N — New album\n"
        "Ctrl+Q — Quit\n"
        "F1 — This help\n"
        "Space — Play / pause\n"
        "Left / Right — Seek -5 s / +5 s\n"
        "Shift+Left / Right — Seek -30 s / +30 s\n"
        "M — Mute / unmute\n\n"
        "Transport shortcuts are suppressed while typing in a text field.",
    )
```

(Note: `QShortcut` does not bypass focused-widget event handlers for keys the widget cares about — `QLineEdit` consumes Space before the shortcut fires for Qt's default ShortcutContext. If Space still toggles in QLineEdit during testing, switch to `Qt.ShortcutContext.ApplicationShortcut` and rely on `_key_in_text_field` for suppression.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ui/test_keyboard_shortcuts.py -v`
Expected: PASS for all eight (or skip the playback-dependent ones on hosts without GStreamer).

- [ ] **Step 5: Update Spec 00 keyboard table "Wired?" column**

Flip every row from "Phase 3" to "✓ Phase 3A" except the explicit Phase 3B holdouts (none — all keyboard shortcuts ship in 3A).

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/main_window.py tests/ui/test_keyboard_shortcuts.py \
        docs/specs/00-app-overview.md
git commit -m "feat(ui): wire all Spec 00 keyboard shortcuts (closes Theme E)"
```

---

## Task 7: Toast widget for transient errors

**Files:**
- Create: `src/album_builder/ui/toast.py`
- Create: `tests/ui/test_toast.py`

A `QFrame` subclass that overlays the bottom of the parent window for ~4 s, then auto-dismisses. Single-line message + close button. Multiple toasts stack; oldest at the bottom (or overwrites — choose simplest).

For Phase 3A scope: simplest implementation is overwrite — only one toast visible at a time, new toast replaces existing. Stacking is YAGNI.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_toast.py
from album_builder.ui.toast import Toast


def test_toast_shows_message(qtbot):
    t = Toast()
    qtbot.addWidget(t)
    t.show_message("Track file not found: /a/b.mp3")
    assert t.isVisible()
    assert "Track file not found" in t.message_label.text()


def test_toast_auto_dismisses(qtbot):
    t = Toast(auto_dismiss_ms=200)
    qtbot.addWidget(t)
    t.show_message("test")
    assert t.isVisible()
    qtbot.wait(400)
    assert not t.isVisible()


def test_toast_overwrites_previous(qtbot):
    t = Toast()
    qtbot.addWidget(t)
    t.show_message("first")
    t.show_message("second")
    assert "second" in t.message_label.text()


def test_toast_close_button_dismisses(qtbot):
    t = Toast()
    qtbot.addWidget(t)
    t.show_message("test")
    t.btn_close.click()
    assert not t.isVisible()
```

- [ ] **Step 2: Run to verify failure**

`.venv/bin/pytest tests/ui/test_toast.py -v`

- [ ] **Step 3: Implement Toast**

```python
# src/album_builder/ui/toast.py
"""Transient error notice — Spec 06 §Errors & edge cases."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class Toast(QFrame):
    DEFAULT_AUTO_DISMISS_MS = 4000

    def __init__(self, parent=None, auto_dismiss_ms: int = DEFAULT_AUTO_DISMISS_MS):
        super().__init__(parent)
        self.setObjectName("Toast")
        self._auto_dismiss_ms = auto_dismiss_ms
        self.message_label = QLabel("", objectName="ToastMessage")
        self.message_label.setWordWrap(True)
        self.btn_close = QPushButton("x", objectName="ToastClose")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.clicked.connect(self.hide)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self.message_label, stretch=1)
        layout.addWidget(self.btn_close)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, msg: str) -> None:
        self.message_label.setText(msg)
        self.show()
        self.raise_()
        self._timer.start(self._auto_dismiss_ms)
```

- [ ] **Step 4: Run tests to verify they pass**

`.venv/bin/pytest tests/ui/test_toast.py -v`
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/toast.py tests/ui/test_toast.py
git commit -m "feat(ui): add Toast widget for transient errors"
```

---

## Task 8: MainWindow integration

**Files:**
- Modify: `src/album_builder/ui/main_window.py`
- Create or modify: `tests/ui/test_main_window.py`

`MainWindow` owns the `Player`. Replaces `_build_placeholder_pane("Now playing")` with the real `NowPlayingPane`. Wires:

- Library + order pane `preview_play_requested` → `_on_preview_play(path)` → load library track + `set_source` + `play` + `set_track` on now-playing pane + write `state.last_played_track_path` (debounced).
- `Player.error` → toast + (one-shot) codec dialog.
- `closeEvent` → `Player.stop()` (synchronous).
- Startup: load `audio` settings → `Player.set_volume / set_muted`. Read `state.last_played_track_path` → if track still in library, `set_source` (paused at zero) + `set_track` on pane.

Codec-missing detection heuristic: when the first error message contains "decoder" / "codec" / "GStreamer" / "plugin", show the one-shot dialog. Track via `Player.codec_dialog_shown` / `mark_codec_dialog_shown` (Phase 3A pinned API).

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_main_window.py — append (or create stub if absent)
from album_builder.services.player import Player


def test_main_window_owns_player(fresh_main_window):
    mw = fresh_main_window
    assert hasattr(mw, "_player")
    assert isinstance(mw._player, Player)


def test_now_playing_pane_replaces_placeholder(fresh_main_window):
    mw = fresh_main_window
    from album_builder.ui.now_playing_pane import NowPlayingPane
    assert isinstance(mw.now_playing_pane, NowPlayingPane)


def test_preview_play_loads_track_into_player(fresh_main_window, qtbot):
    mw = fresh_main_window
    track_paths = [t.path for t in mw._library_watcher.library().tracks]
    assert track_paths
    mw._on_preview_play(track_paths[0])
    qtbot.wait(100)
    assert mw._player.source() == track_paths[0]


def test_close_event_stops_player(fresh_main_window_playing, qtbot):
    mw = fresh_main_window_playing
    from album_builder.services.player import PlayerState
    qtbot.waitUntil(lambda: mw._player.state() == PlayerState.PLAYING, timeout=2000)
    mw.close()
    assert mw._player.state() == PlayerState.STOPPED


def test_state_last_played_round_trip(tmp_path, monkeypatch):
    # Build a fresh state.json with a known last_played_track_path,
    # construct MainWindow, assert the player loaded that source paused.
    ...  # full body matches the Phase 2 main_window startup-restore tests


def test_codec_error_shows_one_shot_dialog(fresh_main_window, qtbot, monkeypatch):
    mw = fresh_main_window
    calls = []
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QMessageBox.warning",
        lambda *a, **k: calls.append(a[2]) or 0,
    )
    mw._on_player_error("Decoder unavailable: gstreamer-plugins-good missing")
    mw._on_player_error("Decoder unavailable: gstreamer-plugins-good missing")
    assert len(calls) == 1  # one-shot
```

- [ ] **Step 2: Run to verify failure**

`.venv/bin/pytest tests/ui/test_main_window.py -v`
Expected: failures on missing `_player` and `_on_preview_play`.

- [ ] **Step 3: Wire MainWindow**

In `MainWindow.__init__`:

```python
from album_builder.persistence.settings import read_audio
from album_builder.services.player import Player
from album_builder.ui.now_playing_pane import NowPlayingPane
from album_builder.ui.toast import Toast

# After existing widget construction:
self._player = Player(self)
audio_settings = read_audio()
self._player.set_volume(audio_settings.volume)
self._player.set_muted(audio_settings.muted)

self.now_playing_pane = NowPlayingPane(self._player)
# Replace the placeholder slot in the splitter — substitute call.
self.splitter.replaceWidget(2, self.now_playing_pane)

self._toast = Toast(self)
self._toast.setParent(self)
# Position the toast manually in resizeEvent.

# Wire preview-play
self.library_pane.preview_play_requested.connect(self._on_preview_play)
self.album_order_pane.preview_play_requested.connect(self._on_preview_play)

# Wire player errors
self._player.error.connect(self._on_player_error)

# Restore last-played track (paused at zero per Spec 06 TC-06-11).
if state.last_played_track_path:
    last = Path(state.last_played_track_path)
    track = next(
        (t for t in library_watcher.library().tracks if t.path == last), None,
    )
    if track is not None:
        self._player.set_source(track.path)
        self.now_playing_pane.set_track(track)
```

Add methods:

```python
def _on_preview_play(self, path: Path) -> None:
    track = next(
        (t for t in self._library_watcher.library().tracks if t.path == path),
        None,
    )
    if track is None:
        self._toast.show_message(f"Track not in library: {path}")
        return
    self._player.set_source(path)
    self._player.play()
    self.now_playing_pane.set_track(track)
    self._state.last_played_track_path = path
    self._state_save_timer.start()

def _on_player_error(self, msg: str) -> None:
    self._toast.show_message(msg)
    if self._looks_like_codec_error(msg) and not self._player.codec_dialog_shown():
        QMessageBox.warning(
            self,
            "Audio codecs unavailable",
            "Audio playback requires GStreamer plugins.\n"
            "On openSUSE: install gstreamer-plugins-good and "
            "gstreamer-plugins-libav via:\n\n"
            "    sudo zypper install gstreamer-plugins-good "
            "gstreamer-plugins-libav\n\n"
            "Then restart the app.",
        )
        self._player.mark_codec_dialog_shown()

@staticmethod
def _looks_like_codec_error(msg: str) -> bool:
    m = msg.lower()
    return any(s in m for s in ("decoder", "codec", "gstreamer", "plugin"))
```

In `closeEvent`, before `super().closeEvent(e)`, add:

```python
try:
    self._player.stop()
except Exception:
    logger.exception("Player.stop() failed during closeEvent")
# Persist audio settings.
try:
    from album_builder.persistence.settings import AudioSettings, write_audio
    write_audio(AudioSettings(
        volume=self._player.volume(), muted=self._player.muted(),
    ))
except Exception:
    logger.exception("write_audio() failed during closeEvent")
```

In `resizeEvent`, position the toast at bottom-centre:

```python
self._toast.setGeometry(
    20, self.height() - 60, self.width() - 40, 40,
)
```

Remove `_build_placeholder_pane` since it's no longer used.

- [ ] **Step 4: Run tests + full suite**

`.venv/bin/pytest tests/ -v` — expect all green.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat(ui): wire Player + NowPlayingPane + last-played restore"
```

---

## Task 9: QSS for transport + toast + lyrics-placeholder

**Files:**
- Modify: `src/album_builder/ui/theme.py`

Append to `qt_stylesheet`:

```python
QFrame#Toast {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.danger};
    border-radius: 8px;
    color: {p.text_primary};
}}
QPushButton#ToastClose {{
    background: transparent;
    border: none;
    color: {p.text_secondary};
}}
QPushButton#ToastClose:hover {{
    color: {p.text_primary};
}}
QFrame#LyricsPlaceholder {{
    background-color: {p.bg_pane};
    border: 1px dashed {p.border_strong};
    border-radius: 6px;
}}
QPushButton#TransportPlay {{
    font-size: 16pt;
    padding: 6px;
}}
QLabel#TransportTime {{
    color: {p.text_secondary};
    font-variant-numeric: tabular-nums;
    font-family: "JetBrains Mono", "Fira Code", monospace;
}}
QLabel#TransportBuffering {{
    color: {p.accent_warm};
    font-style: italic;
}}
QLabel#NowPlayingTitle {{
    font-size: 14pt;
    font-weight: 600;
    color: {p.text_primary};
    padding: 8px 4px 4px 4px;
}}
QLabel#NowPlayingMeta {{
    color: {p.text_secondary};
}}
QLabel#NowPlayingMetaSecondary {{
    color: {p.text_tertiary};
    font-size: 9pt;
}}
QLabel#NowPlayingCover {{
    background-color: {p.bg_pane};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
```

- [ ] **Step 1: Apply, run full suite + smoke**

`.venv/bin/pytest -q` — should still be all green.

`.venv/bin/python -m album_builder` — manual smoke: confirm no QSS warnings on stderr.

- [ ] **Step 2: Commit**

```bash
git add src/album_builder/ui/theme.py
git commit -m "style(ui): add QSS for transport, toast, lyrics placeholder"
```

---

## Task 10: Full suite + ruff verification

- [ ] **Step 1: Run full pytest**

```bash
.venv/bin/pytest -q
```

Expected: 195 (Phase 2 baseline) + ~30 new tests = ~225+ passing.

- [ ] **Step 2: Run ruff**

```bash
.venv/bin/ruff check src/ tests/
```

Expected: 0 findings.

- [ ] **Step 3: Manual smoke**

```bash
.venv/bin/python -m album_builder
```

Validate:
1. Window opens; right pane shows now-playing with `(nothing loaded)` until something plays.
2. Click a `▶` on a library row; track loads, plays, transport bar updates.
3. Drag scrubber; seek lands.
4. Volume slider changes audio level; mute button toggles.
5. Space toggles play/pause when window has focus; typing in album-name field with Space inserts a space (no toggle).
6. Quit: app exits cleanly (no orphan QMediaPlayer in `ps` or sound). Re-launch: last-played track is loaded paused at zero. Volume + mute restored from settings.json.
7. Click a non-existent path (rename a track on disk while app is open + click play): toast appears with "Track file not found: ...".

- [ ] **Step 4: Stage all changes for the release commit**

(See Task 11.)

---

## Task 11: Release v0.3.0

- [ ] **Step 1: Bump version**

`src/album_builder/version.py`: `__version__ = "0.3.0"`
`pyproject.toml`: `version = "0.3.0"`

- [ ] **Step 2: Update ROADMAP**

Add a v0.3.0 block above v0.2.2:

```markdown
## ✅ v0.3.0 — Phase 3A: Audio Playback (2026-04-28)

QMediaPlayer integration with transport bar, per-row preview-play, all
Spec 00 keyboard shortcuts wired (closes indie-review Theme E), volume +
mute persistence via settings.json, last-played track restoration via
state.json. Lyrics alignment (Spec 07) deferred to v0.4.0 — placeholder
QFrame in NowPlayingPane reserves the panel space.

Tasks 1–11 from `docs/plans/2026-04-28-phase-3a-playback.md` shipped:

- **Persistence:** `audio.{volume, muted}` round-trip via
  `read_audio` / `write_audio`; `_read_settings_dict` extracted as
  shared malformed-JSON guard.
- **Services:** `Player` (QMediaPlayer + QAudioOutput wrapper) emits
  domain-shaped signals (`position_changed(seconds)`,
  `duration_changed(seconds)`, `state_changed(PlayerState)`,
  `error(str)`, `buffering_changed(bool)`).
- **UI widgets:** `TransportBar` (play/pause + scrubber + volume +
  buffering indicator); `NowPlayingPane` (cover + metadata +
  transport + lyrics placeholder); `Toast` (transient bottom-of-window
  error notice with auto-dismiss).
- **UI extensions:** preview-play column on `LibraryPane` +
  `AlbumOrderPane`; column-name lookup replaces magic indices in tests.
- **MainWindow integration:** Player owned; preview-play wired on both
  panes; last-played track restored paused at zero; closeEvent stops
  player + persists audio settings; toast positions in resizeEvent.
- **Keyboard:** Ctrl+N / Ctrl+Q / F1 / Space / arrows / Shift+arrows /
  M wired with `_key_in_text_field` suppression.
- **Theme:** QSS rules for transport, toast, lyrics placeholder, now-
  playing labels.

**Test count:** 195 -> ~225 passing (+~30 across player, transport_bar,
now_playing_pane, toast, keyboard_shortcuts, settings).

**Indie-review carry-forward closures:**
- ✅ Theme E (keyboard shortcuts) — all Spec 00 shortcuts wired.

**Phase 3B (lyrics) carries forward to v0.4.0** — `LyricsPlaceholder`
QFrame in `NowPlayingPane` reserves the panel space; `Player.position_changed`
is fully exposed for the future `LyricsTracker` to subscribe.
```

Strike Theme E from the cross-cutting findings list (line 155); annotate `(closed in v0.3.0)`.

Update the "Upcoming phases" block:
- v0.3.0 entry → moved to closed.
- New v0.4.0 = Phase 3B Lyrics; new v0.5.0 = Phase 4 Export.

- [ ] **Step 3: Stage and commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
release: v0.3.0 — Phase 3A audio playback

QMediaPlayer-based playback service; transport bar with scrubber + volume;
NowPlayingPane in the right pane (replaces Phase 2 placeholder); per-row
preview-play on library + order panes; all Spec 00 keyboard shortcuts wired
with text-field suppression (closes indie-review Theme E); last-played track
restored at startup paused at zero; volume + mute persisted via settings.json.

Lyrics alignment (Spec 07) deferred to v0.4.0 — LyricsPlaceholder QFrame
reserves the panel space; Player.position_changed exposed for the future
LyricsTracker.

Tests: 195 -> ~225 passing. Ruff clean.
EOF
)"
```

- [ ] **Step 4: Tag and push**

```bash
git tag -a v0.3.0 -m "v0.3.0 — Phase 3A audio playback"
git push origin main
git push origin v0.3.0
```

(Public repo — free Linux CI minutes, push freely.)

---

## Test contract crosswalk

| TC | Coverage | Test file / location |
|---|---|---|
| TC-06-01 | direct | `test_player.py::test_set_source_play_reaches_playing` |
| TC-06-02 | direct | `test_player.py::test_volume_int_to_float_mapping` |
| TC-06-03 | direct | `test_player.py::test_seek_lands_within_tolerance` (add) |
| TC-06-04 | direct | `test_player.py::test_swap_source_mid_play_replaces` |
| TC-06-05 | direct | `test_player.py::test_missing_source_emits_error` |
| TC-06-06 | indirect | `test_player.py::test_missing_source_emits_error` covers the same code path; corrupt-MP3 fixture is a manual-smoke item |
| TC-06-07 | direct | `test_main_window.py::test_codec_error_shows_one_shot_dialog` |
| TC-06-08 | direct | `test_player.py::test_seek_clamps_beyond_duration` |
| TC-06-09 | direct | `test_player.py::test_stop_after_play_is_synchronous` + `test_main_window.py::test_close_event_stops_player` |
| TC-06-10 | direct | `test_settings.py::test_audio_round_trip` + main_window startup integration |
| TC-06-11 | direct | `test_main_window.py::test_state_last_played_round_trip` |
| TC-06-12 | direct | `test_keyboard_shortcuts.py::test_space_toggles_player` + `test_space_suppressed_in_text_field` |
| TC-06-13 | direct | `test_keyboard_shortcuts.py::test_left_arrow_seeks_minus_5` + `test_shift_left_seeks_minus_30` |
| TC-06-14 | direct | `test_transport_bar.py::test_buffering_label_shown_on_buffering_signal` |
| TC-06-15 | direct | `test_library_pane.py::test_library_pane_emits_preview_play_request` + `test_album_order_pane.py::test_album_order_pane_emits_preview_play` |
| TC-06-16 | direct | `test_player.py::test_end_of_track_does_not_auto_advance` |

Indirect entries: TC-06-06 — corrupt-MP3 input shares the same `errorOccurred` slot path as missing-file; testing both would duplicate the same code path. Manual-smoke step 7 exercises a true corrupt MP3 once before release.

---

## Out of scope for Phase 3A (deferred to 3B / 4 / future)

- **Lyrics alignment + display** (Spec 07) — Phase 3B (v0.4.0).
- **Auto-advance to next album track** at end-of-track — Spec 06 §Out of scope, future v2.
- **Gapless / crossfade playback** — Spec 06 §Out of scope.
- **Equalizer / DSP** — Spec 06 §Out of scope.
- **Word-level lyric highlighting** — Spec 07 §Out of scope.
- **Real-corrupt-MP3 automated test fixture** — manual smoke covers it pre-release; a synthetic corrupt fixture would be brittle across GStreamer versions.

---

## Manual smoke checklist (Phase 3A pre-release)

1. Cold launch — window opens; right pane shows `(nothing loaded)` placeholder.
2. Click `▶` on a `Tracks/` row — track loads, transport bar shows duration, plays.
3. Drag scrubber forward — seek lands at chosen position; current-time label updates.
4. Volume slider 0..100 — audible level change; setting persists across launches.
5. Mute button — silences audio; glyph flips `🔊`/`🔇`.
6. Space toggles play/pause when window has focus.
7. Typing in album-name field — Space inserts a space, does NOT toggle.
8. Left/Right with focus on table — seeks ±5 s; with Shift, ±30 s.
9. Ctrl+N → new-album dialog; Ctrl+Q → close; F1 → help dialog.
10. Quit while playing — app exits silently (no zombie audio).
11. Re-launch — last-played track loaded paused at zero; volume + mute restored.
12. Rename a track on disk while app is open, click play on the renamed row — toast: "Track file not found: <path>".
13. Boot a host without GStreamer plugins (or temporarily uninstall `gstreamer-plugins-good`) — first failed playback surfaces the codec dialog with the install command; subsequent failures show only the toast.

If any item above fails, the bug stops the release. Roll forward in a v0.3.1 patch.
