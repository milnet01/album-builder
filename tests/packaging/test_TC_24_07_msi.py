"""Spec 24 §4.8 - the Windows MSI (MUSI-0407): what the WiX source, the build
script and the workflows must say so the MSI installs for all users, upgrades
in place, and is the copy Spec 28 calls WINDOWS_MSI. The MSI itself builds and
runs only on the Windows runner (windows.yml), so these read the files as text."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from album_builder.domain import release_manifest as rm

ROOT = Path(__file__).resolve().parents[2]
WXS = ROOT / "packaging" / "windows" / "album-builder.wxs"
MARKER = ROOT / "packaging" / "windows" / "install-kind-msi.txt"
BUILD = ROOT / "packaging" / "build-windows.ps1"
WINDOWS_YML = ROOT / ".github" / "workflows" / "windows.yml"
SIGN_YML = ROOT / ".github" / "workflows" / "release-sign.yml"
NS = {"w": "http://wixtoolset.org/schemas/v4/wxs"}

# Fixed for good (INV-24-15): a new UpgradeCode would make the next MSI
# install a second copy beside the first instead of upgrading it.
UPGRADE_CODE = "FE9BFD3E-3FCD-45FD-B691-6F0321461D0F"


def _package() -> ET.Element:
    package = ET.parse(WXS).getroot().find("w:Package", NS)
    assert package is not None
    return package


# Spec: TC-24-07
def test_msi_installs_for_all_users_and_upgrades_in_place() -> None:
    package = _package()
    assert package.get("Scope") == "perMachine"
    assert package.get("UpgradeCode") == UPGRADE_CODE
    assert package.find("w:MajorUpgrade", NS) is not None
    folder = package.find("w:StandardDirectory[@Id='ProgramFiles64Folder']/w:Directory", NS)
    assert folder is not None
    assert folder.get("Name") == "Album Builder"
    # The whole bundle goes in.
    assert folder.find("w:Files", NS).get("Include") == r"$(var.BundleDir)\**"


# Spec: TC-24-07
def test_msi_writes_the_marker_the_updater_reads() -> None:
    assert MARKER.read_text(encoding="ascii").strip() == "msi"
    files = [f for f in _package().iter(f"{{{NS['w']}}}File")
             if f.get("Source", "").endswith("install-kind-msi.txt")]
    assert len(files) == 1
    assert files[0].get("Name") == "install-kind.txt"


# Spec: TC-24-07
def test_msi_is_named_as_spec_28_expects() -> None:
    script = BUILD.read_text(encoding="utf-8")
    out = re.search(r'\$Msi\s*=\s*Join-Path \$Dist "([^"]+)"', script)
    assert out is not None
    built = out.group(1).replace("$Version", "1.2.0")
    assert built == rm.asset_name((1, 2, 0), "windows-msi")


# Spec: TC-24-07
def test_build_pins_wix_by_version_and_hash() -> None:
    script = BUILD.read_text(encoding="utf-8")
    assert re.search(r'\$WixVersion\s*=\s*"\d+\.\d+\.\d+"', script)
    assert re.search(r'\$WixSha256\s*=\s*"[0-9a-f]{64}"', script)
    assert "api.nuget.org/v3-flatcontainer/wix/$WixVersion/wix.$WixVersion.nupkg" in script
    # The hash is checked before WiX runs, and the licence is accepted by id
    # (owner, 2026-11-18).
    assert script.index("$WixSha256") < script.index("wix.dll")
    assert "-acceptEula wix7" in script


# Spec: TC-24-07
def test_workflows_ship_and_sign_the_msi() -> None:
    steps = yaml.safe_load(WINDOWS_YML.read_text())["jobs"]["windows"]["steps"]
    uploads = [s for s in steps if "softprops/action-gh-release" in s.get("uses", "")]
    assert len(uploads) == 1
    assert "dist/AlbumBuilder-*-windows-x64.msi" in uploads[0]["with"]["files"]
    smoke = [s for s in steps if "msiexec" in s.get("run", "")]
    assert len(smoke) == 1
    assert "'msi'" in smoke[0]["run"] or '"msi"' in smoke[0]["run"]
    sign_steps = yaml.safe_load(SIGN_YML.read_text())["jobs"]["sign"]["steps"]
    wait = next(s["run"] for s in sign_steps if "want=(" in s.get("run", ""))
    assert '"AlbumBuilder-$v-windows-x64.msi"' in wait
