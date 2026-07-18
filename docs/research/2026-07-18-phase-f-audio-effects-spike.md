# Phase F spike — Equalizer / audio effects / ReplayGain (2026-07-18)

**Status:** Research only (no code). Decision memo for the music-player epic
Phase F. Companion to `ROADMAP.md` heading `## Future / deferred` (the epic
bullet) and `docs/specs/16-transport-controls.md` §Gapless investigation.

## Question

Phase F of the music-player epic asks whether to build any of: an **equalizer**,
**ReplayGain / volume normalization**, or **gapless / crossfade** playback on the
current PyQt6 + `QMediaPlayer` + `QAudioOutput` stack (Specs 06/15/16). The epic
flagged all three as "hard / deferred" pending a spike to gauge feasibility and
demand. This memo records the feasibility half.

## Findings

### 1. Equalizer / audio DSP — not feasible without replacing the pipeline

Qt Multimedia provides **no** audio-processing / effects API. The Qt 6.11 audio
overview states plainly that "Qt does not provide audio processing functionality,
and external dependencies are needed." `QAudioOutput` exposes only device
selection, volume, and mute — no filter graph, no EQ bands, no DSP hook. There is
no per-band EQ anywhere in QtMultimedia in Qt 6.

Building an EQ therefore means one of:
- **Raw-sample DSP** — decode to PCM and push through `QAudioSink` (the low-level
  sink, formerly `QAudioOutput` in Qt 5) with a hand-written biquad filter bank.
  This **replaces** `QMediaPlayer` entirely (the app would own decode + resample +
  filtering + buffering), which is a full rewrite of the Spec 06 playback service
  and its Spec 15 single-path invariant. High cost, high risk.
- **A different backend** — drive playback through GStreamer (which has an
  `equalizer-nbands` element) or a library like `miniaudio` with a DSP node graph,
  bound from Python. Adds a heavyweight native dependency and, again, retires
  `QMediaPlayer`.

**Verdict: deferred.** The cost (retire `QMediaPlayer`, own the whole pipeline) is
disproportionate for a curation-first app. Revisit only if a concrete user need
appears; it would be its own multi-phase project, not a Phase-F increment.

### 2. Gapless / crossfade — confirmed removed in Qt 6; deferred

`QMediaGaplessPlaybackControl` (which carried both gapless *and* `crossfadeTime`)
was a **Qt 5-only** service-control class; it does not exist in Qt 6's
`QMediaPlayer`. This re-confirms the epic's earlier note and Spec 16's §Gapless
investigation. The only Qt-6 route is a **dual-`QMediaPlayer` pre-roll** (load the
next track into a second player and swap at end-of-media), which fights the Spec 15
**single-playback-path invariant** (one controller owns every `set_source`/`play`/
`stop`). That conflict is exactly why Spec 16 deferred it to a dedicated spec
sequenced with this phase.

**Verdict: deferred.** No cheap path. If built, it needs its own spec that first
resolves the single-path invariant (e.g. an explicit "pre-roll player" carve-out).

### 3. ReplayGain (volume normalization) — feasible and cheap on the current stack

This is the one Phase-F item that is genuinely low-cost here, because it is **not**
DSP — it is tag-driven output-volume scaling:

- **Reading is free.** `domain/track.py` already parses ID3 via **mutagen** (an
  existing dependency). ReplayGain data lives in standard tags the same reader can
  pull: `TXXX:REPLAYGAIN_TRACK_GAIN` / `REPLAYGAIN_ALBUM_GAIN` (and the `_PEAK`
  companions), the `RVA2` frame, or the R128 `TXXX:R128_TRACK_GAIN` (Opus/EBU).
- **Applying is a multiply.** A `+/- N dB` gain is a linear factor
  `10 ** (dB / 20)` applied to the effective output level. `QAudioOutput.setVolume`
  takes a 0.0-1.0 linear scalar (Spec 06 already maps percent -> that), so a
  normalization offset composes with the user's volume as
  `output = user_volume * replaygain_factor`, clamped to `[0, 1]`, with peak
  headroom honored to avoid clipping.
- **No new dependency, no pipeline change.** Scanning/*writing* RG tags (what
  `rsgain` / `r128gain` do) stays **out of scope** — those are external one-off
  tools. The app would only *read* pre-existing tags and *scale volume*; files
  without RG tags fall back to today's behavior (no offset).

**Verdict: feasible as its own small, spec-first feature** (track/album-gain
reading + a normalization toggle + volume compositing). It does not require the EQ
or gapless work and could ship independently.

## Recommendation

- **EQ** and **gapless/crossfade**: keep deferred. Both retire `QMediaPlayer` or
  fight the single-path invariant; neither is a Phase-F-sized increment. Leave as
  parked epic items with this memo as the rationale.
- **ReplayGain volume normalization**: the only feasible/cheap piece. Promote it to
  its own spec (read-only tag consumption + output-volume compositing) **iff there
  is user demand for loudness leveling**. Gauge that demand before authoring a spec
  (per the epic's "gauge demand before committing").

## Sources

- Qt Multimedia audio overview (Qt 6.11): <https://doc.qt.io/qt-6/audiooverview.html>
- QMediaPlayer (Qt 6.11) — no gapless control class:
  <https://doc.qt.io/qt-6/qmediaplayer.html>
- QMediaGaplessPlaybackControl (Qt 5.15 only):
  <https://doc.qt.io/qt-5/qmediagaplessplaybackcontrol.html>
- rsgain (ReplayGain 2.0 scanner/tagger, external CLI):
  <https://github.com/complexlogic/rsgain>
- r128gain (Python RG/R128 module): <https://pypi.org/project/r128gain/>
