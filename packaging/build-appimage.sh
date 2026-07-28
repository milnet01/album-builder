#!/usr/bin/env bash
# Album Builder - AppImage build (Spec 23 / Phase Dist-2).
#
# One script, run locally (`./packaging/build-appimage.sh`) or by CI
# (.github/workflows/appimage.yml calls it unchanged - INV-23-9). It builds the
# AppImage INSIDE a digest-pinned ubuntu:22.04 container so a local build on any
# host matches the CI release and the glibc floor is the container's, not the
# build host's (INV-23-7). Output: dist/AlbumBuilder-<version>-x86_64.AppImage.
set -euo pipefail

# --- Pinned build inputs (INV-23-10). Immutable refs, refreshed on the
# dependency-currency sweep - never `latest`/`HEAD`/a branch. -------------------
BASE_IMAGE="ubuntu:22.04@sha256:0d779ea97881505f5ef0039336ee85edba27519bdba968c284c86ee066a973c8"
PYTHON_APPIMAGE_TAG="python3.12.7"                                   # niess/python-appimage release
PYTHON_APPIMAGE_ASSET="python3.12.7-cp312-cp312-manylinux2014_x86_64.AppImage"
APPIMAGETOOL_VERSION="1.9.0"                                         # AppImage/appimagetool release

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# =============================================================================
# OUTER: not yet in the container -> re-run this script inside the pinned image.
# apt-get (stage 4) needs root, so the container runs as root; the output file is
# chowned back to the invoking user at the end (via HOST_UID/HOST_GID) so a local
# build does not leave a root-owned dist/ (Spec 23 Section 6).
# =============================================================================
if [ "${_ALBUM_BUILDER_IN_CONTAINER:-}" != "1" ]; then
    runtime=""
    for c in podman docker; do
        if command -v "$c" >/dev/null 2>&1; then runtime="$c"; break; fi
    done
    if [ -z "$runtime" ]; then
        echo "build-appimage: need Docker or Podman to run the pinned build container." >&2
        echo "  openSUSE: sudo zypper install podman   Debian/Ubuntu: sudo apt install podman" >&2
        exit 1
    fi
    mkdir -p "$REPO_ROOT/dist"
    echo "build-appimage: building inside $BASE_IMAGE via $runtime ..."
    exec "$runtime" run --rm \
        -e _ALBUM_BUILDER_IN_CONTAINER=1 \
        -e HOST_UID="$(id -u)" \
        -e HOST_GID="$(id -g)" \
        -e PYTHON_APPIMAGE_TAG="$PYTHON_APPIMAGE_TAG" \
        -e PYTHON_APPIMAGE_ASSET="$PYTHON_APPIMAGE_ASSET" \
        -e APPIMAGETOOL_VERSION="$APPIMAGETOOL_VERSION" \
        -v "$REPO_ROOT:/src:ro" \
        -v "$REPO_ROOT/dist:/out:rw" \
        "$BASE_IMAGE" \
        /src/packaging/build-appimage.sh
fi

# =============================================================================
# INNER: everything below runs as root inside ubuntu:22.04.
# =============================================================================
export DEBIAN_FRONTEND=noninteractive
SRC=/src
BUILD="$(mktemp -d)"
APPDIR="$BUILD/AppDir"
trap 'rm -rf "$BUILD"' EXIT

# --- Stage 1: version, from the runtime single source version.py (INV-23-3). ---
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$SRC/src/album_builder/version.py")"
if [ -z "$VERSION" ]; then
    echo "stage 1: could not read __version__ from src/album_builder/version.py" >&2
    exit 1
fi
echo "stage 1: version $VERSION"

# --- Prereqs: fetch tools + the WeasyPrint native stack + a font. --------------
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    ca-certificates wget file desktop-file-utils patchelf \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1 libglib2.0-0 \
    fonts-dejavu-core >/dev/null

# --- Stage 2: python-appimage manylinux CPython -> relocatable AppDir. ----------
echo "stage 2: fetching $PYTHON_APPIMAGE_ASSET"
wget -q "https://github.com/niess/python-appimage/releases/download/${PYTHON_APPIMAGE_TAG}/${PYTHON_APPIMAGE_ASSET}" \
    -O "$BUILD/python.AppImage"
chmod +x "$BUILD/python.AppImage"
( cd "$BUILD" && ./python.AppImage --appimage-extract >/dev/null )
mv "$BUILD/squashfs-root" "$APPDIR"
PYBIN="$(echo "$APPDIR"/opt/python*/bin/python3)"
[ -x "$PYBIN" ] || { echo "stage 2: no interpreter in the extracted AppDir" >&2; exit 1; }

# --- Stage 3: pip install the app + requirements (installs the PACKAGE, not the
# repo checkout, so no pyproject.toml lands beside it - INV-23-4). ---------------
echo "stage 3: pip install"
"$PYBIN" -m pip install --no-warn-script-location -q --upgrade pip
"$PYBIN" -m pip install --no-warn-script-location -q -r "$SRC/requirements.txt"
"$PYBIN" -m pip install --no-warn-script-location -q "$SRC"

# --- Stage 4: bundle WeasyPrint's native library closure + font (INV-23-2). -----
echo "stage 4: bundling native libraries"
mkdir -p "$APPDIR/usr/lib"
weasy_libs="libgobject-2.0.so.0 libpango-1.0.so.0 libpangoft2-1.0.so.0 \
libharfbuzz.so.0 libharfbuzz-subset.so.0 libfontconfig.so.1"
# Copy each named soname plus its ldd closure, minus the driver/core libraries
# that must come from the host (libGL is driver-coupled; libc/ld are the base).
copy_with_closure() {
    local soname="$1" src
    src="$(ldconfig -p | awk -v n="$soname" '$1==n {print $NF; exit}')"
    [ -n "$src" ] || { echo "stage 4: $soname not found after apt-get" >&2; exit 1; }
    cp -uL "$src" "$APPDIR/usr/lib/"
    ldd "$src" | awk '/=> \//{print $3}' | while read -r dep; do
        case "$(basename "$dep")" in
            libc.so.*|libm.so.*|libdl.so.*|libpthread.so.*|librt.so.*|\
            ld-linux*.so.*|libGL.so.*|libEGL.so.*|libGLdispatch.so.*) continue ;;
        esac
        cp -uL "$dep" "$APPDIR/usr/lib/"
    done
}
for lib in $weasy_libs; do copy_with_closure "$lib"; done
# Font + a minimal fontconfig config at the exact path AppRun sets (Section 4.3).
mkdir -p "$APPDIR/usr/share/fonts" "$APPDIR/etc/fonts"
cp -uL /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf "$APPDIR/usr/share/fonts/"
cat > "$APPDIR/etc/fonts/fonts.conf" <<'FONTS'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>/usr/share/fonts</dir>
  <cachedir>/tmp/fontconfig-cache</cachedir>
</fontconfig>
FONTS

# --- Stage 5: AppRun, .desktop, icon. ------------------------------------------
echo "stage 5: launcher + desktop integration"
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# Exec'd directly by the AppImage runtime (no shell), so the shebang is
# mandatory - without it execve fails ENOEXEC (Spec 23 INV-23-1).
HERE="$(dirname "$(readlink -f "$0")")"
export APPDIR="${APPDIR:-$HERE}"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$LD_LIBRARY_PATH"
export FONTCONFIG_FILE="$APPDIR/etc/fonts/fonts.conf"
# Resolve the bundled interpreter WITHOUT a quoted glob (a glob does not expand
# in double quotes, so "$APPDIR/opt/python*/..." would reach exec literally).
for _py in "$APPDIR"/opt/python*/bin/python3; do PYTHON="$_py"; break; done
[ -x "$PYTHON" ] || { echo "AppRun: bundled interpreter missing under $APPDIR/opt" >&2; exit 1; }
exec "$PYTHON" -m album_builder "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

sed 's|@@LAUNCHER@@|AppRun|g' "$SRC/packaging/album-builder.desktop.in" \
    > "$APPDIR/album-builder.desktop"
mkdir -p "$APPDIR/usr/share/applications"
cp "$APPDIR/album-builder.desktop" "$APPDIR/usr/share/applications/"
desktop-file-validate "$APPDIR/album-builder.desktop"

cp "$SRC/assets/album-builder.svg" "$APPDIR/album-builder.svg"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp "$SRC/assets/album-builder.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"

# --- Stage 6: package with appimagetool (itself an AppImage; no FUSE in the
# container, so run it extracted - INV-23-9 keeps all of this in the script). ---
echo "stage 6: appimagetool"
wget -q "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-x86_64.AppImage" \
    -O "$BUILD/appimagetool.AppImage"
chmod +x "$BUILD/appimagetool.AppImage"
( cd "$BUILD" && ./appimagetool.AppImage --appimage-extract >/dev/null )
OUT="/out/AlbumBuilder-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$BUILD/squashfs-root/AppRun" "$APPDIR" "$OUT"

# Hand the artifact back to the invoking user, not root (Spec 23 Section 6).
chown "${HOST_UID:-0}:${HOST_GID:-0}" "$OUT"
echo "done: $OUT"
