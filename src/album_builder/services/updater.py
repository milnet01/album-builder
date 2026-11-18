"""The app updates itself - Spec 28 (MUSI-0389).

How the app was installed, when the daily check is due, the check against
GitHub's latest release, the verified download, and the AppImage swap.
Network work runs in the QThread workers at the bottom, in the shape of
services/duplicates.py's DuplicateWorker.

GitHub's answers, redirects and asset bytes are untrusted until the signed
SHA256SUMS check (domain/release_manifest.py) and the download's hash pass.

On Windows only a copy the installer put in place updates; it downloads the
signed installer and runs it in its quiet update mode (Spec 24 §4.7).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Protocol

import certifi
from PyQt6.QtCore import QThread, pyqtSignal

import album_builder
from album_builder.domain import release_manifest as rm
from album_builder.persistence.settings import read_updates, settings_dir, write_updates
from album_builder.version import __version__

logger = logging.getLogger(__name__)

LATEST_URL = "https://api.github.com/repos/milnet01/album-builder/releases/latest"
TIMEOUT_SECONDS = 15
# INV-9: every response is read to a fixed cap.
MAX_RELEASE_JSON_BYTES = 1 << 20
MAX_SUMS_BYTES = 64 << 10
MAX_SIG_BYTES = 1 << 10
MAX_ASSET_BYTES = 1 << 30
_CHUNK = 1 << 16
_CHECK_INTERVAL = timedelta(hours=24)
_CLOCK_SLACK = timedelta(hours=1)


class InstallKind(StrEnum):
    APPIMAGE = "appimage"
    WINDOWS = "windows"
    NONE = "none"


_UPDATING_KINDS = frozenset({InstallKind.APPIMAGE, InstallKind.WINDOWS})

# The installer's quiet update mode (Spec 24 §4.7): no questions, a progress
# window, then the new version starts. /WAITPID=<pid> is added at launch.
INSTALLER_UPDATE_SWITCHES = ("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE")
_INSTALLER_NAME = re.compile(r"AlbumBuilder-(\d+\.\d+\.\d+)-windows-x64-setup\.exe")


class UpdateError(Exception):
    """The check or the download failed; the running copy is untouched."""


class UpdateCancelled(UpdateError):
    """The user cancelled the download, or the window is closing."""


def install_kind(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    frozen: bool | None = None,
    executable: Path | None = None,
    package_dir: Path | None = None,
) -> InstallKind:
    """How this copy was installed (§4.2). Arguments default to the live process."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    executable = Path(sys.executable) if executable is None else executable
    if package_dir is None:
        package_dir = Path(album_builder.__file__).parent
    image, appdir = environ.get("APPIMAGE"), environ.get("APPDIR")
    if image and appdir and Path(image).is_file():
        # A copy started from a terminal another AppImage launched inherits
        # APPIMAGE; only a package inside this APPDIR is that AppImage.
        if package_dir.resolve().is_relative_to(Path(appdir).resolve()):
            return InstallKind.APPIMAGE
    if platform == "win32" and frozen:
        try:
            marker = (executable.parent / "install-kind.txt").read_text(encoding="utf-8")
        except OSError:
            marker = ""
        if marker.strip() == "installer":
            return InstallKind.WINDOWS
    return InstallKind.NONE


def updates_enabled(kind: InstallKind) -> bool:
    """Whether this copy checks for updates and shows the Help menu entries."""
    return kind in _UPDATING_KINDS


def daily_due(updates, now: datetime) -> bool:
    """§4.5: due when switched on and the last check is missing, a day old,
    or more than an hour in the future (a clock set back)."""
    if not updates.auto_check:
        return False
    last = updates.last_check
    return last is None or now - last >= _CHECK_INTERVAL or last - now > _CLOCK_SLACK


def claim_daily_check(kind: InstallKind, now: datetime) -> bool:
    """True when the daily check should run now. Writes `last_check = now`
    first (INV-2), so a check that then fails also waits a day."""
    if not updates_enabled(kind):
        return False
    updates = read_updates()
    if not daily_due(updates, now):
        return False
    try:
        write_updates(replace(updates, last_check=now))
    except OSError as exc:
        # Without a stored time the check would repeat every start; skip it.
        logger.info("update check skipped: cannot save the check time (%s)", exc)
        return False
    return True


# ---- Transport ------------------------------------------------------------


class Transport(Protocol):
    def get(self, url: str, cap: int) -> bytes: ...
    def stream(self, url: str) -> Iterator[bytes]: ...


class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects to https only; the default handler also follows http."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.HTTPError(newurl, code, "redirect to non-https refused",
                                         headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_capped(stream: BinaryIO, cap: int) -> bytes:
    """Read the whole body, refusing one longer than `cap` bytes."""
    body = stream.read(cap + 1)
    if len(body) > cap:
        raise UpdateError(f"response longer than {cap} bytes")
    return body


class HttpsTransport:
    """urllib over HTTPS with certifi's CA bundle: the AppImage's bundled
    Python has no usable certificate store of its own (§2 item 5)."""

    def __init__(self) -> None:
        context = ssl.create_default_context(cafile=certifi.where())
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), HttpsOnlyRedirect(),
        )

    def _open(self, url: str):
        if not url.lower().startswith("https://"):
            raise UpdateError(f"refusing a non-https URL: {url}")
        headers = {"User-Agent": f"album-builder/{__version__}"}
        if url == LATEST_URL:
            headers["Accept"] = "application/vnd.github+json"
        try:
            return self._opener.open(
                urllib.request.Request(url, headers=headers), timeout=TIMEOUT_SECONDS,
            )
        except (urllib.error.URLError, OSError) as exc:
            raise UpdateError(str(exc)) from exc

    def get(self, url: str, cap: int) -> bytes:
        with self._open(url) as response:
            try:
                return read_capped(response, cap)
            except OSError as exc:
                raise UpdateError(str(exc)) from exc

    def stream(self, url: str) -> Iterator[bytes]:
        with self._open(url) as response:
            while True:
                try:
                    chunk = response.read(_CHUNK)
                except OSError as exc:
                    raise UpdateError(str(exc)) from exc
                if not chunk:
                    return
                yield chunk


# ---- The check --------------------------------------------------------------


class CheckStatus(StrEnum):
    OFFER = "offer"
    NEWEST = "newest"
    NOT_READY = "not_ready"  # published, but not yet signed and listed (§4.4)
    FAILED = "failed"  # GitHub could not be reached or answered nonsense


@dataclass(frozen=True)
class Offer:
    version: str
    notes: str
    page_url: str
    asset_name: str
    asset_url: str
    asset_size: int
    sha256: str


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    running: str
    offer: Offer | None = None


def _get(transport: Transport, url: str, cap: int) -> bytes:
    try:
        return transport.get(url, cap)
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(str(exc)) from exc


def check_release(
    transport: Transport,
    *,
    running: str,
    kind: InstallKind,
    skipped: str | None,
    trusted: Mapping[str, str] | None = None,
) -> CheckResult:
    """Ask GitHub for the latest release and decide whether it is on offer
    (§4.4). `skipped` is the daily check's skipped version; the manual check
    passes None. `trusted` defaults to release_manifest.TRUSTED_KEYS."""
    try:
        release = json.loads(_get(transport, LATEST_URL, MAX_RELEASE_JSON_BYTES))
        tag = release["tag_name"]
        assets = {a["name"]: a for a in release.get("assets") or ()}
    except (UpdateError, ValueError, KeyError, TypeError) as exc:
        logger.info("update check failed: %s", exc)
        return CheckResult(CheckStatus.FAILED, running)
    version = rm.offered_version(str(tag), running, skipped=skipped)
    if version is None:
        return CheckResult(CheckStatus.NEWEST, running)
    not_ready = CheckResult(CheckStatus.NOT_READY, running)
    try:
        sums = _get(transport, assets["SHA256SUMS"]["browser_download_url"], MAX_SUMS_BYTES)
        sig = _get(transport, assets["SHA256SUMS.sig"]["browser_download_url"], MAX_SIG_BYTES)
    except KeyError:
        return not_ready
    except UpdateError as exc:
        logger.info("update check failed: %s", exc)
        return CheckResult(CheckStatus.FAILED, running)
    if not rm.signature_accepted(sums, sig, trusted):
        logger.info("update check: release %s is not signed by a trusted key", tag)
        return not_ready
    try:
        listed = rm.parse_sums(sums)
    except rm.ManifestError as exc:
        logger.info("update check: %s", exc)
        return not_ready
    # INV-6: the expected name is built from the tag, never taken from the
    # manifest, so an old signed SHA256SUMS replayed under a new tag fails.
    name = rm.asset_name(version, kind.value)
    asset = assets.get(name)
    if name not in listed or not isinstance(asset, dict):
        return not_ready
    try:
        offer = Offer(
            version=rm.format_version(version),
            notes=str(release.get("body") or ""),
            page_url=str(release.get("html_url") or ""),
            asset_name=name,
            asset_url=str(asset["browser_download_url"]),
            asset_size=int(asset["size"]),
            sha256=listed[name],
        )
    except (KeyError, TypeError, ValueError):
        return not_ready
    return CheckResult(CheckStatus.OFFER, running, offer)


# ---- Download and install ---------------------------------------------------


def download_verified(
    transport: Transport,
    offer: Offer,
    temp: Path,
    *,
    should_stop: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> None:
    """Stream the asset into `temp`, hashing as it goes (§4.6 Download).

    Returns only when the SHA-256 equals the signed entry; on any failure or
    cancel `temp` is deleted and nothing else on disk has changed (INV-6).
    """
    cap = min(offer.asset_size, MAX_ASSET_BYTES)
    digest = hashlib.sha256()
    received = 0
    try:
        with temp.open("wb") as out:
            for chunk in transport.stream(offer.asset_url):
                if should_stop():
                    raise UpdateCancelled("download cancelled")
                received += len(chunk)
                if received > cap:
                    raise UpdateError("the download is larger than the release lists")
                digest.update(chunk)
                out.write(chunk)
                progress(received, offer.asset_size)
            out.flush()
            os.fsync(out.fileno())
        if digest.hexdigest() != offer.sha256:
            raise UpdateError("the download does not match its signed checksum")
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def appimage_path() -> Path:
    return Path(os.environ["APPIMAGE"]).resolve()


def appimage_folder_writable(target: Path) -> bool:
    return os.access(target.parent, os.W_OK)


def install_appimage(
    transport: Transport,
    offer: Offer,
    target: Path,
    *,
    should_stop: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> None:
    """Download, verify, then swap the AppImage at the same path (INV-7)."""
    temp = target.with_name(f".{target.name}.update")
    download_verified(transport, offer, temp, should_stop=should_stop, progress=progress)
    try:
        os.chmod(temp, (target.stat().st_mode & 0o777) | 0o111)
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class Launch:
    """A program app.run() starts after this process lets go of its lock."""

    program: Path
    arguments: tuple[str, ...] = ()


def updates_dir() -> Path:
    """Where a Windows update's installer is downloaded; only this user writes it."""
    return settings_dir() / "updates"


def install_windows(
    transport: Transport,
    offer: Offer,
    folder: Path,
    *,
    pid: int,
    should_stop: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> Launch:
    """Download and verify the installer into `folder` (§4.6 Windows, INV-8).

    Returns the launch that runs it in its quiet update mode, waiting for
    process `pid` to exit first. The file loses its `.part` suffix only after
    its hash matches, so nothing launchable exists before that.
    """
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / offer.asset_name
    part = final.with_name(f"{final.name}.part")
    download_verified(transport, offer, part, should_stop=should_stop, progress=progress)
    try:
        os.replace(part, final)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return Launch(final, (*INSTALLER_UPDATE_SWITCHES, f"/WAITPID={pid}"))


def finish_windows_update(folder: Path, running: str) -> bool:
    """At start, delete the updates folder (§4.6 Windows).

    True when it held an installer for a version newer than `running`: the
    last update did not install. Deleting the folder makes that said once.
    """
    if not folder.is_dir():
        return False
    current = rm.parse_version(running)
    failed = False
    for entry in folder.iterdir():
        match = _INSTALLER_NAME.fullmatch(entry.name)
        if match and current is not None:
            version = rm.parse_version(match[1])
            failed = failed or (version is not None and version > current)
    # The installer that just ran may still hold its file open; the next start
    # deletes whatever is left.
    shutil.rmtree(folder, ignore_errors=True)
    return failed


_after_exit: Launch | None = None


def request_restart(target: Path) -> None:
    """Ask app.run() to start `target` once this process has released its
    single-instance lock (§4.6 AppImage, Restart now)."""
    request_launch(Launch(target))


def request_launch(launch: Launch) -> None:
    """Ask app.run() to start `launch` once this process has released its
    single-instance lock and is about to exit."""
    global _after_exit
    _after_exit = launch


def take_restart_request() -> Launch | None:
    global _after_exit
    launch, _after_exit = _after_exit, None
    return launch


# ---- Workers ------------------------------------------------------------------


class UpdateCheckWorker(QThread):
    """Runs check_release off the ui thread; emits `done(CheckResult)` once."""

    done = pyqtSignal(object)  # Type: CheckResult

    def __init__(self, transport: Transport, kind: InstallKind, skipped: str | None,
                 parent=None) -> None:
        super().__init__(parent)
        self._transport = transport
        self._kind = kind
        self._skipped = skipped

    def run(self) -> None:
        try:
            result = check_release(
                self._transport, running=__version__, kind=self._kind,
                skipped=self._skipped,
            )
        except Exception:  # nothing may escape a thread's run()
            logger.exception("update check failed")
            result = CheckResult(CheckStatus.FAILED, __version__)
        if not self.isInterruptionRequested():
            self.done.emit(result)


class InstallWorker(QThread):
    """Runs one install job (install_appimage or install_windows, with its
    arguments bound) off the ui thread.

    The job takes `should_stop` and `progress` keywords. Emits
    `progress(received, total)` while downloading, then `done(str)` once: ""
    on success, "cancelled", or the error text. `result` holds what the job
    returned.
    """

    progress = pyqtSignal(object, object)  # bytes received, bytes in total
    done = pyqtSignal(str)

    def __init__(self, job: Callable[..., object], parent=None) -> None:
        super().__init__(parent)
        self._job = job
        self.result: object = None

    def run(self) -> None:
        try:
            self.result = self._job(
                should_stop=self.isInterruptionRequested, progress=self.progress.emit,
            )
        except UpdateCancelled:
            self.done.emit("cancelled")
            return
        except Exception as exc:  # nothing may escape a thread's run()
            logger.warning("update install failed: %s", exc)
            self.done.emit(str(exc) or type(exc).__name__)
            return
        self.done.emit("")
