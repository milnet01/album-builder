# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this directory is

This is **not a code project**. It is a working folder for music production source material — primarily voice memos and rough track ideas exchanged over WhatsApp.

- `Tracks/` — raw `.mpeg` audio files. Filenames follow the WhatsApp export convention `WhatsApp Audio YYYY-MM-DD at HH.MM.SS.mpeg`; the timestamp in the filename is the *export* time, not necessarily the recording time. Files are not under version control and may be regenerated/replaced when new memos arrive.

There is no source code, no `package.json` / `Cargo.toml` / `pyproject.toml`, no tests, no build system, and no git history. Slash commands that assume a codebase (`/audit`, `/release`, `/bump`, `/feature-test`, `/triage`, `/indie-review`, `/debt-sweep`, `/security-review`, `/review`) do not apply here — do not run them.

## Likely tasks

Expect requests around the audio files themselves rather than code:

- **Inspecting / converting audio** — use `ffprobe` to read metadata, `ffmpeg` to transcode (e.g. `.mpeg` → `.wav`/`.flac` for DAW import, or normalise loudness with `loudnorm`).
- **Renaming / organising tracks** — the WhatsApp filenames sort lexically by export time, which is usually fine; only rewrite them if the user asks.
- **Trimming / splitting** — `ffmpeg -ss ... -to ... -c copy` for lossless cuts on `.mpeg` (MPEG audio) containers.

Do not transcode, rename, move, or delete files in `Tracks/` without explicit user confirmation — these are source recordings and the only copy may live here.

## Inherited rules

The repo-wide rules in `/mnt/Storage/CLAUDE.md` (notably the `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A -p "..."` requirement for any privileged command) and the global rules in `~/.claude/CLAUDE.md` (commit-locally / batch-push, shortest correct implementation, no workarounds without root-cause fixes) apply here as everywhere else.
