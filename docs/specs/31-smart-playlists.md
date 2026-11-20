<!-- ants-spec-format: 1 -->
# 31 — Smart playlists

**Status:** accepted (2026-11-20).
**Kind:** implement.
**Source:** ROADMAP MUSI-0356 Phase MP-5 (user request 2026-07-25; owner decisions 2026-11-20).
**Depends on:** 01, 10, 15, 17, 25, 29. **Amends:** 01, 10, 17.

**Layman:** Make playlists that fill themselves from rules you choose, such as "never played" or "jazz from before 1990". They update on their own as your library and listening change. "Never played" and "Recently added" are there to start with.

## 1. Goal

After this ships, the Player tab's Playlists list can hold smart playlists beside the ordinary ones. A smart playlist has a name, a set of rules, a choice of matching all or any of them, an order and an optional song limit. Its songs are worked out again whenever the library, the play history or the rules change. Rules can use title, artist, album artist, album, composer, genre, year, length, plays, date added, last played and the heart. Two smart playlists, "Never played" and "Recently added", are created on first run and can be edited or deleted like any other.

## 2. Problem

Checked 2026-11-20. The pieces this builds on:

- `Track` (`domain/track.py`) carries title, artist, album artist, composer, album, comment, lyrics, cover, length, size and ReplayGain. It reads no genre, no year and no file date. `Track.from_path` already calls `path.stat()` for the size.
- Tags are read per container: ID3 frames in `Track.from_path`, and Vorbis, MP4 and ASF names through `_VORBIS_KEYS`, `_MP4_KEYS`, `_ASF_KEYS` and `_container_text`.
- `PlayHistory.stats_for` (`services/play_history.py`) gives a track's plays, last played time and heart time as a `SongStats` (Spec 29 §4.3), and emits `changed`.
- `PlaylistsPane` (`ui/playlists_pane.py`) shows Spec 29's three self-filling lists first, each carrying a `SmartList` under `_SMART_ROLE`, then the `PlaylistStore` playlists under `_ID_ROLE`. Play on a self-filling row emits `smart_play_requested` with the shown songs, and `MainWindow._on_play_smart_list` plays them.
- `PlaylistStore` (`services/playlist_store.py`) owns `playlists.json` (Spec 17). `load_playlists` raises on a newer `schema_version`, so a store that changed that file's version would show an older build no playlists at all.

## 3. Scope decisions (agreed with the user)

Owner answers, 2026-11-20, in this session:

- **"Date added" is the song file's modified date.** It works at once for every song. A tag editor that re-saves a file makes it look newly added.
- **Genre and year are read from the songs**, so rules can use them.
- **A song with several genres matches a genre rule on any one of them**: "Genre is Jazz" matches a song tagged Rock and Jazz.
- **Rules combine by one switch per playlist: all of them, or any of them.** No nested groups.
- **"Never played" and "Recently added" are editable starters**, not fixed built-ins. They can be renamed, edited or deleted.

Author's calls, each open to the owner:

- **Smart playlists live in their own file**, `.album-builder/smart_playlists.json`. `playlists.json` keeps schema 1, so an older build still reads the ordinary playlists.
- **A smart playlist this build cannot read is kept, never dropped or rewritten.** It shows greyed, plays nothing and cannot be edited, only deleted. This covers a hand edit and an entry a newer build wrote without raising `schema_version`; a newer `schema_version` is §4.3's case.
- **"Recently added" means the last 30 days**, newest first. **"Never played"** is in title order. Neither has a limit.
- **Starters are created only when `smart_playlists.json` does not exist.** Deleting them sticks; a corrupt file does not bring them back.
- **Smart playlists show in the Player tab's Playlists list only.** "Add to playlist" menus never list them: their songs come from rules.
- **No timer.** A date rule ("in the last 30 days") is worked out again whenever the list is shown or played, which keeps it current without a clock.

## 4. Design

### 4.1 New song fields (amends Spec 01)

`Track` gains three fields, appended after `replaygain_album_gain` with defaults so existing constructors still work:

```python
genre: str = ""                      # every genre value, joined with "; "
year: int | None = None
modified: datetime | None = None     # UTC-aware, from the stat() already made
```

| Container | Genre | Year |
|---|---|---|
| ID3 | `TCON`, through mutagen's `TCON.genres`, which turns `(17)` into `Rock` | `TDRC` (mutagen reads an ID3v2.3 `TYER` as `TDRC`) |
| Vorbis (FLAC, Ogg, Opus) | `genre` | `date` |
| MP4 | `\xa9gen` | `\xa9day` |
| ASF | `WM/Genre` | `WM/Year` |

Each genre value is stripped of spaces and a leading `/`: mutagen reads an ID3v2.3 `(17)/Jazz` as `Rock`, `/Jazz`. `year` is the first run of four digits in the tag's text, kept when it is between 1000 and 9999; anything else is `None`. So `1994-05-01` and `1994` both give 1994. MP4's numeric `gnre` atom is not read (§9). A missing track (`Track._missing`) has `genre ""`, `year None`, `modified None`.

### 4.2 The rule model (`domain/smart_playlist.py`, pure, no Qt)

```python
class Field(StrEnum):
    TITLE = "title"; ARTIST = "artist"; ALBUM_ARTIST = "album_artist"
    ALBUM = "album"; COMPOSER = "composer"; GENRE = "genre"
    YEAR = "year"; DURATION = "duration"; PLAYS = "plays"
    DATE_ADDED = "date_added"; LAST_PLAYED = "last_played"
    FAVOURITE = "favourite"

class Op(StrEnum):
    CONTAINS = "contains"; NOT_CONTAINS = "not_contains"
    IS = "is"; IS_NOT = "is_not"; STARTS_WITH = "starts_with"
    GT = "gt"; LT = "lt"
    IN_LAST_DAYS = "in_last_days"; NOT_IN_LAST_DAYS = "not_in_last_days"

@dataclass(frozen=True)
class Rule:
    field: Field
    op: Op
    value: str | int | bool

@dataclass(frozen=True)
class Order:
    by: Field          # any Field but FAVOURITE
    descending: bool = False

@dataclass(frozen=True)
class SmartPlaylist:
    id: str            # uuid4().hex
    name: str
    match_all: bool
    rules: tuple[Rule, ...]
    order: Order
    limit: int | None  # 1..9999, or None for no limit

def matches(rule: Rule, track: Track, stats: SongStats, now: datetime) -> bool: ...
def songs(pl: SmartPlaylist, candidates: Iterable[tuple[Track, SongStats]],
          now: datetime) -> list[Track]: ...
```

**Which operators go with which field, and the value each takes:**

| Fields | Operators | Value | A song with no value |
|---|---|---|---|
| title, artist, album artist, album, composer, genre | contains, not contains, is, is not, starts with | text | the value `Track` holds: title falls back to the file name, artist to "Unknown artist", album artist to the artist; the others are `""` |
| year, duration (seconds), plays | is, is not, gt, lt | whole number `>= 0` | year `None` matches `is not` only |
| date added, last played | in last days, not in last days | whole number of days, 1 to 36500 | matches `not in last days` only |
| favourite | is | `true` or `false` | not hearted is `false` |

- **Text** compares `casefold()` of both sides, as `Library.search` does. Plain substring and prefix tests; no pattern syntax.
- **Genre** is tested one value at a time: `genre.split("; ")`, or `[""]` when the genre is empty. `contains`, `is` and `starts with` match when any value does; `not contains` and `is not` match when no value does.
- **Duration** compares `int(track.duration_seconds)`.
- **Dates:** `in last days` with `n` matches a date at or after `now - n days`; `not in last days` is its exact opposite, so a song with no date (never played, or no file date) matches it.
- **Plays and last played** come from `PlayHistory.stats_for`; a song with no history has 0 plays and no last played.

**`songs`** keeps the candidates that match all rules (`match_all`) or at least one (`not match_all`). A playlist with no rules matches every candidate. It then sorts by `order.by` (text by `casefold()`; a missing year, date or empty text last whichever the direction), ties by title `casefold()`, then by path, and cuts to `limit`.

### 4.3 `smart_playlists.json` (this spec owns the bytes)

```json
{
  "schema_version": 1,
  "smart_playlists": [
    {
      "id": "3f2a...hex",
      "limit": null,
      "match": "all",
      "name": "Recently added",
      "order": {"by": "date_added", "descending": true},
      "rules": [{"field": "date_added", "op": "in_last_days", "value": 30}]
    }
  ]
}
```

| Field | Type | Constraint |
|---|---|---|
| `id` | string | non-empty, unique in the file |
| `name` | string | non-empty after strip |
| `match` | string | `"all"` or `"any"` |
| `rules` | array of objects | each `field`/`op`/`value` per the §4.2 table; a bool is not a whole number |
| `order.by` | string | a `Field` value other than `favourite` |
| `order.descending` | bool | |
| `limit` | int or `null` | 1 to 9999; a bool is not an int |

Spec 10 §Encoding rules apply (sorted keys, 2-space indent). Writes are atomic, through a `DebouncedWriter` (250 ms).

**An entry that breaks any constraint, or holds a key the table does not name, is unreadable.** It is kept as its raw JSON value, in place, and written back unchanged on every save. In memory it is an `UnreadableSmartPlaylist(raw, id)` with a session-only id. It matches no songs. Rules are never dropped one by one, because with `match: "all"` a dropped rule would quietly widen the list.

**Load.** Absent file: no smart playlists, plus the starters (§4.4). A file that does not parse, is not an object, lacks `schema_version` or has a non-array `smart_playlists`: `load_smart_playlists` raises. A newer `schema_version` raises `SchemaTooNewError`. The store handles both as `PlayHistory` does (Spec 29 §4.1 Load): corrupt sets `load_failed` and the first save renames the file to `smart_playlists.json.corrupt.bak`; too new sets `read_only` and the file is never written that run. `MainWindow` shows a toast for each.

### 4.4 `services/smart_playlist_store.py`

```python
class SmartPlaylistStore(QObject):
    changed = pyqtSignal()
    load_failed: bool
    read_only: bool
    def __init__(self, project_root: Path, library_watcher: LibraryWatcher,
                 history: PlayHistory, parent: QObject | None = None): ...
    def playlists(self) -> list[SmartPlaylist | UnreadableSmartPlaylist]: ...
    def create(self, pl: SmartPlaylist) -> None: ...
    def update(self, pl: SmartPlaylist) -> None: ...   # replaces the entry with pl.id
    def rename(self, playlist_id: str, name: str) -> None: ...
    def delete(self, playlist_id: str) -> None: ...
    def songs(self, playlist_id: str) -> list[Track]: ...
    def songs_for(self, pl: SmartPlaylist) -> list[Track]: ...  # saved or not
    def flush(self) -> None: ...
```

`songs_for` passes `smart_playlist.songs` every track in `library_watcher.library()` with its `history.stats_for`, and `datetime.now(UTC)`. `songs(id)` is `songs_for` on the stored entry; an unreadable entry gives `[]`. `update` and `rename` on an unreadable entry raise `ValueError`, as `rename` does on a name empty after strip.

**Starters.** When the file was absent at load, the store creates, in this order, and schedules a write:

- **Never played** (`tr`): match all; `plays is 0`; order title ascending; no limit.
- **Recently added** (`tr`): match all; `date added in last days 30`; order date added descending; no limit.

The names are translated once, when created, and stored as text.

`MainWindow` builds the store after `PlayHistory`, shows the toasts and calls `flush()` in `closeEvent`.

### 4.5 Playlists list (amends Spec 17 §UI surface)

Rows, top to bottom: Spec 29's three lists; the smart playlists in file order, each prefixed with `Glyphs.AUTO_LIST`; then the ordinary playlists. A smart row carries its id under a new `_SMART_ID_ROLE`; it never carries `_ID_ROLE` or `_SMART_ROLE`. `MainWindow` hands the pane the store with a new `set_smart_store(store: SmartPlaylistStore)`, as it does `set_play_history`.

For a smart row:

- Selecting it shows its songs (`SmartPlaylistStore.songs`) in the tracks list.
- Double-click renames, as for an ordinary playlist; `MainWindow` catches a `ValueError` and re-renders, as Spec 17 does. The edit starts from the stored name without the glyph, and `rename_smart_committed` carries the name without it. Delete asks first, as Spec 17 does.
- Up, Down and Remove are disabled: the rules set the order.
- **Play** works the songs out again (`SmartPlaylistStore.songs`), shows them, and emits `smart_play_requested` with them, the same signal Spec 29's lists use; an empty list toasts and leaves the queue alone.
- The shown songs refresh on `SmartPlaylistStore.changed`, `PlayHistory.changed`, a library change and each time the row is selected.
- An unreadable row shows greyed, with the tooltip "This smart playlist can't be read by this version"; it shows no songs, and only Delete is enabled.

New buttons, both with accessible names: **New smart playlist** (always enabled) and **Edit rules** (enabled on a readable smart row). The id-carrying signals of Spec 17 never fire for a smart row; new signals `create_smart_requested`, `edit_smart_requested(id)`, `rename_smart_committed(id, name)` and `delete_smart_requested(id)` carry them.

### 4.6 Rule editor (`ui/smart_playlist_dialog.py`)

```python
class SmartPlaylistDialog(QDialog):
    def __init__(self, existing: SmartPlaylist | None,
                 count: Callable[[SmartPlaylist], int], parent=None): ...
    def result_playlist(self) -> SmartPlaylist: ...   # after accept
```

Contents, top to bottom: a name box; "Match [all | any] of these rules"; one row per rule (field, operator, value, a remove button); **Add rule**; "Order by [field] [descending]"; "Limit to [n] songs" with a check box and a number box, 1 to 9999; a live "N songs match" line from `count`; OK and Cancel.

- The operator list follows the field, per the §4.2 table. Changing the field resets the operator and value when the old ones do not fit.
- The value editor follows the field: a text box, a number box, a days box (1 to 36500), "minutes : seconds" boxes for duration, or Yes/No for favourite.
- OK is disabled while the name is empty after strip.
- Opening an existing playlist and pressing OK with no change returns an equal `SmartPlaylist`, id included.
- Every control is reachable by keyboard and has an accessible name. Every string goes through `tr()` and into each shipped catalog (Spec 25, TC-25-03).

`MainWindow` opens it for **New smart playlist** (then `store.create`) and **Edit rules** (then `store.update`), passing `count` as `len(store.songs_for(pl))`.

### 4.7 Trust boundary

`smart_playlists.json` is hand-editable. Its strings are only compared with `casefold()`, substring and prefix tests, never compiled as patterns or run. Numbers are range-checked on load (§4.3); a value outside its range makes the entry unreadable, so no unchecked value reaches `matches`.

## 5. Invariants

Each *Test:* names the rule its fixture isolates.

- **INV-1** (TC-31-01) — `Track.from_path` reads genre and year from ID3, Vorbis (FLAC), MP4 and ASF files per §4.1's table; several genre values join with `"; "`; an ID3v2.3 `(17)/Jazz` gives `Rock; Jazz`; a year tag of `1994-05-01` gives 1994, and `abcd` gives `None`; a file with neither tag gives `""` and `None`.
  *Test:* `tests/domain/test_TC_31_track_tags.py`, one tagged file per container, written with mutagen in `tmp_path`.
  *Breaks when:* a container's genre or year key is wrong, a genre value keeps its `/`, or the year is not cut to four digits.

- **INV-2** (TC-31-02) — `Track.modified` equals the file's `st_mtime` as a UTC-aware datetime; a missing track has `None`.
  *Test:* `tests/domain/test_TC_31_track_tags.py::test_modified`, setting the mtime with `os.utime` to a known instant (isolates the field from "now").
  *Breaks when:* the time is naive, local, or taken from somewhere other than the file.

- **INV-3** (TC-31-03) — `matches` follows §4.2's table for every field and operator: text casefolded (`"JAZZ"` contains `"jazz"`); a song with genre `Rock; Jazz` matches `genre is Jazz` and not `genre is_not Jazz`, while a title `Rock; Jazz` does not match `title is Jazz`; a song with no year matches `year is_not 1990` and no other year rule; a never-played song matches `last_played not_in_last_days 30` and not `in_last_days 30`; a date exactly `n` days before `now` is in the last `n` days.
  *Test:* `tests/domain/test_TC_31_rules.py`, table-driven, with a fixed `now`.
  *Breaks when:* a comparison is case-sensitive, genre `is` tests the joined text instead of each value, a missing value matches a comparison, or the day boundary is off by one.

- **INV-4** (TC-31-04) — `songs` with `match_all` keeps songs matching every rule; with any, songs matching one; with no rules, every candidate.
  *Test:* `tests/domain/test_TC_31_rules.py::test_match`, two rules each matched by a different song (isolates all-vs-any from the rules themselves).
  *Breaks when:* the switch is ignored, or an empty rule list matches nothing.

- **INV-5** (TC-31-05) — `songs` orders by `order.by` in the chosen direction, puts missing values last either way, breaks ties by title then path, and applies `limit` after ordering.
  *Test:* `tests/domain/test_TC_31_rules.py::test_order_limit`, a limit of 2 over 4 songs where the first 2 by path are not the first 2 by order (isolates limit-after-sort).
  *Breaks when:* the limit cuts before sorting, or a missing year sorts first.

- **INV-6** (TC-31-06) — `save_smart_playlists` then `load_smart_playlists` returns equal playlists; the file has sorted keys and 2-space indent.
  *Test:* `tests/persistence/test_TC_31_smart_io.py::test_round_trip`.
  *Breaks when:* a field is lost or renamed on the way through.

- **INV-7** (TC-31-07) — An entry with an unknown key, an unknown field, an unknown operator, an operator that does not fit its field, a value of the wrong type or range, a numeric rule value or `limit` of `true`, or a missing `id` loads as `UnreadableSmartPlaylist`; it is written back equal to its raw JSON on the next save, while a readable neighbour edited in the same run is saved with its edit.
  *Test:* `tests/persistence/test_TC_31_smart_io.py::test_unreadable_kept`, one case per bad value beside one valid entry.
  *Breaks when:* a bad entry is dropped, partly kept, or rewritten.

- **INV-8** (TC-31-08) — A corrupt file sets `load_failed` and the first save leaves `smart_playlists.json.corrupt.bak` holding the original bytes; a newer `schema_version` sets `read_only` and the file is byte-identical after a create, an edit and `flush()`.
  *Test:* `tests/services/test_TC_31_smart_store.py::test_corrupt` and `::test_too_new`.
  *Breaks when:* a bad file is overwritten without a backup, or a newer file is written.

- **INV-9** (TC-31-09) — With no `smart_playlists.json`, the store holds "Never played" and "Recently added" with §4.4's rules and writes them; with a file holding an empty list, it holds none; with a corrupt file, it holds none.
  *Test:* `tests/services/test_TC_31_smart_store.py::test_starters`, three cases.
  *Breaks when:* deleted starters come back, or a corrupt file brings them back.

- **INV-10** (TC-31-10) — `SmartPlaylistStore.songs` returns only tracks in the current library, uses each track's `PlayHistory` stats, and returns `[]` for an unreadable entry.
  *Test:* `tests/services/test_TC_31_smart_store.py::test_songs`, with a hearted song and a `favourite is true` rule.
  *Breaks when:* the store reads stale stats or a song that left the library.

- **INV-11** (TC-31-11) — In `PlaylistsPane`, smart rows sit after Spec 29's three and before the ordinary playlists; on a smart row Up, Down and Remove are disabled and Edit rules is enabled; Play emits `smart_play_requested` with the store's songs at that moment; `play_requested`, `rename_committed` and `delete_requested` never fire for it; an unreadable row enables Delete only.
  *Test:* `tests/ui/test_TC_31_playlists_pane.py`, with signal spies.
  *Breaks when:* a smart row reaches `PlaylistStore` through an id signal, or is reorderable.

- **INV-12** (TC-31-12) — In `SmartPlaylistDialog`, picking a text field offers only the five text operators and a date field only the two date ones; OK is disabled with an empty name; an existing playlist opened and accepted unchanged comes back equal.
  *Test:* `tests/ui/test_TC_31_smart_dialog.py`.
  *Breaks when:* an operator that does not fit can be chosen, or the dialog changes a playlist nobody edited.

- **INV-13** (TC-31-13) — "Add to playlist" menus list only `PlaylistStore` playlists, never a smart playlist.
  *Test:* `tests/ui/test_TC_31_add_menu.py`, an offscreen `MainWindow` with one smart playlist in the store, reading the library pane's menu (the menu lists what `MainWindow` passes it).
  *Breaks when:* `MainWindow` passes a smart playlist to the menu, so it appears as a target a song could be added to.

## 6. Failure modes

- **A tag editor re-saves a file:** its date added becomes today and it shows in "Recently added". Accepted (§3).
- **A copy tool keeps old file dates** (`cp -p`, `rsync -a`): newly copied songs do not show in "Recently added". Accepted (§3).
- **A rule matches no songs:** the list shows empty; Play toasts and leaves the queue alone.
- **The library folder is unreadable:** every smart playlist is empty until the next good scan, as the library itself is (Spec 01).
- **The file is written by a newer build:** this build shows no smart playlists, never writes the file, and says so in a toast (§4.3).

## 7. Tests

- `tests/domain/test_TC_31_track_tags.py` — INV-1, INV-2.
- `tests/domain/test_TC_31_rules.py` — INV-3, INV-4, INV-5.
- `tests/persistence/test_TC_31_smart_io.py` — INV-6, INV-7.
- `tests/services/test_TC_31_smart_store.py` — INV-8, INV-9, INV-10.
- `tests/ui/test_TC_31_playlists_pane.py` — INV-11.
- `tests/ui/test_TC_31_add_menu.py` — INV-13.
- `tests/ui/test_TC_31_smart_dialog.py` — INV-12.

Each is written and seen failing before its code. UI tests run offscreen.

## 8. Alternatives considered (and rejected)

- **Store smart playlists in `playlists.json`.** One file, but the schema would go to 2, and Spec 17's `load_playlists` makes an older build show no playlists at all for a newer file.
- **Drop an unreadable rule and keep the rest.** Under "match all" that silently widens the list; a playlist meant to hold ten songs could start playing the whole library.
- **Nested rule groups.** Rejected by the owner: the editor gets much harder for little gain.
- **Record when the app first sees a song.** Rejected by the owner: every existing song would get the same date.
- **Fixed built-in starters beside Spec 29's lists.** Rejected by the owner: they should be editable.
- **A clock that refreshes date rules at midnight.** Re-working the list on show and on play keeps it current with no timer.

## 9. Out of scope

- Genre, Year and Date added columns in the song list, and searching by genre — not asked for; not yet queued.
- MP4's numeric `gnre` atom — rare in practice; not yet queued.
- Saving a smart playlist's current songs as an ordinary playlist — not asked for.
- Smart playlists in the Album Builder tab — not asked for.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 (TC-31-01) | `tests/domain/test_TC_31_track_tags.py` |
| INV-2 (TC-31-02) | `tests/domain/test_TC_31_track_tags.py::test_modified` |
| INV-3 (TC-31-03) | `tests/domain/test_TC_31_rules.py` |
| INV-4 (TC-31-04) | `tests/domain/test_TC_31_rules.py::test_match` |
| INV-5 (TC-31-05) | `tests/domain/test_TC_31_rules.py::test_order_limit` |
| INV-6 (TC-31-06) | `tests/persistence/test_TC_31_smart_io.py::test_round_trip` |
| INV-7 (TC-31-07) | `tests/persistence/test_TC_31_smart_io.py::test_unreadable_kept` |
| INV-8 (TC-31-08) | `tests/services/test_TC_31_smart_store.py::test_corrupt`, `::test_too_new` |
| INV-9 (TC-31-09) | `tests/services/test_TC_31_smart_store.py::test_starters` |
| INV-10 (TC-31-10) | `tests/services/test_TC_31_smart_store.py::test_songs` |
| INV-11 (TC-31-11) | `tests/ui/test_TC_31_playlists_pane.py` |
| INV-12 (TC-31-12) | `tests/ui/test_TC_31_smart_dialog.py` |
| INV-13 (TC-31-13) | `tests/ui/test_TC_31_add_menu.py` |
| Trust boundary (§4.7) | **Partial:** INV-7 shows out-of-range values never load; that no value is used as a pattern is checked only by reading `domain/smart_playlist.py` |
| The editor fits and reads well in every language (§4.6) | nothing; checked by eye in English and one right-to-left language |

## 11. Cross-doc impact

Edited in the implementation commit:

- **Spec 01** §Data shape and §Test contract — `genre`, `year`, `modified`, citing this spec's TC-31-01 and TC-31-02.
- **Spec 10** — `.album-builder/smart_playlists.json` joins the files table, naming this spec as owner of the bytes.
- **Spec 17** §UI surface — smart rows and the two new buttons.
- **Spec 25** — no text change; new strings join every catalog.
- **CHANGELOG** — one plain-language entry. **README** — the player section mentions smart playlists.
- **ROADMAP** MUSI-0356 — names this spec's path.

## 12. Cold-eyes loop log

Rows live in [`../reviews/31-smart-playlists-loop-log.md`](../reviews/31-smart-playlists-loop-log.md).

## 13. Resource cost

Each refresh runs every rule over every song: one pass over the library per shown or played smart playlist, with no disk access, because tags and stats are already in memory. Reading genre and year adds two tag lookups per file to a scan that already opens every file.

## 14. Migration / compatibility

`smart_playlists.json` is new; a build without it ignores the file. `playlists.json` and `play_history.json` are unchanged. The new `Track` fields have defaults, so nothing that builds a `Track` breaks.

## 15. Open questions

None.
