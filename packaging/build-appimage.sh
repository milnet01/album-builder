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
PYTHON_APPIMAGE_TAG="python3.13"                                     # niess/python-appimage (per-minor tag); 3.13 == CI's tested interpreter
PYTHON_APPIMAGE_ASSET="python3.13.14-cp313-cp313-manylinux2014_x86_64.AppImage"
APPIMAGETOOL_VERSION="1.9.1"                                         # AppImage/appimagetool latest stable

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
    # Chown the output back to the invoking user ONLY when the container runs as
    # real root (rootful, e.g. Docker on CI) - there the artifact would otherwise
    # be root-owned. Under ROOTLESS podman the userns already maps container-root
    # to the host user, so the file is correctly owned and a chown would push it
    # to an unusable subordinate uid. Detect rootless and skip the chown then.
    chown_output=1
    [ "$("$runtime" info --format '{{.Host.Security.Rootless}}' 2>/dev/null)" = "true" ] && chown_output=0
    echo "build-appimage: building inside $BASE_IMAGE via $runtime (rootless-skip-chown=$([ "$chown_output" = 0 ] && echo yes || echo no)) ..."
    # label=disable lets the container read the bind-mounted repo without a
    # recursive SELinux relabel of the host files (needed for rootless podman on
    # SELinux-labelled hosts; a harmless no-op on the CI runner).
    exec "$runtime" run --rm \
        --security-opt label=disable \
        -e _ALBUM_BUILDER_IN_CONTAINER=1 \
        -e CHOWN_OUTPUT="$chown_output" \
        -e HOST_UID="$(id -u)" \
        -e HOST_GID="$(id -g)" \
        -e PYTHON_APPIMAGE_TAG="$PYTHON_APPIMAGE_TAG" \
        -e PYTHON_APPIMAGE_ASSET="$PYTHON_APPIMAGE_ASSET" \
        -e APPIMAGETOOL_VERSION="$APPIMAGETOOL_VERSION" \
        -v "$REPO_ROOT:/src:ro" \
        -v "$REPO_ROOT/dist:/out:rw" \
        "$BASE_IMAGE" \
        bash /src/packaging/build-appimage.sh
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
# The interpreter is bin/python3.<minor> (e.g. python3.13), not a bare python3.
PYBIN=""
for _p in "$APPDIR"/opt/python*/bin/python3.*; do
    case "$_p" in *-config) continue ;; esac
    [ -x "$_p" ] && { PYBIN="$_p"; break; }
done
[ -n "$PYBIN" ] && [ -x "$PYBIN" ] || { echo "stage 2: no interpreter in the extracted AppDir" >&2; exit 1; }

# --- Stage 3: install deps as wheels, then drop the pure-Python album_builder
# package into site-packages. We do NOT `pip install "$SRC"`: /src is read-only
# and a legacy setuptools build (no [build-system]) writes egg-info into it; the
# package is pure Python with no entry points, so a copy IS a complete install.
# Copying only the package - not the checkout - means no pyproject.toml lands
# beside it (INV-23-4). ---------------------------------------------------------
echo "stage 3: pip install deps + copy package"
"$PYBIN" -m pip install --no-warn-script-location -q --upgrade pip
"$PYBIN" -m pip install --no-warn-script-location -q -r "$SRC/requirements.txt"
SITE="$("$PYBIN" -c 'import site; print(site.getsitepackages()[0])')"
cp -a "$SRC/src/album_builder" "$SITE/"

# --- Stage 4: bundle WeasyPrint's native library closure + font (INV-23-2). -----
echo "stage 4: bundling native libraries"
mkdir -p "$APPDIR/usr/lib"
# The five libraries WeasyPrint requires, plus libharfbuzz-subset.so.0 which it
# loads with allow_fail=True (font subsetting; PDFs still render without it) and
# which ubuntu:22.04's harfbuzz 2.7.4 does not ship - so it is bundled if present,
# skipped if not (INV-23-2).
weasy_libs_required="libgobject-2.0.so.0 libpango-1.0.so.0 libpangoft2-1.0.so.0 \
libharfbuzz.so.0 libfontconfig.so.1"
weasy_libs_optional="libharfbuzz-subset.so.0"
# Copy each named soname plus its ldd closure, minus the driver/core libraries
# that must come from the host (libGL is driver-coupled; libc/ld are the base).
copy_with_closure() {
    local soname="$1" optional="${2:-}" src
    src="$(ldconfig -p | awk -v n="$soname" '$1==n {print $NF; exit}')"
    if [ -z "$src" ]; then
        [ -n "$optional" ] && { echo "stage 4: $soname absent (optional) - skipping" >&2; return 0; }
        echo "stage 4: $soname not found after apt-get" >&2; exit 1
    fi
    cp -uL "$src" "$APPDIR/usr/lib/"
    ldd "$src" | awk '/=> \//{print $3}' | while read -r dep; do
        case "$(basename "$dep")" in
            libc.so.*|libm.so.*|libdl.so.*|libpthread.so.*|librt.so.*|\
            ld-linux*.so.*|libGL.so.*|libEGL.so.*|libGLdispatch.so.*) continue ;;
        esac
        cp -uL "$dep" "$APPDIR/usr/lib/"
    done
}
for lib in $weasy_libs_required; do copy_with_closure "$lib"; done
for lib in $weasy_libs_optional; do copy_with_closure "$lib" optional; done
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
# in double quotes). The binary is bin/python3.<minor> (e.g. python3.13).
PYTHON=
for _py in "$APPDIR"/opt/python*/bin/python3.*; do
    case "$_py" in *-config) continue ;; esac
    [ -x "$_py" ] && { PYTHON="$_py"; break; }
done
[ -n "$PYTHON" ] && [ -x "$PYTHON" ] || { echo "AppRun: bundled interpreter missing under $APPDIR/opt" >&2; exit 1; }
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

# Hand the artifact back to the invoking user when the container ran as real root
# (rootful, e.g. Docker); under rootless podman it is already user-owned, so a
# chown would break it (Spec 23 Section 6).
[ "${CHOWN_OUTPUT:-1}" = "1" ] && chown "${HOST_UID:-0}:${HOST_GID:-0}" "$OUT"
echo "done: $OUT"
