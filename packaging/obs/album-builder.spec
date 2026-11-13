# RPM recipe for Album Builder on openSUSE Tumbleweed (Spec 27).
#
# A noarch package on the distribution's own Python libraries. Built by OBS
# in home:milnet:album-builder from a tarball obs-submit.sh makes with
# `git archive`; tested by rpm-smoke.sh in a clean Tumbleweed container.
#
# Macros in comments are written %%like_this: rpm expands a bare macro
# inside a comment (perch's spec records the failure).

# Build for the distribution's default python3 only. openSUSE builds once per
# configured flavour otherwise, and perch measured Tumbleweed picking a
# flavour whose interpreter the build root did not have.
%define pythons python3
# %%{_metainfodir} is undefined on openSUSE.
%define _metainfodir %{_datadir}/metainfo

Name:           album-builder
Version:        1.1.0
Release:        0
Summary:        Curate an album from a folder of songs
License:        MIT
URL:            https://github.com/milnet01/album-builder
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel >= 3.11
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools >= 77
BuildRequires:  python3-wheel
BuildRequires:  appstream-glib
BuildRequires:  desktop-file-utils
# Also a BuildRequires: openSUSE's file-list check runs on the build root and
# fails on an unowned /usr/share/icons/hicolor (perch).
BuildRequires:  hicolor-icon-theme
# The runtime set again, so %%check can run --selftest in the build root.
# Keep these equal to requirements.txt (Spec 27 INV-3, TC-27-03).
BuildRequires:  python3-PyQt6 >= 6.6
BuildRequires:  python3-mutagen >= 1.47
BuildRequires:  python3-platformdirs >= 4.11
BuildRequires:  python3-Jinja2 >= 3.1
BuildRequires:  python3-weasyprint >= 68
BuildRequires:  python3-Pillow >= 11
# A font for the PDF report. With no font installed, WeasyPrint 70 segfaults
# drawing text (measured 2026-11-05 in a bare Tumbleweed container; a build
# root is that bare). DejaVu Sans is in the report template's font list.
BuildRequires:  dejavu-fonts

Requires:       hicolor-icon-theme
Requires:       dejavu-fonts
Requires:       python3-PyQt6 >= 6.6
# Qt's FFmpeg audio plugin is in this package; without it nothing plays.
Requires:       qt6-multimedia
Requires:       python3-mutagen >= 1.47
Requires:       python3-platformdirs >= 4.11
Requires:       python3-Jinja2 >= 3.1
Requires:       python3-weasyprint >= 68
Requires:       python3-Pillow >= 11

%description
Album Builder helps you put an album together from a folder of songs.
Pick the tracks you want, drag them into order, listen through with the
lyrics scrolling along, and when you are happy, approve it. Approving
makes a ready-to-share album folder: a playlist, the tracks numbered in
order, and a printable report.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
sed 's|@@LAUNCHER@@|album-builder|' packaging/album-builder.desktop.in > album-builder.desktop
install -Dm644 album-builder.desktop \
    %{buildroot}%{_datadir}/applications/album-builder.desktop
install -Dm644 assets/album-builder.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/album-builder.svg
install -Dm644 packaging/linux/io.github.milnet01.AlbumBuilder.metainfo.xml \
    %{buildroot}%{_metainfodir}/io.github.milnet01.AlbumBuilder.metainfo.xml

%check
appstream-util validate-relax --nonet \
    %{buildroot}%{_metainfodir}/io.github.milnet01.AlbumBuilder.metainfo.xml
desktop-file-validate %{buildroot}%{_datadir}/applications/album-builder.desktop
QT_QPA_PLATFORM=offscreen PYTHONPATH=%{buildroot}%{python3_sitelib} \
    python3 -m album_builder --selftest

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/album-builder
%{python3_sitelib}/album_builder/
%{python3_sitelib}/album_builder-*.dist-info/
%{_datadir}/applications/album-builder.desktop
%{_datadir}/icons/hicolor/scalable/apps/album-builder.svg
%{_metainfodir}/io.github.milnet01.AlbumBuilder.metainfo.xml

%changelog
