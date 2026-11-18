"""Spec 28 §4.7 - packaging/release-signing.py and release-sign.yml
(TC-28-10, TC-28-11)."""

from __future__ import annotations

import base64
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from album_builder.domain import release_manifest as rm

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packaging" / "release-signing.py"
WORKFLOW = ROOT / ".github" / "workflows" / "release-sign.yml"
SUMS = b"cc" * 32 + b"  AlbumBuilder-1.2.0-x86_64.AppImage\n"


def _load_script():
    spec = importlib.util.spec_from_file_location("release_signing", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generate(tmp_path: Path) -> tuple[str, dict[str, str]]:
    """Run `generate` outside the work tree; return (key line, trusted map)."""
    key_file = tmp_path / "release.key"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "generate", "--out", str(key_file)],
        capture_output=True, text=True, check=True,
    )
    assert key_file.stat().st_mode & 0o777 == 0o600
    line = key_file.read_text().strip()
    entry = next(t for t in result.stdout.splitlines() if t.strip().startswith('"'))
    kid, pub = (part.strip().strip('",') for part in entry.split(":"))
    return line, {kid: pub}


# Spec: TC-28-10
def test_sign_verify_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    line, trusted = _generate(tmp_path)
    script = _load_script()
    sums = tmp_path / "SHA256SUMS"
    sums.write_bytes(SUMS)
    monkeypatch.setenv("RELEASE_SIGNING_KEY", line)
    assert script.main(["sign", str(sums)]) == 0
    # The printed TRUSTED_KEYS entry is the generated key's public half.
    pub = rm.public_raw_from_private(base64.b64decode(line))
    assert trusted == {rm.key_id(pub): base64.b64encode(pub).decode()}

    monkeypatch.setattr(rm, "TRUSTED_KEYS", trusted)
    assert script.main(["verify", str(sums)]) == 0
    # A key the app does not trust fails the release job.
    monkeypatch.setattr(rm, "TRUSTED_KEYS", {})
    assert script.main(["verify", str(sums)]) == 1


# Spec: TC-28-10
def test_generate_refuses_the_work_tree() -> None:
    target = ROOT / "release.key"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "generate", "--out", "./release.key"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode != 0
    assert not target.exists()


# Spec: TC-28-10
def test_sign_refuses_a_bad_key(tmp_path: Path) -> None:
    sums = tmp_path / "SHA256SUMS"
    sums.write_bytes(SUMS)
    env = {**os.environ, "RELEASE_SIGNING_KEY": "not a key"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "sign", str(sums)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert not (tmp_path / "SHA256SUMS.sig").exists()


# Spec: TC-28-11
def test_workflow_shape() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    steps = workflow["jobs"]["sign"]["steps"]
    secret = "secrets.RELEASE_SIGNING_KEY"

    using_secret = [s for s in steps if secret in yaml.safe_dump(s)]
    assert len(using_secret) == 1
    assert secret in using_secret[0]["env"]["RELEASE_SIGNING_KEY"]
    assert secret not in using_secret[0]["run"]

    def index(fragment: str) -> int:
        return next(i for i, s in enumerate(steps) if fragment in s.get("run", ""))

    upload = index("gh release upload")
    assert index("release-signing.py verify") < upload
    assert steps[upload]["run"].split()[4:6] == ["SHA256SUMS", "SHA256SUMS.sig"]
    assert steps[upload]["run"].count("SHA256") == 2


# Spec: TC-28-11
def test_workflow_downloads_outside_the_checkout() -> None:
    # v1.2.0's signing failed on `mkdir assets`: the repository tracks an
    # assets/ folder, and hashing it would have listed the logos too.
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["sign"]["steps"]
    runs = [s.get("run", "") for s in steps]
    download = next(r for r in runs if "gh release download" in r)
    sums = next(r for r in runs if "sha256sum" in r)
    assert 'mkdir "$RUNNER_TEMP/release-assets"' in download
    assert '--dir "$RUNNER_TEMP/release-assets"' in download
    assert 'cd "$RUNNER_TEMP/release-assets"' in sums


# Spec: TC-28-11
def test_workflow_can_sign_an_existing_tag_by_hand() -> None:
    # A re-run uses the tag's own copy of the workflow, so a fixed workflow
    # can only sign an already-published release through a manual run.
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow[True]  # PyYAML reads the bare key `on` as True
    assert triggers["push"]["tags"] == ["v*"]
    assert triggers["workflow_dispatch"]["inputs"]["tag"]["required"] is True
    runs = yaml.safe_dump(workflow["jobs"]["sign"]["steps"])
    assert "github.ref_name" not in runs.replace("inputs.tag || github.ref_name", "")
