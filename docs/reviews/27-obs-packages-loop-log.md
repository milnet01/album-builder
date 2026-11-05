# Loop log — docs/specs/27-obs-packages.md

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|---|---|---|---|---|---|---|---|
| impl | 2026-11-05 | none (no reviewer dispatched; implementation row, not a review loop) | - | - | - | - | Built. Fold-backs: Requires/BuildRequires dejavu-fonts (WeasyPrint 70 segfaulted the %check self-test with no font installed); rpm-smoke.sh builds and installs in two containers on the host, so the local wrapper was dropped and a missing Requires cannot hide; --security-opt label=disable for SELinux hosts; obs-submit.sh takes the version check and the spec from the tag. Measured: qt6-multimedia is already pulled in by python3-PyQt6, so its Requires is a guard. Each TC-27 test seen failing before passing; rpm-smoke all checks passed on Tumbleweed. |
