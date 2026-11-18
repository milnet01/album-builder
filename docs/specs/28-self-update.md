<!-- ants-spec-format: 1 -->
# 28 — The app updates itself to the newest release

**Status:** accepted (2026-11-18). Linux half built 2026-11-18; Windows half built 2026-11-18 with the installer (Spec 24 §4.7, MUSI-0406).
**Kind:** feature.
**Source:** ROADMAP MUSI-0389 (user request 2026-10-10; owner decisions 2026-11-04 and 2026-11-18).
**Depends on:** 10, 22, 23, 24, 27. **Amends:** 00 (network use), 10 (`settings.json` schema), 23 (§9 out-of-scope line; update information in the build), 27 (INV-3's name map).

**Layman:** Once a day the app looks for a newer version. If there is one, it asks you, then downloads it, checks it is genuine, and installs it.

## 1. Goal

A copy of Album Builder running from the AppImage or installed by the Windows installer learns that a newer release exists, asks the user, and installs it. It installs only a download whose checksum is listed in a file signed with the project's key. Copies installed any other way never check and never update themselves.

## 2. Problem

1. Neither shipped build updates itself. Spec 23 §9 lists "Auto-update (AppImageUpdate / zsync)" as deferred. Spec 24 says nothing about updates. A user stays on the version they downloaded until they notice a release.
2. The AppImage carries no update information and the release publishes no `.zsync` file. `grep -n zsync packaging/build-appimage.sh .github/workflows/appimage.yml` returns nothing, and `gh release view v1.1.0 --json assets` lists only `AlbumBuilder-1.1.0-windows-x64.zip` and `AlbumBuilder-1.1.0-x86_64.AppImage`. Outside AppImage updaters cannot update it either.
3. Nothing proves a download came from this project. The release publishes no checksum file and no signature.
4. The app cannot tell how it was installed. The only detector, `app.py::_running_from_source_tree`, looks for `pyproject.toml` three levels up. It is true for a live checkout and false for the AppImage, the Windows build and the openSUSE package alike.
5. The AppImage's bundled Python cannot open a secure connection to GitHub. Measured 2026-11-18 by running the interpreter extracted from `dist/AlbumBuilder-0.6.1-x86_64.AppImage` (`--appimage-extract`, then `opt/python3.13/bin/python3.13` under `env -i`): `urllib.request.urlopen("https://api.github.com/...")` fails with `CERTIFICATE_VERIFY_FAILED`. `ssl.get_default_verify_paths()` points at `/opt/_internal/openssl-3.5/cert.pem`, a path inside the build container. AppRun sets no `SSL_CERT_FILE` (`grep -n SSL packaging/build-appimage.sh` → nothing).
6. Spec 00 promises that the only network use is the Whisper model download (§ Offline). A daily check is a second use and needs that promise changed.

## 3. Scope decisions (agreed with the user)

All by the owner, recorded on MUSI-0389.

- **Check on start, at most once a day; always ask before installing** — 2026-11-04.
- **Offline, the daily check fails quietly and tries again the next day.** Only a check the user starts says it could not reach GitHub — 2026-11-18.
- **Each release publishes a checksum file signed with a project key.** The app carries the public key and refuses a download whose signature or checksum does not match — 2026-11-18.
- **A copy from the openSUSE package never updates itself; zypper does** — 2026-11-18, and Spec 27 §9 hands the check to this spec. **The launcher that runs a live checkout never updates itself** — MUSI-0389 body.
- **The release workflow signs automatically, with the private key held as a GitHub Actions secret.** Uploading the secret waits for the owner's go-ahead — 2026-11-18.
- **The AppImage downloads the whole new file and checks it.** The release also publishes zsync data so outside AppImage updaters can do small updates — 2026-11-18. This replaces the 2026-11-04 answer "the AppImage uses its built-in zsync update information": applying zsync in-app would need a second bundled program.
- **A "Check for updates automatically" switch, on by default** — 2026-11-18.
- **The offer has three buttons: Install now, Remind me tomorrow, Skip this version** — 2026-11-18.
- **Windows gets an installer (MUSI-0406) before Windows self-update, and a Windows update runs the signed installer quietly.** The zip stays as a portable version that does not update itself — 2026-11-18.
- **`SHA256SUMS.sig` may carry several signatures**, so a copy that missed a key change still verifies — 2026-11-18.

Author's calls, cheap to change: the signature is a raw Ed25519 signature in a one-line file of this project's own format (§8 says why not minisign or GPG); the signing job polls for the release's assets rather than restructuring the two build workflows (§8).

## 4. Design

### 4.1 Parts

| Part | New or changed | Holds |
|---|---|---|
| domain | new `domain/release_manifest.py` | version parsing, `SHA256SUMS` and signature parsing, signature check, `TRUSTED_KEYS`, expected asset names |
| services | new `services/updater.py` | install-kind detection, HTTPS fetches, the check and download workers (`QThread`), applying the update |
| persistence | `persistence/settings.py` | `read_updates()` / `write_updates()` for the `updates` block |
| ui | new `ui/update_dialog.py`; `ui/main_window.py` Help menu and `closeEvent` | the offer, progress and result dialogs; two menu entries; the close-time wait for the update worker |
| packaging | `packaging/release-signing.py`, `.github/workflows/release-sign.yml`, `packaging/build-appimage.sh` | key generation, signing, update information in the AppImage |

Layer rules are `docs/design.md`'s: the domain module imports no PyQt6; network work runs in a `QThread` worker in the shape of `services/duplicates.py::DuplicateWorker` and reports by signal.

New runtime dependencies: `cryptography` (Ed25519) and `certifi` (§2 item 5). Both go in `requirements.txt` with floors as `docs/standards/dependency-currency.md` sets them.

### 4.2 Install kind

```python
class InstallKind(StrEnum):
    APPIMAGE = "appimage"
    WINDOWS = "windows"
    NONE = "none"

def install_kind() -> InstallKind: ...
```

- `APPIMAGE` when the `APPIMAGE` environment variable names an existing file **and** the resolved `album_builder` package directory lies inside the resolved `APPDIR`. The second test stops a copy started from a terminal that another AppImage launched, which inherits that AppImage's `APPIMAGE`.
- `WINDOWS` when `sys.platform == "win32"`, `getattr(sys, "frozen", False)` is true, and the file `install-kind.txt` beside `sys.executable` reads `installer` once surrounding whitespace is stripped. The installer (MUSI-0406) writes that file; the portable zip carries none.
- `NONE` otherwise: the portable zip, the openSUSE package, a pip install, `install.sh`'s launcher, `PYTHONPATH=src` runs.

Under `NONE` the app makes no update request and the Help menu shows neither update entry.

### 4.3 What a release publishes

Four assets come from the build workflows: `AlbumBuilder-<V>-x86_64.AppImage`, `AlbumBuilder-<V>-x86_64.AppImage.zsync` (new, §4.7), `AlbumBuilder-<V>-windows-x64.zip` and `AlbumBuilder-<V>-windows-x64-setup.exe` (new, MUSI-0406). `release-sign.yml` adds two:

`SHA256SUMS` — GNU `sha256sum` text format, ASCII, LF line ends, one line per asset above, sorted by name:

```
<64 lowercase hex><two spaces><asset name>\n
```

The app's parser ignores names it does not use, so a later release may list more assets. It refuses a malformed line or a repeated name.

`SHA256SUMS.sig` — one line per signing key:

```
album-builder-signature-v1 <key id> <base64 signature>\n
```

- `<key id>`: the first 16 lowercase hex characters of SHA-256 over the 32-byte raw public key.
- `<base64 signature>`: standard base64 (with padding) of the 64-byte Ed25519 signature over the exact bytes of `SHA256SUMS`.

The file is accepted when every line parses, at least one line names a key id in `TRUSTED_KEYS`, and every line naming a trusted key id verifies. A line under an unknown key id is skipped. Several lines let a copy that missed a key change still verify (§6; owner, 2026-11-18).

`release_manifest.TRUSTED_KEYS: dict[str, str]` maps key id to base64 raw public key. It may hold several, so a release can introduce a successor (§6).

### 4.4 Checking

The check asks `https://api.github.com/repos/milnet01/album-builder/releases/latest`, which leaves out drafts and pre-releases. It sends `User-Agent: album-builder/<version>` and `Accept: application/vnd.github+json`, and nothing else about the user.

A release is **on offer** when all of these hold:

1. `tag_name` matches `^v(\d+)\.(\d+)\.(\d+)$`, and that version is greater, as an integer triple, than the running `album_builder.version.__version__`.
2. The release lists `SHA256SUMS` and `SHA256SUMS.sig`. Both download, and `SHA256SUMS.sig` is accepted (§4.3) over the downloaded `SHA256SUMS` bytes.
3. `SHA256SUMS` parses, and lists this kind's asset for that version: `AlbumBuilder-<V>-x86_64.AppImage` or `AlbumBuilder-<V>-windows-x64-setup.exe`. The release also lists that asset.
4. For the daily check only: `V` is not `updates.skipped_version`.

A release failing 2 or 3 is treated as **not ready**, not as an error: the daily check stays silent, and a manual check says "A new version is being prepared. Try again later."

### 4.5 When the check runs

**Daily.** A few seconds after the main window first shows, the app checks when all hold: kind is not `NONE`; `updates.auto_check` is true; `updates.last_check` is missing, unreadable, at least 24 hours old, or more than an hour in the future (a clock set back). The app writes `last_check = now` **before** the request, so a failed check also waits a day. A failure shows nothing and is logged at INFO.

**Manual.** Help ▸ *Check for updates now*. It ignores `auto_check`, `last_check` and `skipped_version`, and does not write `last_check`. It always ends in a dialog: the offer, "You have the newest version (X.Y.Z).", "Could not reach GitHub. Check your internet connection and try again.", or the not-ready message.

Help ▸ *Check for updates automatically* is a checkable entry bound to `updates.auto_check`.

Only one check or download runs at a time; a manual check started meanwhile runs when the other ends.

### 4.6 The offer and the install

The offer dialog names both versions and shows the release body as plain text (never rendered as HTML or Markdown), or a link to the release page when the body is empty. Buttons:

- **Install now** — downloads and installs (below).
- **Remind me tomorrow** — closes; the next daily check offers it again.
- **Skip this version** — writes `updates.skipped_version = V`; the daily check stays quiet until a newer release.

**Download.** The worker streams the asset into a temporary file beside the target (below) and hashes it as it goes, stopping at INV-9's cap. A progress dialog shows bytes received and a Cancel button. Only when the SHA-256 equals the `SHA256SUMS` entry does anything change on disk outside the temporary file. On any failure or cancel the temporary file is deleted and the running copy is untouched.

**AppImage.** The target is `Path(os.environ["APPIMAGE"]).resolve()`. The temporary file is `.<target name>.update` in the same folder. If the folder is not writable, the app says so before downloading and offers to open the release page. After the hash matches: copy the target's permission bits (adding execute), `fsync`, then `os.replace` onto the target. The path stays the same, so shortcuts keep working; the file name keeps its old version number. The dialog then offers **Restart now** (close through the normal close path so state is saved; `app.run()` starts the target with `QProcess.startDetached` only after it releases the single-instance lock, because a copy started earlier finds the lock held and exits) or **Later** (the next start runs the new version).

**Windows.** Only an installed copy updates (§4.2). The download goes to `<settings_dir()>\updates\AlbumBuilder-<V>-windows-x64-setup.exe.part`, a folder only this user writes. After the hash matches it is renamed without `.part`. The app tells the user "Album Builder will close and reopen to finish updating", starts the installer in the quiet update mode Spec 24 §4.7 defines, and closes through the normal close path. That mode asks nothing, shows progress, waits for the running app to exit, installs over the existing install, and starts the new version. Spec 24 §4.7 sets its flags. At the next start the app deletes the `updates` folder. When it finds an installer there named for a version newer than its own, the install did not happen, and it shows once "The update could not finish. You are still on X.Y.Z." first.

### 4.7 Publishing: zsync data and the signature

`build-appimage.sh` passes appimagetool `-u "gh-releases-zsync|milnet01|album-builder|latest|AlbumBuilder-*x86_64.AppImage.zsync"`, and keeps the `.zsync` file it writes beside the AppImage. `appimage.yml` uploads both.

`release-sign.yml` runs on `push: tags: ['v*']`, and by hand (`workflow_dispatch`) with a required `tag` input naming the release to sign, with `permissions: contents: write`. Its one job:

1. polls the tag's release every 60 seconds, for up to 120 minutes, until every build asset of §4.3 that exists yet is present with `state` `uploaded`: the AppImage, its `.zsync`, the zip and the installer. `release-sign.yml` holds that list (a failed build means it times out and fails, so nothing is signed);
2. downloads them into a folder under `$RUNNER_TEMP`, outside the checkout, writes `SHA256SUMS`, and runs `packaging/release-signing.py sign SHA256SUMS` with the secret in the environment variable `RELEASE_SIGNING_KEY`;
3. runs `release-signing.py verify SHA256SUMS`, which checks the signature against `TRUSTED_KEYS` imported from `album_builder.domain.release_manifest`, so a secret that does not match the shipped key fails the job;
4. uploads `SHA256SUMS` and `SHA256SUMS.sig` to the release.

`RELEASE_SIGNING_KEY` holds one line per signing key, each the standard base64 of a 32-byte raw Ed25519 private key; `sign` writes one signature line per key. It reaches only step 2's environment.

`packaging/release-signing.py` has three commands: `generate --out PATH` (writes the private key file, in `RELEASE_SIGNING_KEY`'s format, with mode 0600, refuses a path inside the git work tree, and prints the `TRUSTED_KEYS` entry), `sign FILE` and `verify FILE`.

### 4.8 Settings

A new optional `updates` block in `settings.json`, read by `read_updates()` and written by `write_updates()` through `_write_settings`:

| Field | Type | Default |
|---|---|---|
| `updates.auto_check` | bool | `true` |
| `updates.last_check` | ISO-8601 string (Spec 10 § Encoding rules) or `null` | `null` |
| `updates.skipped_version` | string `X.Y.Z` or `null` | `null` |

A malformed value reads as its default. No `schema_version` bump: every field is optional, as Spec 26 did for its fields.

## 5. Invariants

The domain and services tests inject a fetcher, a clock and a test key pair; none touches the network.

- **INV-1** (TC-28-01) — The app makes an update request only when `install_kind()` is `APPIMAGE` or `WINDOWS`; under `NONE` neither Help entry exists. `APPIMAGE` needs both the `APPIMAGE` file and the package inside `APPDIR`.
  *Test:* `tests/services/test_TC_28_updater.py::test_install_kind` — cases: no variables; `APPIMAGE` set to a file with `APPDIR` elsewhere (inherited); both matching; `sys.frozen` on `win32` with `install-kind.txt` reading `installer`, reading `portable`, and absent; `sys.frozen` off `win32`. And `::test_no_request_when_kind_none`, which counts fetcher calls.
  *Breaks when:* detection trusts `APPIMAGE` alone, or the startup check runs before consulting the kind.

- **INV-2** (TC-28-02) — The daily check runs at most once per 24 hours, writes `last_check` before the request, and makes none when `auto_check` is false.
  *Test:* `tests/services/test_TC_28_updater.py::test_daily_due` — a fake clock at last_check +23 h (no request), +24 h (one), a failing request followed by +1 h (no request), last_check two hours in the future (one), `auto_check` false (none).
  *Breaks when:* `last_check` is written only on success, so an offline start retries every launch.

- **INV-3** (TC-28-03) — A failed daily check opens no dialog; a failed manual check opens exactly the could-not-reach dialog.
  *Test:* `tests/ui/test_TC_28_update_dialog.py::test_offline_quiet_daily_loud_manual` (pytest-qt, fetcher raising `URLError`).
  *Breaks when:* both paths share one error handler that shows a message.

- **INV-4** (TC-28-04) — A release is on offer only when its tag is exactly `vX.Y.Z` and greater than the running version; the daily check also passes over `skipped_version`, and the manual check does not.
  *Test:* `tests/domain/test_TC_28_release_manifest.py::test_version_rule` — table: `v1.1.1` > `1.1.0`; `v1.10.0` > `1.9.0`; `v1.1.0`, `v1.0.9`, `v1.2.0-rc.1`, `1.2.0`, `v1.2` all refused; skipped `1.2.0` refused by daily, offered by manual.
  *Breaks when:* versions compare as strings (`1.10.0` < `1.9.0`), or a pre-release suffix is ignored rather than refused.

- **INV-5** (TC-28-05) — `SHA256SUMS` is accepted only under §4.3's rule for `SHA256SUMS.sig`, checked over its exact bytes. This is the trust boundary: GitHub's answers, redirects and asset bytes are untrusted until this check and INV-6 pass.
  *Test:* `tests/domain/test_TC_28_release_manifest.py::test_signature` — a test key signs a fixture; accepted. Accepted: a trusted line beside a line under an unknown key id. Refused: one byte of `SHA256SUMS` changed; one signature byte changed; only unknown key ids; the right signature under a wrong key id; a malformed line beside a valid one; two trusted lines of which one fails; a missing `.sig`.
  *Breaks when:* verification runs on re-encoded or line-split text instead of the downloaded bytes, an unknown key id falls back to any key, or one verifying line is taken as enough while another trusted line fails.

- **INV-6** (TC-28-06) — A downloaded asset changes nothing outside its temporary file unless its SHA-256 equals the signed entry for `AlbumBuilder-<V>-<kind suffix>`, where `V` is the release's tag version. A failed, oversized or cancelled download leaves the running copy byte-identical and no temporary file behind.
  *Test:* `tests/services/test_TC_28_updater.py::test_download_gate` — with a fake AppImage in `tmp_path`: a matching download replaces it; a wrong hash, a body over the listed size, a cancel mid-stream, and a manifest whose entry names another version (an old signed `SHA256SUMS` replayed under a new tag) each leave the target's bytes and mtime unchanged and the folder holding only the target.
  *Breaks when:* the file is moved into place before hashing completes, or the expected name is taken from the manifest rather than built from the tag.

- **INV-7** (TC-28-07) — An AppImage update replaces the file at the same path, keeps it executable, and uses one `os.replace`.
  *Test:* `tests/services/test_TC_28_updater.py::test_appimage_replace` — mode 0755 target; after the update the path holds the new bytes with mode 0755.
  *Breaks when:* the new file is written under the new versioned name, or the mode is not copied.

- **INV-8** (TC-28-08) — On Windows the app starts the downloaded installer only after its hash matches, only from `<settings_dir()>\updates\`, and only on an installed copy; the portable zip never starts one.
  *Test:* `tests/services/test_TC_28_updater.py::test_windows_install_gate`, with the process launch replaced by a recorder: a matching download records one launch of the renamed file in that folder; a wrong hash records none and leaves no file; an `install-kind.txt` that is missing or reads anything but `installer` records no request at all. On the Windows test machine (`ssh wintest`), a manual recipe on two test builds whose `TRUSTED_KEYS` and release URL are patched, before the build runs, to a test key and a test repository (release builds carry no such patch): install the older with its installer, update it to the newer from inside the app, and confirm the newer starts, the albums and settings remain, and `updates\` is gone at the following start.
  *Breaks when:* the launch happens before the rename that follows the hash check, or detection treats every frozen Windows build as installed.

- **INV-9** (TC-28-09) — Every update request is HTTPS on every redirect hop, and every response is read to a fixed cap: release JSON 1 MiB, `SHA256SUMS` 64 KiB, `.sig` 1 KiB, asset the smaller of its listed size and 1 GiB.
  *Test:* `tests/services/test_TC_28_updater.py::test_transport_limits` — a redirect to `http://` refused; over-cap bodies for each kind refused.
  *Breaks when:* the default `urllib` redirect handler is used unchanged (it follows `https` → `http`).

- **INV-10** (TC-28-10) — `release-signing.py sign` then `verify` round-trips with the key in `RELEASE_SIGNING_KEY`, `verify` checks against `release_manifest.TRUSTED_KEYS`, and `generate` refuses a path inside the work tree.
  *Test:* `tests/packaging/test_TC_28_release_signing.py` — round trip with a generated test key and `TRUSTED_KEYS` patched; `verify` with an untrusted key exits non-zero; `generate --out ./key` inside the repo exits non-zero and writes nothing.
  *Breaks when:* `verify` carries its own copy of the key list, or `generate` writes wherever it is told.

- **INV-11** (TC-28-11) — `release-sign.yml` passes `secrets.RELEASE_SIGNING_KEY` only to the signing step's `env`, verifies before uploading, and uploads only `SHA256SUMS` and `SHA256SUMS.sig`.
  *Test:* `tests/packaging/test_TC_28_release_signing.py::test_workflow_shape` — parses the YAML: exactly one step references the secret, through `env`; the verify step precedes the upload step; the upload names those two files.
  *Breaks when:* the secret is interpolated into a `run:` line, which puts it in the shell command text.

- **INV-12** (TC-28-12) — The AppImage carries the update information string of §4.7, and the release workflow uploads the `.zsync` file.
  *Test:* a new smoke step in `appimage.yml`: `readelf --string-dump=.upd_info <AppImage>` contains `gh-releases-zsync|milnet01|album-builder|latest|AlbumBuilder-*x86_64.AppImage.zsync`, and the `.zsync` file exists beside the AppImage; and `tests/test_TC_23_appimage.py` gains a check that `appimage.yml`'s upload `files` names the `.zsync`.
  *Breaks when:* the `-u` flag is dropped from the appimagetool call, or the build writes no `.zsync` beside the AppImage.

- **INV-13** (TC-28-13) — The `updates` block reads its defaults from a missing block and from each malformed field, and `write_updates` keeps every other top-level key.
  *Test:* `tests/persistence/test_TC_28_settings_updates.py` — absent block; `auto_check: "yes"`; `last_check: 5`; `skipped_version: "x"`; a round trip that leaves `audio` and `ui` unchanged.
  *Breaks when:* a field is read without a type check, or the writer rebuilds the file from the `updates` block alone.

## 6. Failure modes

| What breaks | What happens |
|---|---|
| Offline, DNS failure, timeout (15 s connect and read) | Daily: silent, retried next day. Manual: could-not-reach dialog. |
| GitHub rate limit (HTTP 403/429) | As offline. One request a day is far inside the unauthenticated limit. |
| Release published before signing finished | Not ready (§4.4): daily silent, manual says try later. |
| `release-sign.yml` times out (a build failed) | No signature; no copy offers the release. Re-run the workflow after fixing the build. |
| `release-sign.yml` itself fails | No signature; no copy offers the release. A re-run uses the tag's copy of the workflow, so fix it on `main`, then run it by hand with that tag. |
| Signing secret missing or not matching `TRUSTED_KEYS` | Step 3 fails the job; nothing is uploaded. |
| Private key lost | Copies in the field can never verify a later release. Users must download one release by hand, and that release carries a new key. The owner keeps an offline copy of the key file. |
| Private key leaked | An attacker who can also publish a release on the repository could ship a signed update. Put a new key beside the old one in `RELEASE_SIGNING_KEY`, so each release carries two signature lines, and ship `TRUSTED_KEYS` holding only the new key. Copies that skip that release still verify a later one by its old-key line. Drop the old key from the secret once few copies can still need it; copies that never updated by then must update by hand once. |
| `TRUSTED_KEYS` empty (before the key exists) | Every release fails INV-5, so nothing is offered. Safe by default. |
| Disk full during download | Write fails; temporary file deleted; old copy untouched; message names the folder. |
| AppImage folder not writable (e.g. `/opt`) | Said before downloading; offers the release page. |
| Windows: the installer fails or is cancelled | The installer's own rollback keeps the old install; the next start finds the newer installer in `updates\` and shows the could-not-finish message once. |
| App closed during a check or download | `closeEvent` requests interruption and waits, as it does for `_duplicate_worker`; the worker honours `isInterruptionRequested` and deletes its temporary file. |
| User replaces the AppImage by hand while it runs | `os.replace` acts on whatever is at the path; the new hash was verified, so the result is the signed release. |

## 7. Tests

Each invariant's *Test:* clause names its test; §10 maps them. The test files are new except `tests/test_TC_23_appimage.py`. Each test is seen failing before the code it locks exists.

- `tests/domain/test_TC_28_release_manifest.py` — INV-4, INV-5.
- `tests/services/test_TC_28_updater.py` — INV-1, INV-2, INV-6, INV-7, INV-8, INV-9.
- `tests/ui/test_TC_28_update_dialog.py` — INV-3.
- `tests/persistence/test_TC_28_settings_updates.py` — INV-13.
- `tests/packaging/test_TC_28_release_signing.py` — INV-10, INV-11.
- INV-12: the `appimage.yml` smoke step and `tests/test_TC_23_appimage.py`.

INV-8's real install runs only on the Windows test machine, and INV-12's `readelf` step only in the AppImage workflow; the rest run in `./local-CI.sh`. New user-facing strings go through `tr()` into all seven catalogs; TC-25-03 and TC-25-04 already enforce that.

## 8. Alternatives considered (and rejected)

- **In-app zsync, by bundling AppImageUpdate.** Smaller downloads, but a second program inside the AppImage to keep current and a second verification path. Owner chose the full download (2026-11-18).
- **minisign format.** A standard tool and format, but verifying it needs BLAKE2b prehashing plus a second "global" signature over a trusted comment, all parsed by hand; this project would write that parser anyway. Our one-line format carries the same Ed25519 check with less to get wrong.
- **GPG signatures.** Needs `gpg` on the user's machine (absent on Windows) or a large library.
- **Python's own certificate store instead of `certifi`.** Fails in the AppImage (§2 item 5).
- **`QNetworkAccessManager`.** Its TLS on Linux loads the host's `libssl` at run time, an AppImage dependency nothing measures; `urllib` with `certifi` behaves the same on every kind.
- **One release workflow calling the two builds as reusable workflows, with signing as a `needs:` job.** No polling, but it changes the triggers Specs 23 and 24 pin (INV-23-8, INV-24-8). Polling touches neither, and a timeout fails safe.
- **Triggering signing on the `release` event.** Uploads made with `GITHUB_TOKEN` start no new workflow runs, so the event never arrives.
- **Writing the new AppImage under its new versioned name.** Breaks every shortcut that points at the old path.
- **Updating the portable zip by swapping its files with a script.** A running exe cannot be overwritten, so a helper script must swap files after the app exits, and a Windows copy may keep its albums in the same folder (`app.py::_resolve_project_root` falls back to the working directory). Owner chose an installer instead (2026-11-18, MUSI-0406).
- **Checking the openSUSE package and telling the user to run zypper.** Owner: zypper owns that copy (Spec 27).

## 9. Out of scope

- Delta (zsync) downloads inside the app — rejected above; outside AppImage updaters get them from §4.7.
- Code-signing the Windows exe — deferred by Spec 24; not yet queued.
- Pre-release channels — `releases/latest` excludes them; deferred, not yet queued.
- Rolling back to the previous version from inside the app — deferred; not yet queued.
- The portable Windows zip updating itself — owner, 2026-11-18: it does not.
- The installer itself — Spec 24 §4.7.
- Updating an arm64 AppImage — none is built (Spec 23 §9).

## 10. What checks this

| Rule | What catches a breach |
|---|---|
| INV-1 | `test_TC_28_updater.py::test_install_kind`, `::test_no_request_when_kind_none` |
| INV-2 | `test_TC_28_updater.py::test_daily_due` |
| INV-3 | `test_TC_28_update_dialog.py::test_offline_quiet_daily_loud_manual` |
| INV-4 | `test_TC_28_release_manifest.py::test_version_rule` |
| INV-5 | `test_TC_28_release_manifest.py::test_signature` |
| INV-6 | `test_TC_28_updater.py::test_download_gate` |
| INV-7 | `test_TC_28_updater.py::test_appimage_replace` |
| INV-8 | Partial: `test_TC_28_updater.py::test_windows_install_gate` checks the gate with a recorded launch, and `::test_windows_update_cleanup` the next start's cleanup; only the manual Windows recipe runs a real installer |
| INV-9 | `test_TC_28_updater.py::test_transport_limits` |
| INV-10 | `test_TC_28_release_signing.py` |
| INV-11 | `test_TC_28_release_signing.py::test_workflow_shape` |
| INV-12 | `appimage.yml` smoke step (tag and manual runs only) and `test_TC_23_appimage.py` |
| INV-13 | `test_TC_28_settings_updates.py` |
| A real release is signed and offered end to end | **nothing** automated — proven by the first tagged release after this ships, updating an AppImage and an installed Windows copy of the previous release |
| No private key in the tree | Partial: `generate` refuses the work tree (INV-10); `gitleaks` in `/audit` scans commits; a key pasted into a file by hand is caught only by that scan |

## 11. Cross-doc impact

Applied after the review gate, before building, each with a labelled loop-log row in its spec's log:

- **Spec 00**: the **Offline** bullet and the opening "no server" line: add the daily update check, on the AppImage and installed Windows copies only, switchable off.
- **Spec 24**: amended by MUSI-0406, which adds the installer and `install-kind.txt`; not by this spec.
- **Spec 10** `settings.json` schema: add the `updates` block (§4.8) to the example and the field table.
- **Spec 23** §9: the auto-update line points here; §4 gains the `-u` flag and the `.zsync` upload.
- **Spec 27** INV-3: the name map gains `cryptography`→`python3-cryptography` and `certifi`→`python3-certifi`; `packaging/obs/album-builder.spec` gains the matching `Requires:` and `BuildRequires:` lines.
- `docs/standards/dependency-currency.md`: the two new dependencies.
- `README.md`: a short "Updates" paragraph. `CHANGELOG.md`: the release entry.

## 12. Cold-eyes loop log

Rows live in `../reviews/28-self-update-loop-log.md`.

## 13. Resource cost

- **Network:** one request to the GitHub API a day, plus two small files when a release is newer; the asset only after the user says Install.
- **Disk:** one temporary file the size of the asset, beside the AppImage, or in `updates\` on Windows until the next start.
- **Dependencies:** `cryptography` and `certifi`, in the AppImage, the Windows bundle and the openSUSE package's `Requires:`.
- **CI:** one `release-sign.yml` job per tag, idle while it polls; the repository is public, so its Linux minutes are free.

## 14. Open questions

None about the design. The owner's go-ahead is needed for one step: running `release-signing.py generate`, then uploading the key with `gh secret set RELEASE_SIGNING_KEY`.
