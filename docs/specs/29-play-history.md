<!-- ants-spec-format: 1 -->
# 29 — Play history: favourites, play counts, recently and most played

**Status:** spec draft (2026-11-18).
**Kind:** implement.
**Source:** ROADMAP MUSI-0356 Phase MP-4 (user request 2026-07-25; owner decisions 2026-11-18).
**Depends on:** 01, 06, 10, 11, 15, 17, 18, 25, 26. **Amends:** 00, 06, 10, 11, 17, 18.

**Layman:** Mark songs you love with a heart. The app counts how often you really listen to each song and when you last did, and the Player tab gains three ready-made lists: Favourites, Recently played and Most played.

## 1. Goal

After this ships, a song can be hearted from the Player tab. Every song that is really listened to (half of it, or 4 minutes) gains a play and a last-played time. The Player tab's song list shows a heart and a play count per song and sorts by either. The Playlists tab opens with three lists that fill themselves: Favourites, Recently played and Most played.

## 2. Problem

Checked 2026-11-18: nothing in `src/` records a favourite, a rating, a play count or a play time. `state.json` keeps the song to resume (`AppState.last_played_track_path`, Spec 26). The pieces this builds on:

- `Player` (`services/player.py`) reports position (`position_changed`), user jumps (`seeked`), state (`state_changed`) and natural ends (`ended`). Nothing measures how long a song was actually heard, and no signal says a new source was loaded.
- `PlaybackController._load_and_play` calls `Player.set_source` for every song it loads, including a repeat-one replay of the same song, but emits `current_changed` only when the song differs.
- Play after Stop, or after the queue ends, replays the loaded song without `set_source` (`PlaybackController.toggle` and `play`).
- Songs are identified by `Track.path`, an absolute resolved path. `Library.scan` reads one folder without recursion, and `Library.folder` is that folder, resolved.
- `PlaylistsPane` (`ui/playlists_pane.py`) lists only `PlaylistStore` playlists, every one renamable and deletable.
- `COLUMNS` in `ui/library_pane.py` has no heart or play-count column; `Glyphs` has no heart.

## 3. Scope decisions (agreed with the user)

Owner decisions, 2026-11-18 (recorded on MUSI-0356):

- **A favourite heart, not star ratings.**
- **The data lives in the app's own file, never in song tags.** Renaming or moving one song file loses its heart and counts.
- **A play counts once half the song, or 4 minutes, has played.**
- **The Player tab offers Favourites, Recently played and Most played.**

Owner answers, 2026-11-18, in this session:

- **The heart shows on the Player tab's now-playing card and as a column in the Player tab's song list, beside a "Plays" column; right-click offers it too.**
- **Listening in either tab counts.** Short preview clicks never reach the threshold.
- **The three lists sit at the top of the Playlists tab**, marked as filling themselves, playable like a playlist, never renamed, deleted or reordered.
- **Moving the whole music folder keeps the data**: songs are matched by their path inside the music folder.

Author's calls, each open to the owner:

- **Songs of 30 s or less never count**, so a short jingle cannot gain a play in 15 s. Recorded here so it can be dropped.
- **Recently played and Most played show 50 songs each.** Favourites has no limit.
- **Favourites are listed newest heart first**, so a heart is stored as the time it was given.
- **The file is `.album-builder/play_history.json`**, beside `state.json` and `playlists.json`, and is never folded into `state.json`, which self-heals by resetting (Spec 10) and would wipe months of history on one bad byte.
- **No MPRIS rating.** `services/mpris.py` exposes none today.

## 4. Design

### 4.1 `play_history.json` (this spec owns the bytes)

```json
{
  "schema_version": 1,
  "songs": {
    "Slow Tide.mp3": {
      "favourited": "2026-11-18T15:04:05.123Z",
      "last_played": "2026-11-18T16:10:00.000Z",
      "plays": 12
    },
    "Walking Home Late.flac": {
      "favourited": null,
      "last_played": "2026-11-17T09:00:00.000Z",
      "plays": 1
    }
  }
}
```

| Field | Type | Constraint | On a bad value |
|---|---|---|---|
| `songs` key | string | the song's path relative to `Library.folder`, POSIX separators | — (any string is a key; §5 trust boundary) |
| `favourited` | string or `null` | Spec 10 §Timestamps | `null` |
| `last_played` | string or `null` | Spec 10 §Timestamps | `null` |
| `plays` | int | `>= 0`; a bool is not an int | `0` |
| `songs` | object | | an absent or non-object `songs` is a corrupt file |

An entry that is not an object is dropped alone. An entry left with `favourited` `null` and `plays` `0` is not written. Spec 10 §Encoding rules apply (sorted keys, 2-space indent, `null` for empty fields), except §Paths: keys are relative (Keying, below). Writes are atomic.

**Keying.** The key is `track.path.relative_to(library.folder).as_posix()`. `Library.scan` does not recurse, so today the key is the file name. A track whose path is not under `Library.folder` gets no key and is never recorded. To show a song's data, its key is joined to the current `Library.folder` and looked up with `Library.find`, so a library moved whole keeps its data.

**Load.** Absent file: empty history. A file that does not parse, is not an object, lacks `schema_version`, or has a bad `songs`: `load_history` raises, as `load_playlists` does (Spec 17 §Persistence & schema). `PlayHistory` then:

- **Corrupt:** starts empty with `load_failed = True`. The first save renames the file to `play_history.json.corrupt.bak`, then writes. `MainWindow` shows a toast saying so.
- **Newer `schema_version`:** starts empty with `read_only = True`, and never writes the file for the rest of the run (Spec 10 §Schema versioning: "Don't crash, don't overwrite"). Hearts and plays still work in memory. A toast says they will not be saved until the app is updated.

### 4.2 What counts as a play

Constants in `domain/play_history.py`: `PLAY_MAX_THRESHOLD_S = 240.0`, `PLAY_MIN_SONG_S = 30.0`, `MAX_TICK_S = 2.0`.

A **listen** starts at every `Player.source_changed` and at every `state_changed` to `STOPPED` (a Stop, or a song's end). So a song replayed after Stop, or after it ended, is a new listen. Within a listen:

- **Heard time** grows by `p - last` for each `position_changed(p)` received while `Player.state()` is `PLAYING`, but only when `0 < p - last <= MAX_TICK_S`. Every `position_changed` and every `seeked(p)` sets `last = p`, whatever the state. So a seek, a resume point applied while stopped (Spec 26), or a backward jump adds nothing. The keyboard seeks 5 or 30 s (`MainWindow._seek_relative`), so the cap alone stops them; the `seeked` reset covers a small scrubber or MPRIS jump, except when the backend's `position_changed` for it arrives before `seeked`, which adds under 2 s. The backend reports position about every 100 ms (measured 2026-11-18 on Linux with Qt's FFmpeg backend: a 6 s wav, largest gap 102 ms), so `MAX_TICK_S` is twenty times the normal gap.
- **Threshold**, from `d = Player.duration()` at the moment of the check:
  - `d > 0` and `d <= PLAY_MIN_SONG_S`: never counts.
  - `d > PLAY_MIN_SONG_S`: `min(d / 2, PLAY_MAX_THRESHOLD_S)`.
  - `d <= 0` (not yet known): `PLAY_MAX_THRESHOLD_S`.
- The first time heard time reaches the threshold, the song's `plays` goes up by one and `last_played` becomes now (UTC). A listen counts at most once. A repeat-one replay is a new listen, because `_load_and_play` calls `set_source` again.

Heard time is kept in memory only. A listen cut by quitting is lost; resuming the song after relaunch (Spec 26) starts a new listen at the resume point.

### 4.3 New surfaces

```python
# services/player.py
class Player:
    source_changed = pyqtSignal(object)  # Type: Path | None; every set_source call,
                                         # the same path included

# domain/play_history.py  (pure, no Qt)
@dataclass(frozen=True)
class SongStats:
    plays: int = 0
    last_played: datetime | None = None
    favourited: datetime | None = None

class ListenMeter:
    def start(self) -> None: ...                              # a new listen
    def position(self, seconds: float, *, playing: bool) -> None: ...
    def seeked(self, seconds: float) -> None: ...
    def reached(self, duration: float) -> bool: ...           # True once per listen

def favourites(stats: Mapping[str, SongStats]) -> list[str]: ...
def recently_played(stats: Mapping[str, SongStats], limit: int = 50) -> list[str]: ...
def most_played(stats: Mapping[str, SongStats], limit: int = 50) -> list[str]: ...

# persistence/play_history_io.py
HISTORY_FILE = "play_history.json"
def load_history(project_root: Path) -> dict[str, SongStats]: ...   # raises on corrupt / too new
def save_history(project_root: Path, stats: Mapping[str, SongStats]) -> None: ...

# services/play_history.py
class SmartList(Enum):
    FAVOURITES = "favourites"
    RECENTLY_PLAYED = "recently_played"
    MOST_PLAYED = "most_played"

class PlayHistory(QObject):
    changed = pyqtSignal()
    load_failed: bool
    read_only: bool
    def __init__(self, project_root: Path, player: Player,
                 library_watcher: LibraryWatcher, parent: QObject | None = None): ...
    def stats_for(self, track: Track) -> SongStats: ...
    def set_favourite(self, track: Track, on: bool) -> None: ...
    def smart_list(self, which: SmartList) -> list[Track]: ...
    def flush(self) -> None: ...
```

`PlayHistory` owns a `ListenMeter`, feeds it from `Player`, and maps the source path to a key through `library_watcher.library()`. Every change (a heart, a counted play) updates memory, emits `changed`, and schedules a write through a `DebouncedWriter` (250 ms, Spec 10 §Debounce). `MainWindow` builds it beside `PlaylistStore` and calls `flush()` in `closeEvent`.

### 4.4 The three lists

`favourites`, `recently_played` and `most_played` return keys. `PlayHistory.smart_list` passes them only the entries whose key has a track in the current library, then maps the keys to `Track`s, so a missing song does not shorten a limited list. Missing songs stay in the file and come back if the file returns.

- **Favourites:** `favourited` not `null`, newest `favourited` first.
- **Recently played:** `last_played` not `null`, newest first, at most 50.
- **Most played:** `plays >= 1`, most plays first, ties broken by newest `last_played`, then by key, at most 50.

### 4.5 Player tab

**Playlists tab.** `PlaylistsPane` shows the three lists as its first rows, in the order above, each name prefixed with `Glyphs.AUTO_LIST` and above the user's playlists. Selecting one shows its songs in the tracks list. For these rows:

- the name is not editable, and Delete, Up, Down and Remove are disabled;
- Play plays the shown songs in the shown order through `PlaybackController.play_tracks`; an empty list toasts and leaves the queue alone, as an empty playlist does (Spec 17 §Errors & edge cases);
- the shown songs refresh on `PlayHistory.changed` and on a library change.

The rows carry a `SmartList` under their own item role, never a `PlaylistStore` id, so no store call can receive one. "Add to playlist" menus keep listing only `PlaylistStore` playlists.

**Song list (player mode only).** `COLUMNS` gains `("♥", "_fav")` third, after `_toggle`, and `(N_("Plays"), "_plays")` after `duration_seconds`; `_used` stays last (TC-13-09a) and `_toggle` second (TC-04-26). Both new columns are hidden when `player_mode` is false.

- `_fav` shows `Glyphs.HEART` for a favourite and `Glyphs.HEART_OUTLINE` otherwise. A mouse click on the cell toggles the heart, and so does Enter with the cell current. Neither plays. A mouse activation of the cell (a double-click, or a single click on a style that activates on one, Spec 18 §`ui/library_pane.py` — player mode) adds no second toggle. Sort key: favourite first, then title.
- `_plays` shows the count, blank for 0. Sort key: the count.
- Both refresh on `PlayHistory.changed`, as `_used` does on `UsageIndex.changed`.
- The right-click menu gains "Add to favourites", or "Remove from favourites" when the clicked song is one. It acts on the clicked song, as the menu's other actions do.

**Now-playing card.** The Player tab's `NowPlayingCard` gains a checkable heart button showing the current track's state; the Album Builder tab's card does not. Its accessible name is "Favourite" and its tooltip says "Add to favourites" or "Remove from favourites". With no track loaded it is disabled.

**Glyphs.** `Glyphs.HEART = "♥"` (♥), `Glyphs.HEART_OUTLINE = "♡"` (♡), `Glyphs.AUTO_LIST = "↻"` (↻, "refreshes itself").

Every new string goes through `tr()` and into each shipped catalog (Spec 25, TC-25-03).

## 5. Invariants

Each *Test:* names the rule its fixture isolates.

- **INV-1** (TC-29-01) — `save_history` then `load_history` of a history carrying every §4.1 field returns equal values; the file has sorted keys, `null` for empty times, and Z-suffixed millisecond times.
  *Test:* `tests/persistence/test_TC_29_play_history_io.py::test_round_trip`.
  *Breaks when:* a field is dropped, or a time is written in another form.

- **INV-2** (TC-29-02) — A bad field heals alone: a non-int, negative or bool `plays` reads 0; an unparsable time, or one with no UTC offset, reads `null`; a non-object entry is dropped; the other entries load.
  *Test:* `tests/persistence/test_TC_29_play_history_io.py::test_field_heal`, one case per bad value of `favourited`, `last_played` and `plays`, plus a non-object entry, each beside a valid entry asserted unchanged (isolates per-entry healing from whole-file failure).
  *Breaks when:* one bad entry fails the whole load, a bool passes as a count, or a time with no offset is kept.

- **INV-3** (TC-29-03) — A corrupt file starts the history empty with `load_failed`, and the first save leaves the original bytes in `play_history.json.corrupt.bak`. A file with a newer `schema_version` starts empty with `read_only`, and after a heart and a flush its bytes are unchanged.
  *Test:* `tests/services/test_TC_29_play_history.py::test_load_failures`.
  *Breaks when:* a bad file is overwritten without a backup, or a newer file is written over.

- **INV-4** (TC-29-04) — A listen counts once heard time reaches `min(d / 2, 240)`; never for `0 < d <= 30`; at 240 when `d <= 0`.
  *Test:* `tests/domain/test_TC_29_listen_meter.py::test_threshold`, feeding 0.1 s ticks while playing: `d = 600` counts at 240 and not at 239.9; `d = 100` at 50; `d = 30` never; `d = 31` at 15.5; `d = 0` at 240.
  *Breaks when:* the half and 4-minute rules are combined with max, or the 30 s floor is off by one.

- **INV-5** (TC-29-05) — A seek adds no heard time.
  *Test:* `tests/domain/test_TC_29_listen_meter.py::test_seek_is_not_heard`, two cases on a 100 s song after 10 s of 0.1 s ticks. (a) A jump to 90 sent as `position_changed(90)` with no `seeked`: heard time stays 10 (isolates the `MAX_TICK_S` cap). (b) `seeked(11.5)` then `position_changed(11.5)`: heard time stays 10 (isolates the `seeked` reset; 1.5 s is under the cap).
  *Breaks when:* heard time is read from position, a jump over `MAX_TICK_S` is added, or `seeked` does not move `last`.

- **INV-6** (TC-29-06) — Ticks while not `PLAYING` add nothing but move `last`.
  *Test:* `tests/domain/test_TC_29_listen_meter.py::test_only_playing_counts`: 0.1 s ticks from 0 to 60 with `playing=False` on a 100 s song do not count (isolates the playing rule; every delta is under the cap); then 0.1 s ticks with `playing=True` from 60 add only the played span.
  *Breaks when:* paused or stopped ticks are added.

- **INV-7** (TC-29-07) — A listen counts at most once, and each `source_changed` or `state_changed` to `STOPPED` starts a new one, the same path included.
  *Test:* `tests/services/test_TC_29_play_history.py::test_once_per_listen`, driving a `Player` with `_set_state_for_test`, `_set_duration_for_test` and emitted ticks: one listen run past the threshold twice counts 1; a second `set_source` of the same path, run past the threshold, counts 2; an emitted `state_changed(STOPPED)`, then ticks past the threshold, counts 3.
  *Breaks when:* the meter restarts on `current_changed`, which a repeat-one replay does not emit, or only on `source_changed`, which Play after Stop does not emit.

- **INV-8** (TC-29-08) — `Player.source_changed` fires on every `set_source`, with the path, or `None` for a clear.
  *Test:* `tests/services/test_TC_29_play_history.py::test_source_changed`.
  *Breaks when:* it fires only when the path differs.

- **INV-9** (TC-29-09) — A counted play writes key `track.path.relative_to(library.folder).as_posix()` with `plays` + 1 and `last_played` now. A history saved for one library folder shows its data for a library at another folder holding the same file names. A source outside `Library.folder` records nothing.
  *Test:* `tests/services/test_TC_29_play_history.py::test_keying`, with two temporary folders holding the same file name (isolates relative keying from absolute keying).
  *Breaks when:* keys are absolute paths, or an outside path raises.

- **INV-10** (TC-29-10) — `set_favourite(track, True)` sets `favourited` to now; `False` sets it to `null`; an entry with no heart and no plays is not written; each change emits `changed` and reaches the file after `flush()`.
  *Test:* `tests/services/test_TC_29_play_history.py::test_favourite`.
  *Breaks when:* un-hearting leaves an empty entry, or a change is not saved.

- **INV-11** (TC-29-11) — The three lists follow §4.4's filters, order, tie-breaks and limits; a key with no library track is skipped before the limit is applied and stays in the file.
  *Test:* `tests/domain/test_TC_29_history_lists.py` for the order, ties and limit on keys; `tests/services/test_TC_29_play_history.py::test_smart_list_skips_missing` for 51 played songs with one missing returning 50 tracks.
  *Breaks when:* the limit is applied before the drop, or a tie is ordered by insertion.

- **INV-12** (TC-29-12) — `PlaylistsPane` shows the three lists first, in §4.4's order. With one selected, the name cannot be edited, Delete, Up, Down and Remove are disabled, and Play emits a request that plays its shown tracks through `play_tracks`. No `PlaylistStore` method is called for it.
  *Test:* `tests/ui/test_TC_29_playlists_smart_lists.py`, with a `PlaylistStore` whose mutators raise (isolates "built-ins never reach the store" from "the buttons look disabled").
  *Breaks when:* a built-in row carries a store id, or a disabled action still fires.

- **INV-13** (TC-29-13) — A shown smart list refreshes when a play counts or a heart changes.
  *Test:* `tests/ui/test_TC_29_playlists_smart_lists.py::test_live_refresh`.
  *Breaks when:* the pane renders only on selection.

- **INV-14** (TC-29-14) — The player-mode song list shows `_fav` and `_plays`; the curation list hides both. Clicking a `_fav` cell toggles the heart once and requests no playback, on a style that activates on a single click too; sorting by either column orders by §4.5's keys. `_toggle` stays second and `_used` last.
  *Test:* `tests/ui/test_TC_29_library_columns.py`, with `play_tracks_requested` and `preview_play_requested` spies asserting no emit on the heart click.
  *Breaks when:* the heart click falls through to play-from-here, or the column order shifts an existing contract.

- **INV-15** (TC-29-15) — The Player tab's card heart shows and toggles the current track's heart, follows `current_changed` and `PlayHistory.changed`, and is disabled with no track; the Album Builder tab's card has none.
  *Test:* `tests/ui/test_TC_29_card_heart.py`.
  *Breaks when:* the heart keeps the previous track's state after a track change.

- **INV-16** (TC-29-16) — The right-click action reads "Add to favourites" or "Remove from favourites" for the clicked song and toggles it.
  *Test:* `tests/ui/test_TC_29_library_columns.py::test_context_menu`, through `_build_context_menu`.
  *Breaks when:* the label ignores the song's state.

Trust boundary: `play_history.json` is a file the user can edit. Its keys are only joined to `Library.folder` and looked up with `Library.find`, never opened, so a key such as `../x` matches no library track and shows nothing. Field values are healed by INV-2.

## 6. Failure modes

- **Crash or power loss.** Changes from the last 250 ms debounce window are lost; atomic writes keep the file whole (Spec 10).
- **Disk full on save.** `DebouncedWriter` logs the failure, as for `playlists.json`; the next change retries.
- **Quit mid-song.** The partial listen is lost (§4.2).
- **A position gap over `MAX_TICK_S` during normal play** (a stalled system) drops that span, so a play may count late. Measured on Linux only; Windows tick spacing is unmeasured.
- **A file renamed or moved alone.** Its data stays in the file under the old key and shows nowhere (owner's decision).

## 7. Tests

| Test file | Locks (each INV-N is TC-29-NN in the test markers) |
|---|---|
| `tests/persistence/test_TC_29_play_history_io.py` | INV-1, INV-2 |
| `tests/domain/test_TC_29_listen_meter.py` | INV-4, INV-5, INV-6 |
| `tests/domain/test_TC_29_history_lists.py` | INV-11 (keys) |
| `tests/services/test_TC_29_play_history.py` | INV-3, INV-7, INV-8, INV-9, INV-10, INV-11 (tracks) |
| `tests/ui/test_TC_29_playlists_smart_lists.py` | INV-12, INV-13 |
| `tests/ui/test_TC_29_library_columns.py` | INV-14, INV-16 |
| `tests/ui/test_TC_29_card_heart.py` | INV-15 |

Each test is seen failing against the code before its change. None needs real audio: the meter is pure, and the service tests emit `Player` signals directly.

## 8. Alternatives considered (and rejected)

- **Star ratings.** Rejected by the owner for a single heart.
- **Store the data in song tags.** Rejected by the owner: the app does not edit song files.
- **Key by absolute path, as playlists do.** Rejected by the owner: moving the music folder would lose everything.
- **Key by file contents (a hash).** Would survive renames, but reads every file at scan time; the owner accepted losing data on rename.
- **Keep the data in `state.json`.** Lost because `state.json` resets itself on a bad file (Spec 10 TC-10-12), which is acceptable for window state and not for history.
- **Measure heard time by wall clock while `PLAYING`.** Lost because a suspended or stalled system would add time nobody heard; position ticks only move while audio does.
- **Restart the meter on `current_changed`.** Lost because a repeat-one replay of the same song does not emit it (`PlaybackController._set_loaded`).
- **A separate History tab.** Rejected by the owner for rows at the top of Playlists.

## 9. Out of scope

- Clearing history or resetting a song's count — not yet queued.
- A "Last played" column — not yet queued.
- Grouping the song list by artist or album — MUSI-0356 Phase MP-3, which the owner held until this ships (2026-11-18).
- Rules-based smart playlists — MUSI-0356 Phase MP-5.
- MPRIS or desktop "like" controls — not yet queued.
- Importing counts from another player — not yet queued.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 (TC-29-01) | `tests/persistence/test_TC_29_play_history_io.py::test_round_trip` |
| INV-2 (TC-29-02) | `tests/persistence/test_TC_29_play_history_io.py::test_field_heal` |
| INV-3 (TC-29-03) | `tests/services/test_TC_29_play_history.py::test_load_failures` |
| INV-4 (TC-29-04) | `tests/domain/test_TC_29_listen_meter.py::test_threshold` |
| INV-5 (TC-29-05) | `tests/domain/test_TC_29_listen_meter.py::test_seek_is_not_heard` |
| INV-6 (TC-29-06) | `tests/domain/test_TC_29_listen_meter.py::test_only_playing_counts` |
| INV-7 (TC-29-07) | **Partial:** `tests/services/test_TC_29_play_history.py::test_once_per_listen`; emitted signals, not the real backend, so a backend that emits `positionChanged` differently is not caught |
| INV-8 (TC-29-08) | `tests/services/test_TC_29_play_history.py::test_source_changed` |
| INV-9 (TC-29-09) | `tests/services/test_TC_29_play_history.py::test_keying` |
| INV-10 (TC-29-10) | `tests/services/test_TC_29_play_history.py::test_favourite` |
| INV-11 (TC-29-11) | `tests/domain/test_TC_29_history_lists.py`, `tests/services/test_TC_29_play_history.py::test_smart_list_skips_missing` |
| INV-12 (TC-29-12) | `tests/ui/test_TC_29_playlists_smart_lists.py` |
| INV-13 (TC-29-13) | `tests/ui/test_TC_29_playlists_smart_lists.py::test_live_refresh` |
| INV-14 (TC-29-14) | `tests/ui/test_TC_29_library_columns.py` |
| INV-15 (TC-29-15) | `tests/ui/test_TC_29_card_heart.py` |
| INV-16 (TC-29-16) | `tests/ui/test_TC_29_library_columns.py::test_context_menu` |
| `MAX_TICK_S` against real tick spacing (§4.2) | **Partial:** measured by hand on Linux 2026-11-18; nothing re-measures it, and Windows is unmeasured |
| Glyphs render (§4.5) | nothing; checked by eye on Linux and on Windows (`ssh wintest`) before release |
| Trust boundary (§5) | `tests/services/test_TC_29_play_history.py::test_keying` includes a `../x` key that shows nothing |

## 11. Cross-doc impact

Edited in the implementation commit, so no spec describes behaviour before it ships:

- **Spec 00** §Project on-disk layout — adds `play_history.json`.
- **Spec 06** §Outputs — `Player.source_changed`.
- **Spec 10** §Files we own — a `play_history.json` row naming this spec as the schema's owner; §Paths — `play_history.json`'s keys are relative, so its absolute-path rule does not apply to them.
- **Spec 11** §Glyphs — `HEART`, `HEART_OUTLINE`, `AUTO_LIST`.
- **Spec 17** §`ui/playlists_pane.py` and §UI surface — the built-in rows.
- **Spec 18** §`ui/library_pane.py` — player mode (MP-2) and §`ui/player_pane.py` — `PlayerPane` — the two columns and the card heart.
- **Spec 25** — no text change; new strings join every catalog.
- **CHANGELOG** — one plain-language entry. **README** — the player section mentions hearts and the three lists.
- **ROADMAP** MUSI-0356 — names this spec's path; MP-3's play-count sort is delivered by `_plays`.

## 12. Cold-eyes loop log

Rows live in [`../reviews/29-play-history-loop-log.md`](../reviews/29-play-history-loop-log.md).

## 13. Resource cost

One entry per song ever counted or hearted, a few dozen bytes each; the file is at most the library's size in entries. A write happens only on a counted play or a heart change, debounced. Per `position_changed` the meter does constant work. No new dependencies.

## 14. Migration / compatibility

New file at `schema_version` 1; an absent file is an empty history. Older app versions never read it. `state.json` and `playlists.json` are unchanged.

## 15. Open questions

None.
