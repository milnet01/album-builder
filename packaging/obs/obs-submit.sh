#!/usr/bin/env bash
# Submit release X.Y.Z to the OBS package home:milnet:album-builder/album-builder
# (Spec 27 §4.4). Run after the GitHub release: packaging/obs/obs-submit.sh X.Y.Z
#
# Everything comes from the local tag vX.Y.Z: the version check, the RPM
# recipe and the source tarball (`git archive`). Nothing is downloaded.
# osc reads its credentials from the keyring named in ~/.config/osc/oscrc;
# this script never handles them. OBS builds the upload and publishes it once
# the build is green.
set -euo pipefail

PROJECT=home:milnet:album-builder
PACKAGE=album-builder

die() { echo "obs-submit: $*" >&2; exit 1; }

version=${1:-}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "usage: obs-submit.sh X.Y.Z"
repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
tag="v$version"

git -C "$repo" rev-parse -q --verify "refs/tags/$tag" >/dev/null \
    || die "no local tag $tag"
tagged_version=$(git -C "$repo" show "$tag:pyproject.toml" \
    | sed -n 's/^version = "\(.*\)"$/\1/p' | head -n1)
[[ $tagged_version == "$version" ]] \
    || die "pyproject.toml at $tag says '$tagged_version', not $version"
spec=$(git -C "$repo" show "$tag:packaging/obs/album-builder.spec" 2>/dev/null) \
    || die "$tag has no packaging/obs/album-builder.spec"
command -v osc >/dev/null || die "osc is not installed"

scratch=$(mktemp -d "${OBS_SCRATCH:-$HOME/.cache}/album-builder-obs.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
cd "$scratch"
osc checkout "$PROJECT" "$PACKAGE" >/dev/null
cd "$PROJECT/$PACKAGE"
rm -f -- *.tar.gz
git -C "$repo" archive --format=tar.gz --prefix="$PACKAGE-$version/" \
    -o "$PWD/$PACKAGE-$version.tar.gz" "$tag"
printf '%s\n' "$spec" | sed "s/^Version:.*/Version:        $version/" > "$PACKAGE.spec"
osc addremove >/dev/null
osc commit -m "Update to $version"
echo "obs-submit: $PACKAGE $version sent to $PROJECT; watch: osc results $PROJECT $PACKAGE"
