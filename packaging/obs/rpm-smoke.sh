#!/usr/bin/env bash
# Build the openSUSE package from the working tree and check it installs and
# runs on a clean Tumbleweed (Spec 27 INV-6..9). Needs podman or docker.
#
#   packaging/obs/rpm-smoke.sh
#
# Two containers, on purpose: one builds the RPM (and runs its %check), a
# fresh one installs it. Installing where the build ran would hide a missing
# Requires:, because the build already installed the runtime set.
# The two --stage modes run inside the containers; do not call them by hand.
set -euo pipefail

IMAGE=${RPM_SMOKE_IMAGE:-registry.opensuse.org/opensuse/tumbleweed:latest}

die() { echo "rpm-smoke: $*" >&2; exit 1; }

stage_build() {   # in container: /src (read-only checkout), /out (results)
    zypper -n -q refresh
    zypper -n -q install rpm-build git-core
    local spec=/src/packaging/obs/album-builder.spec version top
    version=$(rpmspec -q --qf '%{version}\n' "$spec" | head -n1)
    # BuildRequires come from the spec itself, as OBS reads them.
    mapfile -t deps < <(rpmspec -q --buildrequires "$spec" | tr -d ' ')
    zypper -n -q install "${deps[@]}"
    top=$(mktemp -d)
    mkdir -p "$top/SOURCES" "$top/tree/album-builder-$version"
    # The working tree's files as git sees them: tracked ones with uncommitted
    # edits, plus new files that are not ignored.
    git -c safe.directory='*' -C /src ls-files -z --cached --others --exclude-standard \
        | (cd /src && xargs -0 cp --parents -t "$top/tree/album-builder-$version")
    tar -C "$top/tree" -czf "$top/SOURCES/album-builder-$version.tar.gz" "album-builder-$version"
    rpmbuild -bb --define "_topdir $top" "$spec"
    cp "$top"/RPMS/noarch/album-builder-*.rpm /out/
    echo "$version" > /out/version
}

stage_install() {   # in a fresh container: /out holds the RPM
    zypper -n -q refresh
    local rpm version
    rpm=$(ls /out/album-builder-*.rpm)
    version=$(cat /out/version)
    zypper -n -q install --allow-unsigned-rpm "$rpm"
    useradd -m smoke
    as() { su smoke -s /bin/bash -c "export QT_QPA_PLATFORM=offscreen; $1"; }

    # INV-6: it runs.
    [[ $(as 'album-builder --version') == "$version" ]] || die "INV-6: --version is not $version"
    as 'album-builder --selftest' || die "INV-6: --selftest failed"
    echo "INV-6 ok: album-builder $version installs, --version and --selftest pass"

    # INV-7: Qt's media backend loads, so audio can play.
    as "python3 -c '
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtMultimedia import QMediaFormat
app = QGuiApplication([])
formats = QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode)
assert formats, \"no decodable formats: the media backend did not load\"
print(\"INV-7 ok:\", len(formats), \"decodable formats\")
'" || die "INV-7: media backend"

    # INV-8: an installed copy never uses a system directory as its project root.
    as "python3 -c '
import album_builder.app as a
assert not a._running_from_source_tree(), \"installed copy thinks it is a source tree\"
'" || die "INV-8: _running_from_source_tree() is true"
    ! rpm -ql album-builder | grep -q 'pyproject\.toml$' || die "INV-8: pyproject.toml installed"
    echo "INV-8 ok: not a source tree, no pyproject.toml installed"

    # INV-9: the files a user needs are installed.
    local files sitelib
    files=$(rpm -ql album-builder)
    # Where python3 imports the package from (sysconfig's purelib names
    # /usr/local on openSUSE, which is not where an RPM installs).
    sitelib=$(as 'python3 -c "import album_builder, pathlib; print(pathlib.Path(album_builder.__file__).parent.parent)"')
    for f in /usr/share/applications/album-builder.desktop \
             /usr/share/icons/hicolor/scalable/apps/album-builder.svg \
             /usr/share/metainfo/io.github.milnet01.AlbumBuilder.metainfo.xml \
             "$sitelib/album_builder/services/templates/report.html.j2" \
             "$sitelib"/album_builder/translations/{af,ar,de,es,fr,he,pt}.json; do
        grep -qxF "$f" <<<"$files" || die "INV-9: $f not installed"
    done
    as 'python3 -c "import album_builder"' || die "INV-9: album_builder not importable"
    echo "INV-9 ok: desktop file, icon, metainfo, report template, 7 catalogs"
}

case ${1:-} in
    --stage-build) stage_build; exit ;;
    --stage-install) stage_install; exit ;;
    "") ;;
    *) die "usage: rpm-smoke.sh" ;;
esac

engine=$(command -v podman || command -v docker) || die "needs podman or docker"
repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
out=$(mktemp -d "${RPM_SMOKE_SCRATCH:-$repo/.rpm-smoke}.XXXXXX")
trap 'rm -rf "$out"' EXIT
self=/src/packaging/obs/rpm-smoke.sh
# label=disable: SELinux hosts (Tumbleweed) otherwise deny the container the
# read-only checkout; relabelling with :Z would rewrite the repo's labels.

"$engine" run --rm --security-opt label=disable -v "$repo:/src:ro" -v "$out:/out" "$IMAGE" bash "$self" --stage-build
"$engine" run --rm --security-opt label=disable -v "$repo:/src:ro" -v "$out:/out" "$IMAGE" bash "$self" --stage-install
echo "rpm-smoke: all checks passed"
