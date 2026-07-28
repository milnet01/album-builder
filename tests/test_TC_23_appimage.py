"""Spec 23 (AppImage distribution) - headless entry points and desktop entry.

Covers the unit-testable arg paths of INV-23-1/2 and the desktop-template half
of INV-23-6. The real-bundle checks (INV-23-1/2 against a built AppImage,
INV-23-4/5 against the extracted AppDir, and INV-23-6 against the bundled
`.desktop`) live in `.github/workflows/appimage.yml`, not here: a real AppImage
build is far too heavy for the unit suite (Spec 23 §7).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from album_builder import app as app_module
from album_builder.version import __version__

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_TEMPLATE = PROJECT_ROOT / "packaging" / "album-builder.desktop.in"


def _forbid_qapplication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make constructing a QApplication fail the test.

    The headless flags must return before any QApplication is created (Spec 23
    Section 4.4); this is also what makes each test fail against pre-change
    `run()`, which constructed QApplication as its first statement.
    """

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "QApplication was constructed; the headless flag should have returned first"
        )

    monkeypatch.setattr(app_module, "QApplication", _boom)


def test_version_flag(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # Spec: TC-23-01
    _forbid_qapplication(monkeypatch)
    monkeypatch.setattr(app_module.sys, "argv", ["album-builder", "--version"])
    assert app_module.run() == 0
    assert capsys.readouterr().out.strip() == __version__


def test_version_short_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Spec: TC-23-01
    _forbid_qapplication(monkeypatch)
    monkeypatch.setattr(app_module.sys, "argv", ["album-builder", "-V"])
    assert app_module.run() == 0
    assert capsys.readouterr().out.strip() == __version__


@pytest.mark.slow
def test_selftest(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # Spec: TC-23-02
    _forbid_qapplication(monkeypatch)
    monkeypatch.setattr(app_module.sys, "argv", ["album-builder", "--selftest"])
    assert app_module.run() == 0
    assert "ok" in capsys.readouterr().out


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None,
    reason="desktop-file-validate not installed",
)
def test_desktop_valid(tmp_path: Path) -> None:
    # Spec: TC-23-03
    rendered = DESKTOP_TEMPLATE.read_text(encoding="utf-8").replace("@@LAUNCHER@@", "AppRun")
    desktop = tmp_path / "album-builder.desktop"
    desktop.write_text(rendered, encoding="utf-8")
    result = subprocess.run(
        ["desktop-file-validate", str(desktop)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
