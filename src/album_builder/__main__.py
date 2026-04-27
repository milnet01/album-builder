"""python -m album_builder entry point."""

from __future__ import annotations

import sys

from album_builder.app import run

if __name__ == "__main__":
    sys.exit(run())
