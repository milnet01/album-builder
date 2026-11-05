#!/usr/bin/env bash
# Create or update the OBS project home:milnet:album-builder and its package
# (Spec 27 §4.4). Idempotent: re-running re-applies the meta, which is also how
# a build target is added or removed. Modelled on Ants Terminal's obs-setup.sh.
#
# Its own sub-project, as the owner's other apps have, so its distribution
# list cannot disturb theirs. Tumbleweed only for now: Leap 16.0's weasyprint
# and platformdirs are below requirements.txt's floors (Spec 27 §3).
#
# Needs osc, logged in once; credentials come from the keyring named in
# ~/.config/osc/oscrc and never pass through this script. The first run is the
# owner's to approve (Spec 27 §3).
#
# Keep the XML free of double hyphens: they are illegal in an XML comment and
# OBS rejects the whole meta (Ants Terminal's note).
set -euo pipefail

PROJECT=home:milnet:album-builder
PACKAGE=album-builder
OBS_USER=milnet

command -v osc >/dev/null || { echo "obs-setup: osc is not installed" >&2; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/prj.xml" <<EOF
<project name="$PROJECT">
  <title>Album Builder</title>
  <description>Curate an album from a folder of songs: pick, order, listen with synced lyrics, approve.</description>
  <person userid="$OBS_USER" role="maintainer"/>
  <repository name="openSUSE_Tumbleweed">
    <path project="openSUSE:Factory" repository="snapshot"/>
    <arch>x86_64</arch>
  </repository>
</project>
EOF
osc meta prj "$PROJECT" -F "$tmp/prj.xml"

cat > "$tmp/pkg.xml" <<EOF
<package name="$PACKAGE" project="$PROJECT">
  <title>Album Builder</title>
  <description>Built from a git archive of the upstream release tag by packaging/obs/obs-submit.sh.</description>
  <person userid="$OBS_USER" role="maintainer"/>
</package>
EOF
osc meta pkg "$PROJECT" "$PACKAGE" -F "$tmp/pkg.xml"

echo "obs-setup: $PROJECT/$PACKAGE ready. Next: packaging/obs/obs-submit.sh X.Y.Z"
