"""Main window - top bar + three-pane horizontal splitter, wired to
AlbumStore + LibraryWatcher + AppState (Phase 2) + Player (Phase 3A)."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from album_builder.domain.track import Track
from album_builder.persistence.lrc_io import read_lrc
from album_builder.persistence.settings import AudioSettings, read_audio, write_audio
from album_builder.persistence.state_io import AppState, WindowState, save_state
from album_builder.services.album_store import AlbumStore
from album_builder.services.alignment_service import AlignmentService
from album_builder.services.alignment_status import AlignmentStatus, compute_status
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.lyrics_tracker import LyricsTracker
from album_builder.services.player import Player
from album_builder.ui.album_order_pane import AlbumOrderPane
from album_builder.ui.library_pane import LibraryPane
from album_builder.ui.now_playing_pane import NowPlayingPane
from album_builder.ui.theme import Palette, qt_stylesheet
from album_builder.ui.toast import Toast
from album_builder.ui.top_bar import TopBar

logger = logging.getLogger(__name__)

# Spec 10 §state.json: splitter_sizes is normalised to small relative ratios
# rather than DPI-dependent absolute pixels. The total only needs to be a
# stable small integer for round-trip identity; matches the spec example
# `[5, 3, 5]` (sum 13) but is otherwise arbitrary.
SPLITTER_RATIO_TOTAL = 13


def _redact_home(value: object) -> str:
    """Replace `$HOME` occurrences in `str(value)` with a literal `~`.

    The closeEvent failure summary lands on stderr (which a desktop launcher
    may redirect to a shared journal). Exception messages from os-level
    APIs commonly embed the absolute path that failed, which on a single-
    user machine reveals the username. Redacting `$HOME` -> `~` keeps the
    diagnostic intact (you can still tell *which* file failed) without
    leaking the home directory path. (L8-privacy.)"""
    s = str(value)
    home = str(Path.home())
    return s.replace(home, "~") if home else s


def _hamilton_ratios(pixels: list[int], total: int) -> list[int]:
    """Apportion `total` across the entries in `pixels` proportional to
    their values, preserving the sum (Hamilton's largest-remainder method).

    L8-M1: the previous `round(p * total / sum(pixels))` could produce
    `[1, 1, 1500] -> [1, 1, 13]` (sum 15) on pathological splits. Hamilton
    floors each share, then bumps the entries with the largest fractional
    remainders until the floors sum to `total`. Returns `[total, 0, ...]`
    style assignments only when the input degenerates to all-zero pixels.
    Each entry is at least 0 (Spec 10 §state.json: splitter_sizes >= 0)."""
    n = len(pixels)
    if n == 0:
        return []
    sum_p = sum(pixels)
    if sum_p <= 0:
        # Degenerate (no widget has been laid out yet). Spread evenly with
        # any rounding remainder allocated to the first entry.
        base = total // n
        remainder = total - base * n
        return [base + (remainder if i == 0 else 0) for i in range(n)]
    raw = [(p * total) / sum_p for p in pixels]
    floors = [int(r) for r in raw]
    deficit = total - sum(floors)
    # Allocate the deficit to the entries with the largest fractional parts.
    fractions = sorted(
        ((raw[i] - floors[i], i) for i in range(n)),
        key=lambda t: (-t[0], t[1]),
    )
    for k in range(deficit):
        _, i = fractions[k]
        floors[i] += 1
    return floors


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: AlbumStore,
        library_watcher: LibraryWatcher,
        state: AppState,
        project_root: Path,
    ):
        super().__init__()
        self._store = store
        self._library_watcher = library_watcher
        self._state = state
        self._project_root = project_root
        # Window title is the bare app name; KDE / GNOME shells render
        # `app.setApplicationVersion` separately (in the about-dialog and
        # task-switcher tooltip), so duplicating it in the title bar is
        # redundant noise. (L8-info Tier 3 cleanup.)
        self.setWindowTitle("Album Builder")
        # Clamp restored geometry against pathological values (hand-edited
        # state.json with width=10 would open a 10 px wide window). Spec 10
        # documents minimum 100px implicit; explicit here so a corrupt cache
        # doesn't make the app unusable.
        self.resize(max(400, state.window.width), max(300, state.window.height))
        self.move(max(0, state.window.x), max(0, state.window.y))
        self.setStyleSheet(qt_stylesheet(Palette.dark_colourful()))

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.top_bar = TopBar(store)
        outer.addWidget(self.top_bar)

        # Player + audio settings (Spec 06).
        self._player = Player(self)
        audio = read_audio()
        self._player.set_volume(audio.volume)
        self._player.set_muted(audio.muted)
        self._player.error.connect(self._on_player_error)

        # Lyrics tracker + alignment service (Spec 07). The tracker
        # subscribes to player.position_changed and pushes the current
        # line index to the LyricsPanel via the wiring below; the service
        # owns the QThread workers that produce .lrc files on demand.
        self._tracker = LyricsTracker(self._player, self)
        self._alignment = AlignmentService(parent=self)
        self._alignment.status_changed.connect(self._on_alignment_status)
        self._alignment.progress.connect(self._on_alignment_progress)
        self._alignment.lyrics_ready.connect(self._on_lyrics_ready)
        self._alignment.error.connect(self._on_alignment_error)
        # Surface a single helpful dialog the first time WhisperX is
        # missing — same shape as the codec-class dialog for Spec 06.
        self._whisperx_dialog_shown = False

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.library_pane = LibraryPane()
        self.library_pane.set_library(library_watcher.library())
        self.album_order_pane = AlbumOrderPane()
        self.now_playing_pane = NowPlayingPane(self._player)
        self.splitter.addWidget(self.library_pane)
        self.splitter.addWidget(self.album_order_pane)
        self.splitter.addWidget(self.now_playing_pane)
        # L8-H1: Qt renormalises setSizes() against the splitter's *current*
        # actual width. At construction the splitter has no real width yet
        # (it's near zero / sizeHint-driven), so the saved ratios drift on
        # first paint. Stash the desired sizes and apply them in showEvent
        # once the splitter has its real width.
        self._restore_splitter_sizes: list[int] = list(state.window.splitter_sizes)
        outer.addWidget(self.splitter, stretch=1)

        # Toast overlays the bottom of the central widget. Position is
        # updated on resize so it always sits above the bottom edge.
        self._toast = Toast(self)

        # Debounced state-save timer for splitter / geometry mutations (TC-03-10).
        self._state_save_timer = QTimer(self)
        self._state_save_timer.setSingleShot(True)
        self._state_save_timer.setInterval(250)
        self._state_save_timer.timeout.connect(self._save_state_now)

        # Wire signals
        self.top_bar.switcher.current_album_changed.connect(self._on_current_changed)
        self.top_bar.rename_committed.connect(self._on_rename)
        self.top_bar.target_committed.connect(self._on_target)
        self.top_bar.approve_requested.connect(self._on_approve)
        self.top_bar.reopen_requested.connect(self._on_reopen)
        self.top_bar.switcher.new_album_requested.connect(self._on_new_album)
        self.top_bar.switcher.delete_requested.connect(self._on_delete_album)
        self.library_pane.selection_toggled.connect(self._on_selection_toggled)
        self.library_pane.preview_play_requested.connect(self._on_preview_play)
        self.album_order_pane.reordered.connect(self._on_reorder_done)
        self.album_order_pane.preview_play_requested.connect(self._on_preview_play)
        library_watcher.tracks_changed.connect(self.library_pane.set_library)
        # Lyrics: tracker → panel (current-line index); panel → service (Align-now)
        self._tracker.current_line_changed.connect(
            self.now_playing_pane.lyrics_panel.set_current_line
        )
        self.now_playing_pane.lyrics_panel.align_now_requested.connect(
            self._on_align_now_clicked
        )
        self.splitter.splitterMoved.connect(lambda *_: self._state_save_timer.start())

        # Spec 00 keyboard shortcuts (closes indie-review Theme E).
        self._wire_shortcuts()

        # Restore last-played track from state.json (Spec 06 TC-06-11).
        if state.last_played_track_path:
            last = Path(state.last_played_track_path)
            track = next(
                (t for t in library_watcher.library().tracks if t.path == last),
                None,
            )
            if track is not None:
                self._player.set_source(track.path)
                self.now_playing_pane.set_track(track)
                # Spec 07 cache-hit at startup: if the LRC is fresh, show
                # the lyrics paused at zero alongside the track.
                self._sync_lyrics_for_track(track)

        # Restore current album from state (TC-03-07) with fallback (TC-03-09)
        if state.current_album_id and store.get(state.current_album_id):
            self.top_bar.switcher.set_current(state.current_album_id)
        else:
            albums = store.list()
            if albums:
                self.top_bar.switcher.set_current(albums[0].id)

    def _current_album(self):
        cid = self.top_bar.switcher.current_id
        return self._store.get(cid) if cid else None

    def _on_current_changed(self, album_id) -> None:
        self.top_bar.set_current(album_id)
        album = self._store.get(album_id) if album_id else None
        self.library_pane.set_current_album(album)
        self.album_order_pane.set_album(
            album, list(self._library_watcher.library().tracks) if album else []
        )
        self._state.current_album_id = album_id
        self._state_save_timer.start()

    def _on_rename(self, album_id: UUID, new_name: str) -> None:
        self._store.rename(album_id, new_name)
        self.top_bar.set_current(album_id)

    def _on_target(self, album_id: UUID, n: int) -> None:
        album = self._store.get(album_id)
        if album is None:
            return
        try:
            album.set_target(n)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot lower target", str(exc))
            self.top_bar.set_current(album_id)  # revert UI
            return
        self._store.schedule_save(album_id)
        self.top_bar.set_current(album_id)

    def _on_approve(self, album_id: UUID) -> None:
        if QMessageBox.question(
            self, "Approve album",
            "Approve this album? It will be locked from edits until you "
            "reopen it. (Export to symlinks + a printable report will run "
            "automatically once that feature ships.)",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.approve(album_id)
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot approve", str(exc))
            return
        self.top_bar.set_current(album_id)
        self.library_pane.set_current_album(self._store.get(album_id))
        self.album_order_pane.set_album(
            self._store.get(album_id), list(self._library_watcher.library().tracks)
        )

    def _on_reopen(self, album_id: UUID) -> None:
        if QMessageBox.question(
            self, "Reopen for editing",
            "Reopening will delete the approved report. Continue?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.unapprove(album_id)
        self.top_bar.set_current(album_id)
        self.library_pane.set_current_album(self._store.get(album_id))
        self.album_order_pane.set_album(
            self._store.get(album_id), list(self._library_watcher.library().tracks)
        )

    def _on_new_album(self) -> None:
        name, ok = QInputDialog.getText(self, "New album", "Album name (1-80 chars):")
        if not ok or not name.strip():
            return
        target, ok = QInputDialog.getInt(
            self, "Target track count", "How many tracks?", 12, 1, 99,
        )
        if not ok:
            return
        try:
            album = self._store.create(name=name.strip(), target_count=target)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot create album", str(exc))
            return
        self.top_bar.switcher.set_current(album.id)

    def _on_delete_album(self, album_id: UUID) -> None:
        album = self._store.get(album_id)
        if album is None:
            return
        if QMessageBox.question(
            self, "Delete album",
            f"Delete '{album.name}'? A backup is kept in Albums/.trash/.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.delete(album_id)
        self.top_bar.switcher.set_current(self._store.current_album_id)

    def _on_selection_toggled(self, path: Path, new_state: bool) -> None:
        album = self._current_album()
        if album is None:
            return
        try:
            if new_state:
                album.select(path)
            else:
                album.deselect(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot toggle", str(exc))
            return
        self._store.schedule_save(album.id)
        self.top_bar.set_current(album.id)
        self.library_pane.set_current_album(album)
        self.album_order_pane.set_album(album, list(self._library_watcher.library().tracks))

    def _on_reorder_done(self) -> None:
        album = self._current_album()
        if album is None:
            return
        self._store.schedule_save(album.id)

    def _wire_shortcuts(self) -> None:
        """Spec 00 keyboard table — wired in Phase 3A.

        Transport shortcuts (Space / Left / Right / Shift+Left / Shift+Right
        / M) suppress when focus is in a text-input widget so a user typing
        in the album-name editor or target-counter doesn't accidentally
        scrub the player.
        """
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_album)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        QShortcut(QKeySequence("F1"), self, activated=self._show_help)
        QShortcut(QKeySequence("Space"), self, activated=self._space_pressed)
        QShortcut(QKeySequence("Left"), self, activated=lambda: self._seek_relative(-5))
        QShortcut(QKeySequence("Right"), self, activated=lambda: self._seek_relative(5))
        QShortcut(QKeySequence("Shift+Left"), self,
                  activated=lambda: self._seek_relative(-30))
        QShortcut(QKeySequence("Shift+Right"), self,
                  activated=lambda: self._seek_relative(30))
        QShortcut(QKeySequence("M"), self, activated=self._toggle_mute)

    def _key_in_text_field(self) -> bool:
        # L8-M3: broadened beyond QLineEdit / QSpinBox / QTextEdit to cover
        # every Qt input that consumes typed characters — QAbstractSpinBox
        # subclasses (QDoubleSpinBox), QDateTimeEdit, and editable
        # QComboBox. Otherwise pressing Space / arrow keys while typing
        # in any of these toggles playback / scrubs.
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QTextEdit, QAbstractSpinBox, QDateTimeEdit)):
            return True
        # Editable QComboBox: the line edit is a child whose parent is the
        # combo. Walk up one level to recognise the case.
        if isinstance(w, QLineEdit):
            return True
        parent = w.parent() if w is not None else None
        if isinstance(parent, QComboBox) and parent.isEditable():
            return True
        return False

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
        # Sync transport-bar glyph if the now-playing pane has surfaced one.
        if hasattr(self.now_playing_pane, "transport"):
            self.now_playing_pane.transport._sync_mute_glyph()

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
        self._sync_lyrics_for_track(track)
        self._state.last_played_track_path = path
        self._state_save_timer.start()

    def _sync_lyrics_for_track(self, track: Track) -> None:
        """Spec 07: cache hit → READY + load LRC + tracker takes over;
        cache miss → status from compute_status; auto-align if opt-in.

        On every track change the tracker's lyrics are reset (None ⇒ -1)
        before any new Lyrics arrive, so a residual current-line index
        from the previous track can't render against the new track.
        """
        panel = self.now_playing_pane.lyrics_panel
        self._tracker.set_lyrics(None)
        panel.set_lyrics(None)
        status = compute_status(track)
        if status == AlignmentStatus.READY:
            lyrics = read_lrc(track.path)
            if lyrics is not None:
                panel.set_lyrics(lyrics)
                self._tracker.set_lyrics(lyrics)
                panel.set_status(AlignmentStatus.READY)
                return
            # The freshness check passed but the parse just failed — read_lrc
            # already moved the file to .bak; fall through to NOT_YET_ALIGNED.
            status = AlignmentStatus.NOT_YET_ALIGNED
        panel.set_status(status)
        if status == AlignmentStatus.NOT_YET_ALIGNED:
            # L8-M5: auto_align_on_play is gated on the
            # alignment.auto_align_on_play setting (default off, Spec 07
            # opt-in). The method name doesn't reveal the conditional so
            # we surface that here. Calling unconditionally is deliberate.
            self._alignment.auto_align_on_play(track)

    def _current_track(self) -> Track | None:
        path = self._state.last_played_track_path
        if path is None:
            return None
        return next(
            (t for t in self._library_watcher.library().tracks if t.path == path),
            None,
        )

    def _on_align_now_clicked(self) -> None:
        """User clicked "Align now" on the lyrics panel."""
        track = self._current_track()
        if track is None:
            self._toast.show_message("No track loaded")
            return
        # Spec 07 §Alignment job: confirm the ~1 GB model download on the
        # first opt-in, but only when we actually need to fetch it. We
        # show the dialog every time alignment is started for a track
        # whose LRC is missing — the user controls the cost explicitly.
        if not self._confirm_alignment_download():
            return
        self._alignment.start_alignment(track)

    def _confirm_alignment_download(self) -> bool:
        # Open question: a "don't show again this session" affordance is
        # tracked as v0.5+ polish; for v0.4.0 the explicit confirm is the
        # contract.
        button = QMessageBox.question(
            self,
            "Align lyrics — model download",
            "Aligning lyrics uses local ML (Whisper + wav2vec2). On first "
            "use, ~1 GB of model files will download to "
            "~/.cache/album-builder/whisper-models/. Continue?",
        )
        return button == QMessageBox.StandardButton.Yes

    def _on_alignment_status(self, path: Path, status: AlignmentStatus) -> None:
        # Only mirror the state to the panel when the change is for the
        # currently-loaded track — a stale worker emit on a no-longer-
        # active track shouldn't redraw the visible pill.
        active = self._state.last_played_track_path
        if active is None or path != active:
            return
        self.now_playing_pane.lyrics_panel.set_status(status)

    def _on_alignment_progress(self, path: Path, percent: int) -> None:
        active = self._state.last_played_track_path
        if active is None or path != active:
            return
        self.now_playing_pane.lyrics_panel.set_status(
            AlignmentStatus.ALIGNING, percent=percent
        )

    def _on_lyrics_ready(self, path: Path, lyrics) -> None:
        active = self._state.last_played_track_path
        if active is None or path != active:
            return
        self.now_playing_pane.lyrics_panel.set_lyrics(lyrics)
        self._tracker.set_lyrics(lyrics)

    def _on_alignment_error(self, _path: Path, msg: str) -> None:
        self._toast.show_message(f"Alignment failed: {msg}")
        if self._looks_like_whisperx_missing(msg) and not self._whisperx_dialog_shown:
            # Anchor the install hint at sys.executable so it lands in the
            # app's own venv regardless of dev-tree vs installed location;
            # bare `pip install` would target the system Python and on
            # PEP 668 distros (openSUSE, Debian 12+) require an extra
            # --break-system-packages flag that doesn't even fix the
            # original problem (the app's venv is a separate site-packages).
            import sys as _sys
            QMessageBox.warning(
                self,
                "WhisperX not installed",
                "Lyrics alignment requires the optional WhisperX runtime.\n"
                "Install it via:\n\n"
                f"    {_sys.executable} -m pip install whisperx\n\n"
                "and restart the app. The first run downloads ~1 GB of model "
                "files to ~/.cache/album-builder/whisper-models/.",
            )
            self._whisperx_dialog_shown = True

    @staticmethod
    def _looks_like_whisperx_missing(msg: str) -> bool:
        m = msg.lower()
        return "whisperx" in m and ("not installed" in m or "no module" in m)

    def _on_player_error(self, msg: str) -> None:
        self._toast.show_message(msg)
        if self._looks_like_codec_error(msg) and not self._player.codec_dialog_shown():
            QMessageBox.warning(
                self,
                "Audio codecs unavailable",
                "Audio playback requires the GStreamer / FFmpeg backend.\n"
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

    def showEvent(self, e) -> None:
        super().showEvent(e)
        # L8-H1: apply the restored splitter ratios now that the splitter
        # has its real width. Reapply only once per session — re-shows
        # (minimise->restore) shouldn't re-clamp to the construction-time
        # ratios.
        if self._restore_splitter_sizes:
            self.splitter.setSizes(self._restore_splitter_sizes)
            self._restore_splitter_sizes = []

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        # Bottom-of-window banner; sits above the bottom edge.
        if hasattr(self, "_toast"):
            self._toast.setGeometry(20, self.height() - 60, self.width() - 40, 40)
        self._state_save_timer.start()

    def moveEvent(self, e) -> None:
        super().moveEvent(e)
        self._state_save_timer.start()

    def closeEvent(self, e) -> None:
        # L8-M2: stop the debounced state-save timer first thing so a 250
        # ms tick mid-teardown can't race the synchronous _save_state_now
        # below (and write a stale partial state into state.json).
        self._state_save_timer.stop()
        # Flush all debounced writes before exit (Spec 10). Each step is
        # wrapped so a raise from one (e.g. ENOSPC mid-flush) does not skip
        # the other - window geometry must persist even if the per-album
        # writer queue couldn't drain. L8-H4: collect step failures into
        # one stderr line at the end so the user has something visible
        # to act on rather than a silent stack trace in the log.
        failures: list[str] = []
        try:
            self._player.stop()
        except Exception as exc:
            logger.exception("Player.stop() failed during closeEvent")
            failures.append(f"player.stop: {_redact_home(exc)}")
        try:
            write_audio(AudioSettings(
                volume=self._player.volume(), muted=self._player.muted(),
            ))
        except Exception as exc:
            logger.exception("write_audio() failed during closeEvent")
            failures.append(f"write_audio: {_redact_home(exc)}")
        try:
            self._store.flush()
        except Exception as exc:
            logger.exception("AlbumStore.flush() failed during closeEvent")
            failures.append(f"album-store flush: {_redact_home(exc)}")
        try:
            self._save_state_now()
        except Exception as exc:
            logger.exception("save_state_now() failed during closeEvent")
            failures.append(f"save_state: {_redact_home(exc)}")
        if failures:
            import sys as _sys
            print(
                "album-builder: close-event partial failure: " + "; ".join(failures),
                file=_sys.stderr,
            )
        super().closeEvent(e)

    def _save_state_now(self) -> None:
        # Spec 10 state.json: splitter_sizes are RATIOS, not pixels.
        # QSplitter.sizes() returns pixels; QSplitter.setSizes() interprets
        # any positive ints as ratios and rescales to the actual pane width
        # at restore time. We normalise to a fixed small total so
        # state.json doesn't grow with display DPI - the absolute values
        # would otherwise drift between screens.
        pixels = self.splitter.sizes()
        ratios = _hamilton_ratios(pixels, SPLITTER_RATIO_TOTAL)
        self._state.window = WindowState(
            width=self.width(), height=self.height(),
            x=self.x(), y=self.y(),
            splitter_sizes=ratios,
        )
        save_state(self._project_root, self._state)
