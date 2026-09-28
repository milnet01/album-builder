# Album Builder — Discovery

> **Purpose — so that later, anyone can tell whether the thing being
> built is still the thing that was wanted.**

Everything is checked against this document for the life of the project,
so each sign of success below is something you could observe by using
the app. The workflow it serves is `~/.claude/workflow.md` § 3.

**Status:** agreed (2026-09-28).

## The problem

Choosing which recordings make an album, and in what order, means
juggling files by hand. You play them in one program, keep the track
list somewhere else, and build the shareable folder yourself. Nothing
ties the choice, the order, the lyrics and the finished album together.

## Who it is for

- **A musician with a folder of their own recordings** who wants to pick
  and order an album and hear it through. The owner is the first such
  person.
- **Anyone using the public Linux or Windows download** for the same job.

## Signs it is working

- **S1** — With a folder of 1,000 songs, the library opens within a few
  seconds and search results keep up as you type.
- **S2** — The approved album folder numbers the tracks, and its
  playlist lists them, in exactly the order shown in the app.
- **S3** — Once a song's lyrics are aligned, each line lights up within
  half a second of being sung.
- **S4** — The approved playlist opens in VLC and in the system's default
  player, and plays every track in the order you set.
- **S5** — The approval report prints on A4 with nothing cut off, in
  every language the app offers, Arabic and Hebrew included.
- **S6** — A fresh Linux or Windows machine that meets the stated system
  requirements runs the download and builds an album with nothing else
  installed. Lyrics alignment is the one optional extra.
- **S7** — Your music files are never renamed, moved, changed or deleted.

## What it deliberately does not do

- Edit, mix, trim or convert audio.
- Edit song tags.
- Stream, sync or store anything online.
- Manage a whole music collection. Libraries far beyond S1's size are
  not a goal.
- Copy songs into the album folder. The folder links to your originals,
  so it plays on this computer. The one exception is adding new music
  from elsewhere (MUSI-0371), which copies files into your music folder.
