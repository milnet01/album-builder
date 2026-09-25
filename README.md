# Album Builder

Album Builder helps you put an album together from a folder of songs.
Pick the tracks you want, drag them into order, listen through with the
lyrics scrolling along, and when you are happy, approve it. Approving
makes a ready-to-share album folder: a playlist, the tracks numbered in
order, and a printable report.

It is a desktop app for Linux (built on KDE Plasma), with a Windows
download too.

## Status

**v0.8.0 (2026-09-25): many more music file types now work properly.**
FLAC, Ogg, Opus, M4A, WMA, WAV and AIFF files now show their song
details, artwork and volume levelling, not just MP3. AAC, AIFF, `.oga`
and WMA files are now picked up too. Dragging a track to reorder an
album is clearer.

See [`CHANGELOG.md`](CHANGELOG.md) for what changed in each release.

## What it does

- **Builds albums.** Tick the songs you want from your library, set how
  many tracks the album should have, and drag them into order. Keep as
  many draft albums as you like and switch between them.
- **Approves and exports.** Approving an album creates its own folder
  with a playlist file (`.m3u`), the songs numbered in album order, and
  a PDF and web-page report. There is also a shorter "artist view"
  report for sharing.
- **Shows what is already used.** A badge marks songs that are already
  on an approved album, so you don't use one twice by accident.
- **Plays music.** A separate player tab plays your whole library, with
  a play queue, shuffle, repeat and saved playlists.
- **Shows lyrics in time with the song.** Lyrics files (`.lrc`) scroll
  along as the song plays. The app can also line up plain lyrics with
  the song automatically; that part is an optional extra (see below).
- **Fits into your desktop.** Play, pause and skip from your desktop's
  media controls, your keyboard's media keys, the lock screen or the
  system tray icon.
- **Evens out volume.** Turn on *Playback → Volume Levelling* and songs
  that carry ReplayGain tags play at a matched loudness.
- **Has themes.** Choose a light or dark look under *View → Theme*.
- **Stays up to date.** Add or remove songs in your music folder and the
  library updates by itself. Your albums and choices are remembered
  between sessions.

### Music files it reads

MP3, M4A, AAC, FLAC, Ogg (`.ogg` and `.oga`), Opus, WAV, AIFF (`.aiff`
and `.aif`) and WMA.

Every type except AAC can carry the song's title, artist, album,
artwork and volume-levelling tags, and the app reads them all. AAC files
have nowhere to store those details, so they show the file name instead.

## Where your music and albums live

- **Your music** is read from `~/Music` unless you choose another
  folder. (Run from this source folder, it reads the `Tracks` folder
  here instead.)
- **Your albums** are saved in an `Albums` folder. Set `albums_folder`
  below so they always land in the same place.

To choose your own folders, put their paths in
`~/.config/album-builder/settings.json`:

```json
{
  "tracks_folder": "/path/to/your/songs",
  "albums_folder": "/path/to/where/albums/go/Albums"
}
```

Album Builder never renames, moves or changes your music files. The
one thing it adds beside them is a lyrics file (`.lrc`) when it lines
up lyrics for a song.

## Download for Linux (AppImage) - nothing to install

This is the quickest way to run Album Builder on Linux.

1. Download the `.AppImage` file from the
   [latest release](https://github.com/milnet01/album-builder/releases/latest).
2. Make it runnable and start it:

   ```bash
   chmod +x AlbumBuilder-*-x86_64.AppImage
   ./AlbumBuilder-*-x86_64.AppImage
   ```

Everything the app needs comes inside that one file. It runs on most
Linux systems from 2022 onward (it needs glibc 2.35 or newer).

If something goes wrong:

- **The window will not open, with a `Qt xcb` error:** install your
  system's basic X11 and OpenGL libraries. Any normal desktop already
  has them.
- **The file will not start at all (no FUSE):** run it as
  `./AlbumBuilder-*-x86_64.AppImage --appimage-extract-and-run`.
- **A `GLIBC_2.35 not found` message:** your system is older than the
  app supports.

Automatic lyric alignment is not included in the AppImage, because it
is very large. Use the full install below if you want it.

## Download for Windows - nothing to install

1. Download `AlbumBuilder-<version>-windows-x64.zip` from the
   [latest release](https://github.com/milnet01/album-builder/releases/latest).
2. Unzip it and double-click `AlbumBuilder.exe`.

It needs 64-bit Windows 10 or newer. The app is not code-signed yet, so
the first time you run it Windows shows "Windows protected your PC".
Click **More info**, then **Run anyway**.

Automatic lyric alignment is not included here either.

## Full install (openSUSE Tumbleweed + KDE Plasma)

This copies Album Builder into `~/.local/share/album-builder` and adds
it to your K Menu. Run it again after updating this folder to install
the newer version.

```bash
./install.sh
```

Then open it from the K Menu under **Multimedia → Album Builder**, or
type `album-builder` in a terminal.

### What the installer expects to find

- **Python 3.11 or newer** (`zypper install python311`).
- **Sound output** (PipeWire, PulseAudio or ALSA). Any desktop already
  has this. No extra codec packages are needed: the app brings its own
  audio decoder.
- **The libraries PDF reports need**: Pango, HarfBuzz and fontconfig
  (`zypper install pango harfbuzz fontconfig`). On Debian or Ubuntu:
  `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1`. If
  reports fail to render, WeasyPrint's
  [installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)
  lists what each system needs. If the PDF part cannot load, the app
  still saves the web-page report.
- **Optional:** `desktop-file-utils`, and one of Inkscape, `rsvg-convert`
  or `cairosvg` for the menu icon. The installer falls back to
  `cairosvg` if none is present.

## Uninstall

```bash
./uninstall.sh           # removes the app, keeps your settings
./uninstall.sh --purge   # also removes ~/.config/album-builder and ~/.cache/album-builder
```

## For developers

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                                  # run the tests
PYTHONPATH=src .venv/bin/python -m album_builder  # run from source
```

`PYTHONPATH=src` is needed because the package is not installed into
`.venv`. `./local-CI.sh` runs the same checks as GitHub's CI.

- `src/album_builder/` - the app's source code
- `tests/` - automated tests
- `docs/specs/` - what each feature must do
- `docs/plans/` - how each phase was built
- `packaging/` - AppImage and Windows build scripts, and the menu entry
- `assets/` - the icon
- [`ROADMAP.md`](ROADMAP.md) - what is planned and what has shipped

## License

MIT. See [LICENSE](LICENSE).
