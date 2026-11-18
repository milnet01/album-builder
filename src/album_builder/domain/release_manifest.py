"""Release manifest - Spec 28 §4.3 and §4.4. Pure Python, no Qt.

Which release is on offer (the version rule), the `SHA256SUMS` and
`SHA256SUMS.sig` file formats, the Ed25519 signature check, and the asset
name each install kind downloads. `packaging/release-signing.py` imports
this module too, so the release workflow and the app share one key list.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

Version = tuple[int, int, int]

TRUSTED_KEYS: dict[str, str] = {
    # Project release key, generated 2026-11-18 (private half: the
    # RELEASE_SIGNING_KEY secret, backed up by the owner).
    "43f74035ce2eab1a": "dU6MouUJe5qjmH65uKRXZ1+o+n/ki6ZVgISamGU7/II=",
}
"""Key id -> standard base64 of a 32-byte raw Ed25519 public key (§4.3).

A release signed by none of these is never offered (§6). A key change adds
the successor here (§6)."""

SIGNATURE_TAG = "album-builder-signature-v1"

_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_SUMS_LINE = re.compile(r"^([0-9a-f]{64})  (\S(?:.*\S)?)$")
_KEY_ID = re.compile(r"^[0-9a-f]{16}$")

_ASSET_SUFFIX = {
    "appimage": "x86_64.AppImage",
    "windows": "windows-x64-setup.exe",
}


class ManifestError(ValueError):
    """A `SHA256SUMS` file that does not parse."""


def _triple(match: re.Match[str] | None) -> Version | None:
    if match is None:
        return None
    major, minor, patch = (int(g) for g in match.groups())
    return major, minor, patch


def parse_version(text: str) -> Version | None:
    """`X.Y.Z` as an integer triple, or None when it is not exactly that."""
    return _triple(_VERSION.match(text))


def format_version(version: Version) -> str:
    return ".".join(str(n) for n in version)


def offered_version(tag: str, running: str, *, skipped: str | None) -> Version | None:
    """The release's version when it is on offer (§4.4 items 1 and 4), else None.

    The tag must be exactly `vX.Y.Z`, so a pre-release suffix is refused, and
    greater than `running` compared as integers (`1.10.0` > `1.9.0`). The
    daily check passes `skipped`; the manual check passes None.
    """
    offered = _triple(_TAG.match(tag))
    current = parse_version(running)
    if offered is None or current is None or offered <= current:
        return None
    if skipped is not None and parse_version(skipped) == offered:
        return None
    return offered


def asset_name(version: Version, kind: str) -> str:
    """The file a `kind` ("appimage" or "windows") copy downloads (§4.4 item 3)."""
    return f"AlbumBuilder-{format_version(version)}-{_ASSET_SUFFIX[kind]}"


def parse_sums(data: bytes) -> dict[str, str]:
    """Parse `SHA256SUMS` (GNU text format, ASCII, LF) into {name: hex digest}.

    Refuses a malformed line, a missing final newline, or a repeated name.
    Names this app does not use are kept; the caller ignores them.
    """
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ManifestError("SHA256SUMS is not ASCII") from exc
    if not text.endswith("\n"):
        raise ManifestError("SHA256SUMS does not end with a newline")
    sums: dict[str, str] = {}
    for line in text[:-1].split("\n"):
        match = _SUMS_LINE.match(line)
        if match is None:
            raise ManifestError(f"malformed SHA256SUMS line: {line!r}")
        digest, name = match.groups()
        if name in sums:
            raise ManifestError(f"SHA256SUMS lists {name} twice")
        sums[name] = digest
    return sums


def key_id(public_raw: bytes) -> str:
    """First 16 hex characters of SHA-256 over the raw public key (§4.3)."""
    return hashlib.sha256(public_raw).hexdigest()[:16]


def private_raw(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())


def public_raw_from_private(raw: bytes) -> bytes:
    key = Ed25519PrivateKey.from_private_bytes(raw)
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def signature_lines(sums: bytes, private_keys: Iterable[bytes]) -> bytes:
    """`SHA256SUMS.sig` content: one signature line per raw private key."""
    out = []
    for raw in private_keys:
        signature = Ed25519PrivateKey.from_private_bytes(raw).sign(sums)
        kid = key_id(public_raw_from_private(raw))
        out.append(f"{SIGNATURE_TAG} {kid} {base64.b64encode(signature).decode()}\n")
    return "".join(out).encode("ascii")


def _parse_signature_line(line: str) -> tuple[str, bytes] | None:
    parts = line.split(" ")
    if len(parts) != 3 or parts[0] != SIGNATURE_TAG or not _KEY_ID.match(parts[1]):
        return None
    try:
        signature = base64.b64decode(parts[2], validate=True)
    except binascii.Error:
        return None
    if len(signature) != 64:
        return None
    return parts[1], signature


def signature_accepted(
    sums: bytes, sig: bytes, trusted: Mapping[str, str] | None = None,
) -> bool:
    """§4.3's rule, checked over the exact downloaded bytes of `SHA256SUMS`.

    Accepted when every line of `sig` parses, at least one names a trusted
    key id, and every line naming a trusted key id verifies. Lines under an
    unknown key id are skipped. `trusted` defaults to TRUSTED_KEYS.
    """
    keys = TRUSTED_KEYS if trusted is None else trusted
    try:
        text = sig.decode("ascii")
    except UnicodeDecodeError:
        return False
    if not text.endswith("\n"):
        return False
    lines = [_parse_signature_line(line) for line in text[:-1].split("\n")]
    if any(parsed is None for parsed in lines):
        return False
    checked = 0
    for kid, signature in lines:  # type: ignore[misc]  # None ruled out above
        if kid not in keys:
            continue
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(keys[kid]))
        try:
            public.verify(signature, sums)
        except InvalidSignature:
            return False
        checked += 1
    return checked > 0
