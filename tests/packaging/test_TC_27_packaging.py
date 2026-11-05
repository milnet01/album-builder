"""Spec 27 - openSUSE packages: the wheel, the RPM recipe, the metainfo and
the OBS submit script agree with the source tree.

The installed-package invariants (INV-6..9) live in packaging/obs/rpm-smoke.sh,
which needs a Tumbleweed environment.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from email.parser import HeaderParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RPM_SPEC = ROOT / "packaging" / "obs" / "album-builder.spec"
METAINFO = ROOT / "packaging" / "linux" / "io.github.milnet01.AlbumBuilder.metainfo.xml"
SUBMIT = ROOT / "packaging" / "obs" / "obs-submit.sh"

# Spec 27 INV-3: requirements.txt name -> openSUSE package name.
RPM_NAMES = {
    "PyQt6": "python3-PyQt6",
    "mutagen": "python3-mutagen",
    "platformdirs": "python3-platformdirs",
    "Jinja2": "python3-Jinja2",
    "weasyprint": "python3-weasyprint",
    "Pillow": "python3-Pillow",
}


def _requirements() -> dict[str, str]:
    """requirements.txt as {name: floor}."""
    out = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, floor = line.split(">=")
            out[name.strip()] = floor.strip()
    return out


def _tracked(prefix: str) -> list[str]:
    out = subprocess.run(
        # Tracked files plus new ones that are not ignored, so an
        # uncommitted data file counts too.
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others",
         "--exclude-standard", prefix],
        capture_output=True, check=True, text=True,
    ).stdout
    return [p for p in out.split("\0") if p]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> zipfile.ZipFile:
    """A wheel built from a copy of the tracked files in the working tree."""
    pytest.importorskip("setuptools")
    tree = tmp_path_factory.mktemp("tree")
    for rel in _tracked("."):
        src = ROOT / rel
        if src.is_file():
            dest = tree / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "-q", "-w", str(out), str(tree)],
        check=True, capture_output=True,
    )
    (whl,) = out.glob("*.whl")
    return zipfile.ZipFile(whl)


# Spec: TC-27-01
def test_wheel_carries_every_tracked_file(wheel) -> None:
    expected = {p.removeprefix("src/") for p in _tracked("src/album_builder")}
    in_wheel = set(wheel.namelist())
    assert expected - in_wheel == set()


# Spec: TC-27-02
def test_wheel_metadata(wheel) -> None:
    (meta_name,) = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
    meta = HeaderParser().parsestr(wheel.read(meta_name).decode())
    requires = sorted(meta.get_all("Requires-Dist") or [])
    assert requires == sorted(f"{n}>={f}" for n, f in _requirements().items())
    (ep_name,) = [n for n in wheel.namelist() if n.endswith(".dist-info/entry_points.txt")]
    entry_points = wheel.read(ep_name).decode()
    assert re.search(r"^album-builder = album_builder\.app:run$", entry_points, re.M)


def _spec_lines(tag: str) -> dict[str, str]:
    """`Tag: name >= floor` lines of the RPM spec as {name: floor}; '' for no floor."""
    out = {}
    for line in RPM_SPEC.read_text().splitlines():
        m = re.match(rf"^{tag}:\s+(\S+)(?:\s+>=\s+(\S+))?\s*$", line)
        if m:
            out[m.group(1)] = m.group(2) or ""
    return out


# Spec: TC-27-03
def test_rpm_requires_match_requirements() -> None:
    reqs = _requirements()
    assert set(reqs) == set(RPM_NAMES), "add the new dependency to RPM_NAMES and the spec"
    for tag in ("Requires", "BuildRequires"):
        lines = _spec_lines(tag)
        for name, floor in reqs.items():
            assert lines.get(RPM_NAMES[name]) == floor, f"{tag}: {RPM_NAMES[name]} >= {floor}"
    text = RPM_SPEC.read_text().lower()
    assert "torch" not in text
    assert "whisperx" not in text


def _project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


# Spec: TC-27-04
def test_versions_agree() -> None:
    from album_builder.version import __version__

    (spec_version,) = re.findall(r"^Version:\s+(\S+)$", RPM_SPEC.read_text(), re.M)
    assert spec_version == _project_version() == __version__


# Spec: TC-27-05
def test_metainfo() -> None:
    root = ET.parse(METAINFO).getroot()
    assert root.findtext("id") == "io.github.milnet01.AlbumBuilder"
    assert root.findtext("launchable") == "album-builder.desktop"
    first = root.find("releases/release")
    assert first is not None
    assert first.get("version") == _project_version()
    tool = shutil.which("appstreamcli")
    if tool is None:
        pytest.skip("appstreamcli not installed; the RPM's %check validates instead")
    run = subprocess.run([tool, "validate", "--no-net", str(METAINFO)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.fixture
def submit_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A throwaway repo holding the submit script, pyproject at 2.0.0, tag
    v2.0.0, and a stub `osc` that only records its arguments."""
    repo = tmp_path / "repo"
    (repo / "packaging" / "obs").mkdir(parents=True)
    shutil.copy2(SUBMIT, repo / "packaging" / "obs" / "obs-submit.sh")
    shutil.copy2(RPM_SPEC, repo / "packaging" / "obs" / "album-builder.spec")
    (repo / "pyproject.toml").write_text('[project]\nname = "album-builder"\nversion = "2.0.0"\n')
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
                 ["tag", "v2.0.0"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, env=env)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "osc.log"
    stub = bin_dir / "osc"
    # Acts out a checkout, so a script that skipped its refusals would get as
    # far as `osc commit` rather than failing for an unrelated reason.
    stub.write_text(
        f'#!/bin/sh\necho "$@" >> "{log}"\n'
        'if [ "$1" = checkout ]; then mkdir -p "$2/$3"; fi\n'
    )
    stub.chmod(0o755)
    return repo, bin_dir, log


@pytest.mark.parametrize("version", ["3.0.0", "1.0.0"], ids=["no-tag", "version-mismatch"])
# Spec: TC-27-10
def test_submit_refuses(submit_repo, version: str) -> None:
    repo, bin_dir, log = submit_repo
    if version == "1.0.0":
        # The tag exists but pyproject.toml says 2.0.0.
        subprocess.run(["git", "-C", str(repo), "tag", "v1.0.0"], check=True)
    run = subprocess.run(
        ["bash", str(repo / "packaging" / "obs" / "obs-submit.sh"), version],
        capture_output=True, text=True,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )
    assert run.returncode != 0
    assert not log.exists() or "commit" not in log.read_text()
