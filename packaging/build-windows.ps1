#requires -Version 5.1
# Album Builder - Windows one-folder bundle (Spec 24 / Phase Dist-3).
#
# One script, the single source of truth for the Windows build (INV-24-9).
# .github/workflows/windows.yml calls it unchanged; it assembles the whole
# bundle and the workflow only smoke-tests + uploads. Unlike the AppImage
# (build-appimage.sh, containerised so a local build == the release), this build
# is NOT reproducible off Windows: PyInstaller freezes the interpreter of the OS
# it runs on, so this runs on a `windows-latest` runner and is verified by CI
# `--selftest` + a manual Windows run (Spec 24 Section 3), never on Linux.
#
# Output: dist\AlbumBuilder-<version>-windows-x64.zip
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# --- Pinned build tooling (INV-24-10). Refreshed on the dependency-currency
# sweep - never a floating `latest`. MSYS2 GTK packages are rolling, like the
# AppImage's un-pinned apt point releases (Spec 23 Section 9). ------------------
$PyInstallerVersion = "6.21.0"          # PyInstaller latest stable
$MsysRoot           = "C:\msys64"       # preinstalled on windows-latest
$MsysBin            = "$MsysRoot\mingw64\bin"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$env:ALBUM_BUILDER_ROOT = $RepoRoot
$Stage    = Join-Path $RepoRoot "packaging\_stage"
$DllDir   = Join-Path $Stage "dlls"
$FontDir  = Join-Path $Stage "fonts"
$Dist     = Join-Path $RepoRoot "dist"

# --- Stage 1: version, from the runtime single source version.py (INV-24-3). ---
$verLine = Get-Content "$RepoRoot\src\album_builder\version.py" |
    Where-Object { $_ -match '^\s*__version__\s*=\s*"(.*)"' } | Select-Object -First 1
if (-not $verLine) { throw "stage 1: could not read __version__ from version.py" }
$Version = $Matches[1]
Write-Host "stage 1: version $Version"

# --- Stage 2: venv + deps + pinned PyInstaller. -------------------------------
Write-Host "stage 2: venv + pip install deps + PyInstaller $PyInstallerVersion"
python -m venv "$Stage\venv"
$Py = "$Stage\venv\Scripts\python.exe"
& $Py -m pip install --upgrade -q pip
& $Py -m pip install -q -r "$RepoRoot\requirements.txt"
& $Py -m pip install -q "pyinstaller==$PyInstallerVersion"

# --- Stage 3: install the MSYS2 GTK / Pango / fontconfig stack. ----------------
# The exact package closure is resolved by pacman on the runner (Spec 24 Section
# 4.2); pango + fontconfig pull GObject / HarfBuzz / glib / freetype / fribidi.
Write-Host "stage 3: MSYS2 GTK stack"
$bash = "$MsysRoot\usr\bin\bash.exe"
& $bash -lc "pacman -S --noconfirm --needed mingw-w64-x86_64-pango mingw-w64-x86_64-fontconfig mingw-w64-x86_64-ttf-dejavu"

# --- Stage 4: stage the WeasyPrint DLL closure (Spec 24 Section 4.2 / INV-24-2).
# Resolve each required DLL's closure with MSYS2 ldd and copy only the mingw64
# DLLs (never the Windows System32 ones, which the target already has). The
# --selftest smoke check (INV-24-2) proves the closure is complete. ------------
Write-Host "stage 4: stage WeasyPrint DLL closure"
New-Item -ItemType Directory -Force -Path $DllDir | Out-Null
# Do the whole ldd-closure copy inside bash (a SINGLE-quoted here-string, so
# PowerShell does not interpolate $d/$3 across the boundary). Inputs cross via
# environment variables. `ldd` resolves the FULL transitive closure; we keep
# only the /mingw64/ DLLs - the Windows System32 deps the target already has.
$env:WB_OUT = (& $bash -lc "cygpath -u '$DllDir'").Trim()
$env:WB_REQUIRED = "libgobject-2.0-0.dll libpango-1.0-0.dll libpangoft2-1.0-0.dll libharfbuzz-0.dll libfontconfig-1.dll"
& $bash -lc @'
set -euo pipefail
mkdir -p "$WB_OUT"
for d in $WB_REQUIRED; do
  src="/mingw64/bin/$d"
  [ -f "$src" ] || { echo "stage 4: required DLL missing: $d" >&2; exit 1; }
  cp -f "$src" "$WB_OUT/"
done
for d in $WB_REQUIRED; do ldd "/mingw64/bin/$d"; done \
  | awk "/=> \/mingw64\//{print \$3}" | sort -u | while read -r dep; do
      [ -f "$dep" ] && cp -f "$dep" "$WB_OUT/"
    done
echo "stage 4: staged $(ls -1 "$WB_OUT" | wc -l) DLL(s)"
'@
if ($LASTEXITCODE -ne 0) { throw "stage 4 (DLL closure) failed" }

# --- Stage 5: font + fontconfig config (Spec 24 Section 4.2). ------------------
# Bundle DejaVu and a fonts.conf that looks in the bundled dir AND the always-
# present Windows font directory, so WeasyPrint has a discoverable font.
Write-Host "stage 5: font + fontconfig config"
New-Item -ItemType Directory -Force -Path $FontDir | Out-Null
$deja = Get-ChildItem "$MsysRoot\mingw64\share\fonts" -Recurse -Filter "DejaVuSans.ttf" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($deja) { Copy-Item -Force $deja.FullName $FontDir }
@'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>.</dir>
  <dir>WINDOWSFONTDIR</dir>
  <cachedir>fontconfig-cache</cachedir>
</fontconfig>
'@ | Set-Content -Encoding ASCII (Join-Path $FontDir "fonts.conf")

# --- Stage 6: PyInstaller one-folder build via the checked-in spec. -----------
Write-Host "stage 6: PyInstaller"
$env:WIN_DLL_DIR  = $DllDir
$env:WIN_FONT_DIR = $FontDir
& $Py -m PyInstaller --noconfirm --clean --distpath "$Dist" `
    --workpath "$Stage\build" "$RepoRoot\packaging\album-builder.spec"

# --- Stage 7: zip the one-folder output. --------------------------------------
$Zip = Join-Path $Dist "AlbumBuilder-$Version-windows-x64.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path (Join-Path $Dist "AlbumBuilder\*") -DestinationPath $Zip
Write-Host "done: $Zip"
