# Versioning overrides — Album Builder

Answers the two questions `~/.claude/standards/versioning.md` leaves to each
project: which surfaces count as breaking (§ 3) and what makes this project
`1.0` (§ 4). Everything else follows that standard unchanged, including § 4's
`0.x` levels: a breaking change bumps the MINOR, anything else bumps the PATCH.

**Status:** agreed by the owner (2026-09-28).

## What makes it 1.0

MAJOR stays `0` until every sign of success in [`docs/discovery.md`](../discovery.md)
(S1–S7) has a passing check, recorded on a roadmap item that names that sign.

## Breaking surfaces

A release that makes any of these stop working for an existing user is
breaking. "Stop working" includes the app refusing or resetting a file, losing
anything stored in it, or changing a layout that other tools rely on.
Upgrading an older file forward on load, with nothing lost, is not breaking
for any file on this list. `persistence/schema.py` runs these upgrades for
albums, app state and playlists.

- **Saved albums** — `Albums/<album>/album.json`, and the `.approved` marker
  (`persistence/album_io.py`). An older album must still open.
- **Settings** — `settings.json` in the config folder, and its keys
  (`persistence/settings.py`), including the chosen music folder.
- **App state and saved playlists** — `.album-builder/state.json` and
  `.album-builder/playlists.json` (`persistence/state_io.py`,
  `persistence/playlist_io.py`).
- **The approved album folder** — the numbered `NN - Title.ext` links,
  `playlist.m3u8` and the `reports/` files (`services/export.py`,
  `services/report.py`). People open these in other players and share them.
- **Lyrics files** — `<song>.lrc` beside each song, and the LRC format
  (`persistence/lrc_io.py`).
- **Command-line options** — `--version` and `--selftest` (`app.py`). The
  release workflows call both.
- **Keyboard shortcuts** — those listed in Help > Keyboard shortcuts.
- **Desktop integration** — the MPRIS bus name `org.mpris.MediaPlayer2.albumbuilder`
  (`services/mpris.py`) and the `album-builder` desktop-file name.

A surface missing from this list is still a surface: if users rely on it and
it breaks, the release was breaking (`versioning.md` § 3).

## Cold-eyes loop log

Kept in [`docs/reviews/C-20260928-versioning-overrides.md`](../reviews/C-20260928-versioning-overrides.md).
