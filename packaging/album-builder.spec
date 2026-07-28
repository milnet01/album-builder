# PyInstaller spec - Album Builder Windows one-folder bundle (Spec 24).
#
# Driven by packaging/build-windows.ps1 (INV-24-9): that script installs the
# MSYS2 GTK stack, stages the WeasyPrint DLL closure + a font, then runs
# `pyinstaller packaging/album-builder.spec`. Not meant to be run by hand.
#
# The exact DLL closure, hidden imports and data files are resolved at build
# time and proven by `AlbumBuilder.exe --selftest` on the runner (Spec 24 Section
# 4.2 / INV-24-2); this file collects the staged inputs the build script prepared.
import os
from pathlib import Path

ROOT = Path(os.environ.get("ALBUM_BUILDER_ROOT", ".")).resolve()

# GTK / Pango / HarfBuzz / fontconfig DLL closure, staged by the build script
# from MSYS2's mingw64/bin (Spec 24 Section 4.2). Placed at the bundle root so
# the Section 4.3a runtime hook's os.add_dll_directory() resolves them.
dll_dir = Path(os.environ["WIN_DLL_DIR"])
binaries = [(str(p), ".") for p in dll_dir.glob("*.dll")]

# Bundled font + fontconfig config (Spec 24 Section 4.2), under fonts/.
font_dir = Path(os.environ["WIN_FONT_DIR"])
datas = [(str(p), "fonts") for p in font_dir.iterdir() if p.is_file()]

# The Jinja2 report template is loaded via FileSystemLoader(__file__ /
# "templates"), so it must sit beside report.py in the bundle tree.
templates = ROOT / "src" / "album_builder" / "services" / "templates"
datas += [
    (str(p), "album_builder/services/templates")
    for p in templates.glob("*") if p.is_file()
]

icon = ROOT / "packaging" / "album-builder.ico"

a = Analysis(
    [str(ROOT / "src" / "album_builder" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["album_builder"],
    runtime_hooks=[str(ROOT / "packaging" / "pyi_rth_weasyprint_dlls.py")],
    excludes=["torch", "whisperx", "tkinter"],  # Spec 24 INV-24-5 (ML stack out)
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AlbumBuilder",
    console=False,                       # GUI app - no console window
    icon=str(icon) if icon.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="AlbumBuilder",                 # -> dist/AlbumBuilder/
)
