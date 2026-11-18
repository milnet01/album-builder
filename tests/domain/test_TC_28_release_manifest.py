"""Spec 28 - the release manifest: version rule, SHA256SUMS and its signature."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from album_builder.domain import release_manifest as rm

SUMS = (
    b"aa" * 32 + b"  AlbumBuilder-1.2.0-windows-x64.zip\n"
    + b"bb" * 32 + b"  AlbumBuilder-1.2.0-x86_64.AppImage\n"
)


def _key() -> tuple[bytes, str, dict[str, str]]:
    """A fresh test key: (raw private bytes, key id, trusted map holding it)."""
    priv = Ed25519PrivateKey.generate()
    raw = rm.private_raw(priv)
    pub = rm.public_raw_from_private(raw)
    kid = rm.key_id(pub)
    return raw, kid, {kid: base64.b64encode(pub).decode()}


# Spec: TC-28-04
@pytest.mark.parametrize(("tag", "running", "expected"), [
    ("v1.1.1", "1.1.0", (1, 1, 1)),
    ("v1.10.0", "1.9.0", (1, 10, 0)),
    ("v1.1.0", "1.1.0", None),
    ("v1.0.9", "1.1.0", None),
    ("v1.2.0-rc.1", "1.1.0", None),
    ("1.2.0", "1.1.0", None),
    ("v1.2", "1.1.0", None),
])
def test_version_rule(tag, running, expected):
    assert rm.offered_version(tag, running, skipped=None) == expected


# Spec: TC-28-04
def test_version_rule_skipped_daily_only():
    # The daily check passes over the skipped version; the manual one does not.
    assert rm.offered_version("v1.2.0", "1.1.0", skipped="1.2.0") is None
    assert rm.offered_version("v1.2.0", "1.1.0", skipped=None) == (1, 2, 0)
    # A newer release than the skipped one is offered again.
    assert rm.offered_version("v1.2.1", "1.1.0", skipped="1.2.0") == (1, 2, 1)


# Spec: TC-28-05
def test_signature():
    raw, kid, trusted = _key()
    sig = rm.signature_lines(SUMS, [raw])
    assert rm.signature_accepted(SUMS, sig, trusted)

    # A trusted line beside a line under an unknown key id is accepted.
    other_raw, _other_kid, _ = _key()
    two = rm.signature_lines(SUMS, [other_raw, raw])
    assert rm.signature_accepted(SUMS, two, trusted)

    # One byte of SHA256SUMS changed.
    assert not rm.signature_accepted(SUMS.replace(b"aa", b"ab", 1), sig, trusted)
    # One signature byte changed.
    tag, k, b64 = sig.decode().split()
    bad = bytearray(base64.b64decode(b64))
    bad[0] ^= 1
    flipped = f"{tag} {k} {base64.b64encode(bytes(bad)).decode()}\n".encode()
    assert not rm.signature_accepted(SUMS, flipped, trusted)
    # Only unknown key ids.
    assert not rm.signature_accepted(SUMS, rm.signature_lines(SUMS, [other_raw]), trusted)
    # The right signature under a wrong key id.
    wrong_id = sig.replace(kid.encode(), b"0" * 16)
    assert not rm.signature_accepted(SUMS, wrong_id, trusted)
    # A malformed line beside a valid one.
    assert not rm.signature_accepted(SUMS, sig + b"album-builder-signature-v1 junk\n", trusted)
    # Two trusted lines, one of which fails.
    raw2, _kid2, trusted2 = _key()
    both_trusted = {**trusted, **trusted2}
    good_two = rm.signature_lines(SUMS, [raw, raw2])
    assert rm.signature_accepted(SUMS, good_two, both_trusted)
    line1, line2 = good_two.decode().splitlines()
    t2, k2, b2 = line2.split()
    broken = bytearray(base64.b64decode(b2))
    broken[5] ^= 1
    one_fails = f"{line1}\n{t2} {k2} {base64.b64encode(bytes(broken)).decode()}\n".encode()
    assert not rm.signature_accepted(SUMS, one_fails, both_trusted)
    # A missing .sig.
    assert not rm.signature_accepted(SUMS, b"", trusted)
    # No trusted keys at all (before the project key exists): nothing passes.
    assert not rm.signature_accepted(SUMS, sig, {})


# Spec: TC-28-05
def test_parse_sums():
    sums = rm.parse_sums(SUMS)
    assert sums["AlbumBuilder-1.2.0-x86_64.AppImage"] == "bb" * 32
    for bad in (
        SUMS + SUMS,  # a repeated name
        b"xyz  name\n",  # not 64 hex
        b"AA" * 32 + b"  name\n",  # upper-case hex
        b"aa" * 32 + b" name\n",  # one space
        b"aa" * 32 + b"  name\r\n",  # CRLF
        b"aa" * 32 + b"  name",  # no final LF
        b"\xff" * 2 + b"\n",  # not ASCII
    ):
        with pytest.raises(rm.ManifestError):
            rm.parse_sums(bad)


# Spec: TC-28-06
def test_asset_names():
    assert rm.asset_name((1, 2, 0), "appimage") == "AlbumBuilder-1.2.0-x86_64.AppImage"
    assert rm.asset_name((1, 2, 0), "windows") == "AlbumBuilder-1.2.0-windows-x64-setup.exe"
