# Changelog

What changed in each release of Album Builder, in plain words.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).
Releases before 0.8.0 are recorded in `ROADMAP.md`.

## [Unreleased]

## [0.9.5] - 2026-10-08

**Theme:** Linux download is back.

### Fixed

- **The Linux download (AppImage) is back.** (MUSI-0387)
  The previous release came out with only the Windows download, because
  a file the Linux build needs had been renamed by the project that
  provides it. The build now finds the current file by itself, so the
  same thing should not stop a Linux download again. This release has
  everything the previous one added, including Add music.

## [0.9.4] - 2026-10-08

**Theme:** Add music.

### Added

- **Add music: drag songs onto the window, or use File → Add Music...** (MUSI-0371)
  Songs and whole folders (with their subfolders) are copied into your
  music folder and show up in the library straight away. Your original
  files are left exactly where they were. If a song has the same name as
  one you already have, both are kept: the new copy gets a number, like
  "Song (2).mp3", and a message tells you which ones.

### Fixed

- **Going back to an older copy of the app no longer wipes your settings.** (MUSI-0384)
  If a newer version of Album Builder saved your settings or window
  layout, an older version used to reset them or read them wrongly. Now
  it uses its own defaults for that session and leaves the newer files
  exactly as they were, so the newer version finds them intact.

- **On Windows, the "Album Builder" and "Player" tabs are readable again.** (MUSI-0382)
  They showed as white boxes with faint text. They now follow the
  chosen colour theme, like the rest of the window.

## [0.9.3] - 2026-09-28

**Theme:** The window fits smaller screens.

### Fixed

- **The window now fits on smaller screens.** (MUSI-0381)
  On a 1280-pixel-wide screen the window used to spill off the right
  edge, hiding the menu and the tabs. It now fits, and a window saved on
  a bigger screen opens inside the current one.

## [0.9.2] - 2026-09-28

**Theme:** The Windows download works again.

### Fixed

- **The Windows download no longer closes itself right after starting.** (MUSI-0379)
  On Windows the app crashed the first time it saved its settings, so
  it vanished a moment after opening. It now saves normally. Linux was
  not affected.

## [0.9.1] - 2026-09-28

**Theme:** Better translations, and a smoother shutdown.

### Fixed

- **Closing the app no longer waits on your desktop's media controls.** (MUSI-0367)
  The app now disconnects from the desktop's play/pause controls before
  it stops the music, so closing it cannot get stuck there.

- **The "WhisperX not installed" message now appears in your language.** (MUSI-0370)
  It was the one message still shown in English. The install help
  still appears once, the first time lyrics syncing needs it.

- **Better wording in every translated language.**
  A second proofread corrected words that read oddly or wrongly: the
  exported song links no longer share a name with keyboard shortcuts,
  Afrikaans says "pouseer" for pause, and Arabic calls a composer a
  composer. In Arabic and Hebrew, the lyrics status line now reads right
  to left. The translations are still AI drafts awaiting native
  speakers.

## [0.9.0] - 2026-09-28

**Theme:** More languages including Arabic and Hebrew, a Player-tab library, and choosing your music folder.

### Added

- **Choose your music folder from inside the app.** (part of MUSI-0357)
  Use File > Choose Music Folder..., and your library reloads straight
  away. When no music is found, the library shows a friendly message
  with a button to pick the right folder, so a fresh install no longer
  opens to an empty window. No more editing settings files by hand.

- **The app now speaks eight languages, including Arabic and Hebrew.** (MUSI-0368)
  English, Afrikaans, Arabic, Hebrew, Spanish, French, German and
  Portuguese. It follows your computer's language, or choose one under
  View > Language and reopen the app. Arabic and Hebrew mirror the whole
  window right to left; the play controls stay the usual way round.
  Approval reports come out in the chosen language too. The translations
  are AI drafts, not yet checked by native speakers.

- **The Player tab now has its own music library.** (part of MUSI-0356)
  Search and browse your songs right in the Player, without switching
  to the Album Builder tab. Double-click a song, or press Enter, to play
  from there. Right-click for play next, add to queue and playlists.
  Both tabs show the same songs and update together. The song details
  now read Title, Artist, Album, like most music players.

- **You can now bring back an album you deleted.** (part of MUSI-0357)
  Choose File > Restore Deleted Album, pick it from the list, and it
  returns exactly as it was, with its tracks, order and reports.

### Fixed

- **No more dark boxes behind text.**
  Song details, headings, the lyrics status line and the time readouts
  now sit cleanly on their panel instead of each drawing a dark strip.

## [0.8.1] - 2026-09-25

**Theme:** The Linux download is back, plus display fixes.

### Fixed

- **The Linux download is back.**
  The 0.8.0 Linux AppImage failed to build because a part it downloads
  had been replaced upstream, so 0.8.0 shipped with only the Windows
  download. This release has both.

- **Song titles now show in the library.** (MUSI-0364)
  The Title column shrank to nothing unless the window was very wide.
  It now always has room, and the Composer column gives way instead.

- **Album-order rows no longer show their text twice.** (MUSI-0365)
  Each track's number and name appeared twice, overlapping. Now each
  row reads once.

- **Small buttons now show their symbols.** (MUSI-0366)
  The play button beside each album-order track, the - and + buttons
  for the track count, and the x that closes a notification were blank
  or cut to a thin line. They now show properly.

## [0.8.0] - 2026-09-25

**Theme:** Many more music file types now work properly.

### Added

- **Five more kinds of music file.** The library now picks up AAC,
  AIFF (`.aiff` and `.aif`), Ogg audio (`.oga`) and Windows Media
  (`.wma`) files, as well as the types it already read. (MUSI-0358)
- **A clearer drag when reordering an album.** The track you are
  dragging fades to half strength, and a line in your theme's colour
  shows exactly where it will land. (MUSI-0361)

### Fixed

- **Song details now show for every file type, not just MP3.** FLAC,
  Ogg, Opus, M4A, WMA, WAV and AIFF files used to show "Unknown
  artist" with no title or album, even when the file had them. They
  now show the real title, artist, album and composer. AAC files are
  the one exception: that format has no place to store song details,
  so they show the file name instead. (MUSI-0359)
- **Album artwork now shows for every file type.** Cover pictures
  stored inside FLAC, Ogg, Opus, M4A, WMA, WAV and AIFF files appear in
  the app, the approval report and your desktop's media controls.
  Before, only MP3 artwork appeared. (MUSI-0359, MUSI-0362)
- **Volume levelling now works for every file type.** If you use
  volume levelling (ReplayGain), FLAC, Ogg, Opus, M4A, WMA, WAV and
  AIFF tracks are now evened out too, instead of playing louder or
  quieter than the rest of the album. Before, only MP3 was.
  (MUSI-0359, MUSI-0363)
- **Songs without any tags no longer show a length of 0:00.** A file
  with no song details at all now shows its real length, so exported
  playlists and sorting by length are correct. (MUSI-0360)
