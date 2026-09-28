"""Check that relative links in tracked Markdown files point at files that exist.

Used by `./local-CI.sh --docs`, the gate for a documentation-only push.
External links (http:, mailto:, ...) and pure #anchors are not checked.
Usage: python tools/check_md_links.py [FILE.md ...]   (default: every tracked *.md)
"""

import re
import subprocess
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
FENCE = re.compile(r"^\s*(```|~~~)")


def md_files(args: list[str]) -> list[Path]:
    if args:
        return [Path(a) for a in args if a.endswith(".md") and Path(a).exists()]
    out = subprocess.run(["git", "ls-files", "*.md"], capture_output=True, text=True, check=True)
    return [Path(p) for p in out.stdout.split()]


def broken_links(path: Path) -> list[str]:
    bad = []
    in_fence = False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for target in LINK.findall(re.sub(r"`[^`]*`", "", line)):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            rel = target.split("#", 1)[0]
            if rel and not (path.parent / rel).exists():
                bad.append(f"{path}:{n}: {target}")
    return bad


def main() -> int:
    bad = [b for f in md_files(sys.argv[1:]) for b in broken_links(f)]
    for b in bad:
        print(f"broken link: {b}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
