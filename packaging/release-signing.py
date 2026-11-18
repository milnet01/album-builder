#!/usr/bin/env python3
"""Release signing - Spec 28 §4.7.

    release-signing.py generate --out PATH   new key file (mode 0600, outside
                                             the work tree); prints the
                                             TRUSTED_KEYS entry to add
    release-signing.py sign FILE             writes FILE.sig with every key in
                                             $RELEASE_SIGNING_KEY
    release-signing.py verify FILE           checks FILE.sig against the app's
                                             own TRUSTED_KEYS

$RELEASE_SIGNING_KEY and a generated key file hold one line per key: the
standard base64 of a 32-byte raw Ed25519 private key. `verify` imports
TRUSTED_KEYS from the app, so the release workflow fails when the secret does
not match the key the app ships with.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

from album_builder.domain import release_manifest as rm  # noqa: E402


def _work_tree() -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out).resolve()


def generate(out: Path) -> int:
    target = out.expanduser().resolve()
    tree = _work_tree()
    if tree is None or target.is_relative_to(tree):
        # A key inside the repository is one `git add` away from being published.
        print(f"refusing to write a private key inside the work tree ({tree})",
              file=sys.stderr)
        return 2
    raw = rm.private_raw(Ed25519PrivateKey.generate())
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"{target} already exists; not overwriting a key", file=sys.stderr)
        return 2
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(base64.b64encode(raw).decode() + "\n")
    public = rm.public_raw_from_private(raw)
    print(f"wrote {target}")
    print("Add to TRUSTED_KEYS in src/album_builder/domain/release_manifest.py:")
    print(f'    "{rm.key_id(public)}": "{base64.b64encode(public).decode()}",')
    return 0


def _keys_from_env() -> list[bytes]:
    keys = []
    for line in os.environ.get("RELEASE_SIGNING_KEY", "").splitlines():
        if not line.strip():
            continue
        try:
            raw = base64.b64decode(line.strip(), validate=True)
        except binascii.Error:
            raw = b""
        if len(raw) != 32:
            raise SystemExit("RELEASE_SIGNING_KEY holds a line that is not a base64 "
                             "32-byte Ed25519 key")
        keys.append(raw)
    if not keys:
        raise SystemExit("RELEASE_SIGNING_KEY is empty")
    return keys


def sign(path: Path) -> int:
    sums = path.read_bytes()
    rm.parse_sums(sums)  # refuse to sign a file the app would not read
    sig = rm.signature_lines(sums, _keys_from_env())
    path.with_name(path.name + ".sig").write_bytes(sig)
    return 0


def verify(path: Path) -> int:
    sums = path.read_bytes()
    sig = path.with_name(path.name + ".sig").read_bytes()
    try:
        rm.parse_sums(sums)
    except rm.ManifestError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1
    if not rm.signature_accepted(sums, sig):
        print(f"{path}.sig is not accepted by the app's TRUSTED_KEYS", file=sys.stderr)
        return 1
    print(f"{path}: signature accepted")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate")
    gen.add_argument("--out", type=Path, required=True)
    commands.add_parser("sign").add_argument("file", type=Path)
    commands.add_parser("verify").add_argument("file", type=Path)
    args = parser.parse_args(argv)
    if args.command == "generate":
        return generate(args.out)
    if args.command == "sign":
        return sign(args.file)
    return verify(args.file)


if __name__ == "__main__":
    sys.exit(main())
