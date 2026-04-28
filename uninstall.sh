#!/usr/bin/env bash
# Album Builder uninstaller. Removes installed files; preserves user data.
set -euo pipefail

PURGE=0
if [[ "${1:-}" == "--purge" ]]; then
    PURGE=1
fi

INSTALL_PREFIX="${HOME}/.local"
APP_DIR="${INSTALL_PREFIX}/share/album-builder"
DESKTOP_FILE="${INSTALL_PREFIX}/share/applications/album-builder.desktop"
ICON_PNG="${INSTALL_PREFIX}/share/icons/hicolor/256x256/apps/album-builder.png"
ICON_SVG="${INSTALL_PREFIX}/share/icons/hicolor/scalable/apps/album-builder.svg"
BIN="${INSTALL_PREFIX}/bin/album-builder"

# Match python, python3, python3.11, python3.13 — but not "pythonista" or
# random binaries that happen to start with the letters "python".
if pgrep -f "python[0-9.]* -m album_builder" >/dev/null; then
    echo "Quit Album Builder first." >&2
    exit 1
fi

rm -rf "$APP_DIR"
rm -f "$DESKTOP_FILE" "$ICON_PNG" "$ICON_SVG" "$BIN"

if [[ $PURGE -eq 1 ]]; then
    rm -rf "${HOME}/.config/album-builder" "${HOME}/.cache/album-builder"
    echo "Removed user settings and cache (--purge)."
fi

# stderr surfaces deliberately — see install.sh for the reasoning.
update-desktop-database "$(dirname "$DESKTOP_FILE")" || true
gtk-update-icon-cache -t "$INSTALL_PREFIX/share/icons/hicolor" || true
if command -v kbuildsycoca6 >/dev/null; then kbuildsycoca6 || true; fi

echo "Uninstalled."
# Plain `if` rather than `[[ … ]] && echo`: under `set -e`, a compound
# `false-test && echo` makes the whole script exit if it's the final command
# in some shell variants. `if` is unambiguously safe.
if [[ $PURGE -eq 0 ]]; then
    echo "User settings preserved at ~/.config/album-builder (use --purge to remove)."
fi
