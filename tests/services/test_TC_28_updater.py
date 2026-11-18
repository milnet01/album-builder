"""Spec 28 - the updater service: install kind, the daily schedule, the check,
the verified download and the AppImage swap. No test touches the network:
each injects a fake transport, a clock and a test key."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from album_builder.domain import release_manifest as rm
from album_builder.persistence import settings
from album_builder.persistence.settings import UpdateSettings
from album_builder.services import updater
from album_builder.services.updater import CheckStatus, InstallKind

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
NEW = b"new AppImage bytes " * 100


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config" / "album-builder"


@pytest.fixture
def key() -> tuple[bytes, dict[str, str]]:
    raw = rm.private_raw(Ed25519PrivateKey.generate())
    pub = rm.public_raw_from_private(raw)
    return raw, {rm.key_id(pub): base64.b64encode(pub).decode()}


class FakeTransport:
    """Serves fixed bodies by URL and records every request."""

    def __init__(self, routes: dict[str, bytes | Exception]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, int | None]] = []

    def _body(self, url: str) -> bytes:
        value = self.routes[url]
        if isinstance(value, Exception):
            raise value
        return value

    def get(self, url: str, cap: int) -> bytes:
        self.calls.append((url, cap))
        body = self._body(url)
        if len(body) > cap:
            raise updater.UpdateError("over cap")
        return body

    def stream(self, url: str) -> Iterator[bytes]:
        self.calls.append((url, None))
        body = self._body(url)
        for i in range(0, len(body), 256):
            yield body[i:i + 256]


def _url(name: str) -> str:
    return f"https://example.invalid/{name}"


def _release(raw: bytes, *, tag: str = "v1.2.0", asset: bytes = NEW,
             sums_version: str = "1.2.0", listed_size: int | None = None,
             signed: bool = True, suffix: str = "x86_64.AppImage") -> FakeTransport:
    """A fake GitHub serving one signed release."""
    name = f"AlbumBuilder-{sums_version}-{suffix}"
    sums = f"{hashlib.sha256(asset).hexdigest()}  {name}\n".encode()
    released_name = f"AlbumBuilder-{tag[1:]}-{suffix}"
    assets = [
        {"name": released_name, "browser_download_url": _url(released_name),
         "size": len(asset) if listed_size is None else listed_size},
        {"name": "SHA256SUMS", "browser_download_url": _url("SHA256SUMS"), "size": len(sums)},
    ]
    routes: dict[str, bytes | Exception] = {
        _url(released_name): asset,
        _url("SHA256SUMS"): sums,
    }
    if signed:
        sig = rm.signature_lines(sums, [raw])
        assets.append({"name": "SHA256SUMS.sig",
                       "browser_download_url": _url("SHA256SUMS.sig"), "size": len(sig)})
        routes[_url("SHA256SUMS.sig")] = sig
    routes[updater.LATEST_URL] = json.dumps({
        "tag_name": tag, "body": "What's new", "html_url": "https://example.invalid/r",
        "assets": assets,
    }).encode()
    return FakeTransport(routes)


def _check(transport, trusted, *, skipped=None, running="1.1.0",
           kind=InstallKind.APPIMAGE):
    return updater.check_release(
        transport, running=running, kind=kind, skipped=skipped, trusted=trusted,
    )


# Spec: TC-28-01
def test_install_kind(tmp_path: Path) -> None:
    appdir = tmp_path / "AppDir"
    package = appdir / "opt" / "site-packages" / "album_builder"
    package.mkdir(parents=True)
    image = tmp_path / "AlbumBuilder.AppImage"
    image.write_bytes(b"x")
    elsewhere = tmp_path / "other" / "album_builder"
    elsewhere.mkdir(parents=True)

    def kind(environ=None, *, platform="linux", frozen=False, package_dir=package,
             executable=tmp_path / "AlbumBuilder.exe"):
        return updater.install_kind(
            environ=environ or {}, platform=platform, frozen=frozen,
            executable=executable, package_dir=package_dir,
        )

    assert kind() is InstallKind.NONE
    # Inherited from another AppImage: APPIMAGE names a file, APPDIR is elsewhere.
    assert kind({"APPIMAGE": str(image), "APPDIR": str(appdir)},
                package_dir=elsewhere) is InstallKind.NONE
    assert kind({"APPIMAGE": str(image), "APPDIR": str(appdir)}) is InstallKind.APPIMAGE
    assert kind({"APPIMAGE": str(tmp_path / "gone"), "APPDIR": str(appdir)}) is InstallKind.NONE

    exe = tmp_path / "win" / "AlbumBuilder.exe"
    exe.parent.mkdir()
    marker = exe.parent / "install-kind.txt"
    marker.write_text(" installer\n")
    assert kind(platform="win32", frozen=True, executable=exe) is InstallKind.WINDOWS
    marker.write_text("msi\n")
    assert kind(platform="win32", frozen=True, executable=exe) is InstallKind.WINDOWS_MSI
    assert updater.updates_enabled(InstallKind.WINDOWS_MSI)
    marker.write_text("portable")
    assert kind(platform="win32", frozen=True, executable=exe) is InstallKind.NONE
    marker.unlink()
    assert kind(platform="win32", frozen=True, executable=exe) is InstallKind.NONE
    marker.write_text("installer")
    assert kind(platform="linux", frozen=True, executable=exe) is InstallKind.NONE
    assert kind(platform="win32", frozen=False, executable=exe) is InstallKind.NONE


# Spec: TC-28-01
def test_no_request_when_kind_none(xdg_config: Path, key) -> None:
    transport = _release(key[0])
    assert not updater.claim_daily_check(InstallKind.NONE, NOW)
    assert not updater.updates_enabled(InstallKind.NONE)
    assert transport.calls == []
    assert not (xdg_config / "settings.json").exists()


# Spec: TC-28-02
def test_daily_due(xdg_config: Path, key) -> None:
    transport = _release(key[0])

    def daily(now: datetime) -> int:
        before = len(transport.calls)
        if updater.claim_daily_check(InstallKind.APPIMAGE, now):
            _check(transport, key[1])
        return len(transport.calls) - before

    assert daily(NOW) > 0  # never checked before
    assert daily(NOW + timedelta(hours=23)) == 0
    assert daily(NOW + timedelta(hours=24)) > 0
    # A failing request still waits a day: last_check was written first.
    transport.routes[updater.LATEST_URL] = urllib.error.URLError("offline")
    assert daily(NOW + timedelta(hours=48)) == 1
    assert settings.read_updates().last_check == NOW + timedelta(hours=48)
    assert daily(NOW + timedelta(hours=49)) == 0
    # A clock set back: last_check more than an hour in the future.
    settings.write_updates(UpdateSettings(last_check=NOW + timedelta(hours=2)))
    assert daily(NOW) == 1
    settings.write_updates(UpdateSettings(auto_check=False))
    assert daily(NOW + timedelta(days=9)) == 0


# Spec: TC-28-04
def test_check_outcomes(key) -> None:
    raw, trusted = key
    result = _check(_release(raw), trusted)
    assert result.status is CheckStatus.OFFER
    assert result.offer.version == "1.2.0"
    assert result.offer.asset_name == "AlbumBuilder-1.2.0-x86_64.AppImage"
    assert _check(_release(raw), trusted, running="1.2.0").status is CheckStatus.NEWEST
    assert _check(_release(raw), trusted, skipped="1.2.0").status is CheckStatus.NEWEST
    # Not signed yet, or signed by a key the app does not trust: not ready.
    assert _check(_release(raw, signed=False), trusted).status is CheckStatus.NOT_READY
    assert _check(_release(raw), {}).status is CheckStatus.NOT_READY
    offline = _release(raw)
    offline.routes[updater.LATEST_URL] = urllib.error.URLError("offline")
    assert _check(offline, trusted).status is CheckStatus.FAILED


def _install(transport, trusted, target: Path, **kwargs) -> None:
    result = _check(transport, trusted)
    if result.status is not CheckStatus.OFFER:
        raise updater.UpdateError(result.status)
    updater.install_appimage(transport, result.offer, target, **kwargs)


# Spec: TC-28-06
def test_download_gate(tmp_path: Path, key) -> None:
    raw, trusted = key
    target = tmp_path / "AlbumBuilder-1.1.0-x86_64.AppImage"
    target.write_bytes(b"old")
    target.chmod(0o755)
    stamp = target.stat().st_mtime_ns

    def unchanged() -> None:
        assert target.read_bytes() == b"old"
        assert target.stat().st_mtime_ns == stamp
        assert sorted(p.name for p in tmp_path.iterdir()) == [target.name]

    # A wrong hash: the asset served is not the one SHA256SUMS lists. Same
    # length, so only the hash check can refuse it.
    bad = _release(raw)
    bad.routes[_url("AlbumBuilder-1.2.0-x86_64.AppImage")] = NEW[:-1] + b"!"
    with pytest.raises(updater.UpdateError):
        _install(bad, trusted, target)
    unchanged()

    # A body over the listed size.
    with pytest.raises(updater.UpdateError):
        _install(_release(raw, listed_size=len(NEW) - 1), trusted, target)
    unchanged()

    # A cancel mid-stream.
    calls = iter(range(10**6))
    with pytest.raises(updater.UpdateCancelled):
        _install(_release(raw), trusted, target, should_stop=lambda: next(calls) >= 2)
    unchanged()

    # An old signed SHA256SUMS replayed under a new tag.
    with pytest.raises(updater.UpdateError):
        _install(_release(raw, tag="v1.3.0", sums_version="1.2.0"), trusted, target)
    unchanged()

    # A matching download replaces the target.
    seen: list[tuple[int, int]] = []
    _install(_release(raw), trusted, target,
             progress=lambda done, total: seen.append((done, total)))
    assert target.read_bytes() == NEW
    assert seen[-1] == (len(NEW), len(NEW))
    assert sorted(p.name for p in tmp_path.iterdir()) == [target.name]


# Spec: TC-28-07
def test_appimage_replace(tmp_path: Path, key, monkeypatch: pytest.MonkeyPatch) -> None:
    raw, trusted = key
    target = tmp_path / "AlbumBuilder-1.1.0-x86_64.AppImage"
    target.write_bytes(b"old")
    target.chmod(0o755)
    replaces: list[tuple[str, str]] = []
    real_replace = os.replace
    monkeypatch.setattr(updater.os, "replace",
                        lambda a, b: (replaces.append((str(a), str(b))), real_replace(a, b)))
    _install(_release(raw), trusted, target)
    assert target.read_bytes() == NEW
    assert target.stat().st_mode & 0o777 == 0o755
    assert replaces == [(str(tmp_path / f".{target.name}.update"), str(target))]


# Spec: TC-28-14
def test_msi_check_wants_the_msi(key) -> None:
    raw, trusted = key
    # Signed and listing the .msi: on offer, naming the .msi.
    result = _check(_release(raw, suffix="windows-x64.msi"), trusted,
                    kind=InstallKind.WINDOWS_MSI)
    assert result.status is CheckStatus.OFFER
    assert result.offer.asset_name == "AlbumBuilder-1.2.0-windows-x64.msi"
    assert result.offer.page_url == "https://example.invalid/r"
    # A release listing only the setup .exe is not ready for an MSI copy.
    result = _check(_release(raw, suffix="windows-x64-setup.exe"), trusted,
                    kind=InstallKind.WINDOWS_MSI)
    assert result.status is CheckStatus.NOT_READY


# Spec: TC-28-08
def test_windows_install_gate(tmp_path: Path, key) -> None:
    raw, trusted = key
    setup = "windows-x64-setup.exe"
    folder = tmp_path / "updates"
    assert updater.updates_enabled(InstallKind.WINDOWS)
    # A portable zip (no install-kind.txt, or one not reading "installer")
    # is NONE, which never checks, so it never reaches an installer.
    exe = tmp_path / "zip" / "AlbumBuilder.exe"
    exe.parent.mkdir()
    for marker in (None, "portable"):
        if marker is not None:
            (exe.parent / "install-kind.txt").write_text(marker)
        kind = updater.install_kind(environ={}, platform="win32", frozen=True,
                                    executable=exe, package_dir=tmp_path)
        assert not updater.updates_enabled(kind)

    def install(transport):
        result = _check(transport, trusted, kind=InstallKind.WINDOWS)
        assert result.status is CheckStatus.OFFER
        return updater.install_windows(transport, result.offer, folder, pid=4321)

    # A wrong hash: nothing to launch, and no file left behind.
    bad = _release(raw, suffix=setup)
    bad.routes[_url(f"AlbumBuilder-1.2.0-{setup}")] = NEW[:-1] + b"!"
    with pytest.raises(updater.UpdateError):
        install(bad)
    assert list(folder.iterdir()) == []

    # A matching download is renamed without .part, and the launch names that
    # file, in that folder, in the installer's quiet update mode.
    launch = install(_release(raw, suffix=setup))
    installer = folder / f"AlbumBuilder-1.2.0-{setup}"
    assert sorted(folder.iterdir()) == [installer]
    assert installer.read_bytes() == NEW
    assert launch.program == installer
    assert launch.arguments == (*updater.INSTALLER_UPDATE_SWITCHES, "/WAITPID=4321")


# Spec: TC-28-08
def test_windows_update_cleanup(tmp_path: Path) -> None:
    folder = tmp_path / "updates"
    # No folder: nothing to report.
    assert not updater.finish_windows_update(folder, "1.2.0")
    # The installer that just ran is this version: it worked.
    folder.mkdir()
    (folder / "AlbumBuilder-1.2.0-windows-x64-setup.exe").write_bytes(b"x")
    assert not updater.finish_windows_update(folder, "1.2.0")
    assert not folder.exists()
    # A newer installer is still waiting: the update did not install. Said once.
    folder.mkdir()
    (folder / "AlbumBuilder-1.10.0-windows-x64-setup.exe").write_bytes(b"x")
    (folder / "AlbumBuilder-1.10.0-windows-x64-setup.exe.part").write_bytes(b"x")
    assert updater.finish_windows_update(folder, "1.9.0")
    assert not folder.exists()
    assert not updater.finish_windows_update(folder, "1.9.0")


# Spec: TC-28-09
def test_transport_limits() -> None:
    handler = updater.HttpsOnlyRedirect()
    request = urllib.request.Request("https://api.github.com/x")
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(request, io.BytesIO(), 302, "Found", {}, "http://evil.invalid/x")
    assert handler.redirect_request(
        request, io.BytesIO(), 302, "Found", {}, "https://objects.example/x",
    ) is not None

    with pytest.raises(updater.UpdateError):
        updater.read_capped(io.BytesIO(b"x" * 11), 10)
    assert updater.read_capped(io.BytesIO(b"x" * 10), 10) == b"x" * 10
    with pytest.raises(updater.UpdateError):
        updater.HttpsTransport().get("http://api.github.com/x", 10)

    # Each kind of response is read to its own cap.
    raw = rm.private_raw(Ed25519PrivateKey.generate())
    transport = _release(raw)
    _check(transport, {})
    caps = dict(transport.calls)
    assert caps[updater.LATEST_URL] == 1 << 20
    assert caps[_url("SHA256SUMS")] == 64 << 10
    assert caps[_url("SHA256SUMS.sig")] == 1 << 10
    assert updater.MAX_ASSET_BYTES == 1 << 30
