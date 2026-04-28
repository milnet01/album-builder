#!/usr/bin/env bash
# Album Builder installer — per-user, no sudo.
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
    echo "Run as your user, not root. Album Builder is per-user." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_PREFIX="${HOME}/.local"
APP_DIR="${INSTALL_PREFIX}/share/album-builder"
VENV_DIR="${APP_DIR}/.venv"
DESKTOP_DIR="${INSTALL_PREFIX}/share/applications"
ICON_DIR_PNG="${INSTALL_PREFIX}/share/icons/hicolor/256x256/apps"
ICON_DIR_SVG="${INSTALL_PREFIX}/share/icons/hicolor/scalable/apps"
BIN_DIR="${INSTALL_PREFIX}/bin"

# 1. Python version check — verified through the SAME interpreter we'll use
# for the venv. The previous version asked $PY for the version string but
# evaluated the comparison via bare `python3`, which on dual-stack systems
# (python3 → 3.13, python3.11 → 3.11) could disagree with $PY.
PY=$(command -v python3.11 || command -v python3 || true)
if [[ -z "$PY" ]]; then
    echo "Python 3.11+ not found. On openSUSE: zypper install python311" >&2
    exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY_VER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    echo "Python 3.11 or newer required (found $PY_VER via $PY)." >&2
    exit 1
fi

# 2. Refuse to run while the app is open (single-instance lock)
if pgrep -f "python.* -m album_builder" >/dev/null; then
    echo "Quit Album Builder first; it is currently running." >&2
    exit 1
fi

mkdir -p "$APP_DIR" "$DESKTOP_DIR" "$ICON_DIR_PNG" "$ICON_DIR_SVG" "$BIN_DIR"

# 3. venv
if [[ ! -d "$VENV_DIR" ]] || ! diff -q "$REPO_DIR/requirements.txt" "$APP_DIR/.requirements.txt.cached" >/dev/null 2>&1; then
    echo "Setting up venv…"
    rm -rf "$VENV_DIR"
    "$PY" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
    "$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"
    cp "$REPO_DIR/requirements.txt" "$APP_DIR/.requirements.txt.cached"
fi

# 4. Source files
echo "Copying source…"
rsync -a --delete "$REPO_DIR/src/" "$APP_DIR/src/"

# 5. Icon
echo "Installing icon…"
install -m 0644 "$REPO_DIR/assets/album-builder.svg" "$ICON_DIR_SVG/album-builder.svg"
if command -v inkscape >/dev/null; then
    inkscape "$ICON_DIR_SVG/album-builder.svg" \
        --export-type=png --export-width=256 \
        --export-filename="$ICON_DIR_PNG/album-builder.png" >/dev/null 2>&1
elif command -v rsvg-convert >/dev/null; then
    rsvg-convert -w 256 -h 256 "$ICON_DIR_SVG/album-builder.svg" -o "$ICON_DIR_PNG/album-builder.png"
else
    "$VENV_DIR/bin/pip" install --quiet cairosvg
    "$VENV_DIR/bin/python" -c "
import cairosvg
cairosvg.svg2png(url='$ICON_DIR_SVG/album-builder.svg',
                 write_to='$ICON_DIR_PNG/album-builder.png',
                 output_width=256, output_height=256)
"
fi

# 6. Launcher script
cat > "$BIN_DIR/album-builder" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$APP_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$VENV_DIR/bin/python" -m album_builder "\$@"
EOF
chmod +x "$BIN_DIR/album-builder"

# 7. .desktop file
sed "s|@@LAUNCHER@@|$BIN_DIR/album-builder|g" \
    "$REPO_DIR/packaging/album-builder.desktop.in" \
    > "$DESKTOP_DIR/album-builder.desktop"
chmod 0644 "$DESKTOP_DIR/album-builder.desktop"

# 8. Refresh caches
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -t "$INSTALL_PREFIX/share/icons/hicolor" 2>/dev/null || true
if command -v kbuildsycoca6 >/dev/null; then kbuildsycoca6 2>/dev/null || true; fi

echo
echo "Installed."
echo "Launch from the K Menu (Multimedia → Album Builder) or run 'album-builder' from a terminal."

if ! echo "$PATH" | tr ':' '\n' | grep -q "^$BIN_DIR\$"; then
    echo
    echo "NOTE: $BIN_DIR is not on PATH. Add this to ~/.bashrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
