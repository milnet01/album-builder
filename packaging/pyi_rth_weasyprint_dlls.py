# PyInstaller runtime hook - Album Builder Windows bundle (Spec 24 Section 4.3a).
#
# Runs before any album_builder import. WeasyPrint's ffi.dlopen loads the GTK /
# Pango / HarfBuzz / fontconfig DLLs by soname with LOAD_LIBRARY_SEARCH_DEFAULT_DIRS
# (weasyprint/text/ffi.py), which searches directories registered via
# os.add_dll_directory. WeasyPrint's OWN add_dll_directory / WEASYPRINT_DLL_DIRECTORIES
# block is guarded by `not hasattr(sys, 'frozen')`, so it is inert inside a frozen
# bundle - this hook must add the bundle directory itself (Spec 24 INV-24-2).
import os
import sys

if hasattr(sys, "frozen"):
    # One-folder build: the bundled DLLs and data live under sys._MEIPASS
    # (PyInstaller's runtime resource root).
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    if hasattr(os, "add_dll_directory") and os.path.isdir(base):
        try:
            os.add_dll_directory(base)
        except OSError:
            pass
    # Point fontconfig at the bundled config + font (Spec 24 Section 4.2), so
    # WeasyPrint has a discoverable font without relying on a system install.
    fonts_conf = os.path.join(base, "fonts", "fonts.conf")
    if os.path.isfile(fonts_conf):
        os.environ.setdefault("FONTCONFIG_FILE", fonts_conf)
        os.environ.setdefault("FONTCONFIG_PATH", os.path.join(base, "fonts"))
