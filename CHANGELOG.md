# Changelog

What changed in each release of Album Builder, in plain words.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).
Releases before 0.8.0 are recorded in `ROADMAP.md`.

## [Unreleased]

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
