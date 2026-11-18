"""Spec 24 §4.7 - the Windows installer (MUSI-0406): what the Inno Setup
script, the build script and the workflows must say so the installer and
Spec 28's Windows update agree. The installer itself builds and runs only on
the Windows runner (windows.yml), so these read the files as text."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from album_builder.domain import release_manifest as rm
from album_builder.services import updater

ROOT = Path(__file__).resolve().parents[2]
ISS = ROOT / "packaging" / "windows" / "album-builder.iss"
MARKER = ROOT / "packaging" / "windows" / "install-kind.txt"
BUILD = ROOT / "packaging" / "build-windows.ps1"
WINDOWS_YML = ROOT / ".github" / "workflows" / "windows.yml"
SIGN_YML = ROOT / ".github" / "workflows" / "release-sign.yml"


def _setup_keys() -> dict[str, str]:
    """The [Setup] section's Key=Value lines."""
    text = ISS.read_text(encoding="utf-8")
    section = text.split("[Setup]", 1)[1].split("\n[", 1)[0]
    keys = {}
    for line in section.splitlines():
        if "=" in line and not line.lstrip().startswith(";"):
            name, value = line.split("=", 1)
            keys[name.strip()] = value.strip()
    return keys


# Spec: TC-24-05
def test_installer_is_per_user_and_named_as_spec_28_expects() -> None:
    keys = _setup_keys()
    assert keys["PrivilegesRequired"] == "lowest"
    assert "PrivilegesRequiredOverridesAllowed" not in keys
    assert keys["DefaultDirName"] == r"{autopf}\Album Builder"
    # Spec 28 §4.4 item 3 downloads exactly this name.
    built = keys["OutputBaseFilename"].replace("{#AppVersion}", "1.2.0") + ".exe"
    assert built == rm.asset_name((1, 2, 0), "windows")
    # A fixed AppId: a new one would install a second copy beside the first.
    assert re.fullmatch(r"\{\{[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}\}", keys["AppId"])


# Spec: TC-24-05
def test_installer_writes_the_marker_the_updater_reads() -> None:
    assert MARKER.read_text(encoding="ascii").strip() == "installer"
    text = ISS.read_text(encoding="utf-8")
    assert re.search(r'Source: "[^"]*install-kind\.txt"; DestDir: "\{app\}"', text)


# Spec: TC-24-05
def test_quiet_update_mode_matches_the_updater() -> None:
    text = ISS.read_text(encoding="utf-8")
    # The switches the app passes (Spec 28 §4.6 Windows) are ones Setup knows:
    # /SILENT, /SUPPRESSMSGBOXES and /NORESTART are Inno Setup's own; /UPDATE
    # and /WAITPID are this script's.
    assert set(updater.INSTALLER_UPDATE_SWITCHES) == {
        "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE",
    }
    assert "'/UPDATE'" in text
    assert "{param:WAITPID|0}" in text
    assert "WaitForSingleObject" in text
    # The update mode starts the new version; a normal silent install does not.
    run = text.split("[Run]", 1)[1].split("\n[", 1)[0]
    assert "Check: IsUpdate" in run
    assert "skipifsilent" in run


# Spec: TC-24-05
def test_build_pins_inno_setup_by_version_and_hash() -> None:
    script = BUILD.read_text(encoding="utf-8")
    assert re.search(r'\$InnoSetupVersion\s*=\s*"\d+\.\d+\.\d+"', script)
    assert re.search(r'\$InnoSetupSha256\s*=\s*"[0-9a-f]{64}"', script)
    assert "Get-FileHash" in script
    assert "ISCC.exe" in script


# Spec: TC-24-05
def test_workflows_ship_and_sign_the_installer() -> None:
    steps = yaml.safe_load(WINDOWS_YML.read_text())["jobs"]["windows"]["steps"]
    uploads = [s for s in steps if "softprops/action-gh-release" in s.get("uses", "")]
    assert len(uploads) == 1
    assert "dist/AlbumBuilder-*-windows-x64-setup.exe" in uploads[0]["with"]["files"]
    assert "dist/AlbumBuilder-*-windows-x64.zip" in uploads[0]["with"]["files"]
    sign_steps = yaml.safe_load(SIGN_YML.read_text())["jobs"]["sign"]["steps"]
    wait = next(s["run"] for s in sign_steps if "want=(" in s.get("run", ""))
    assert '"AlbumBuilder-$v-windows-x64-setup.exe"' in wait
