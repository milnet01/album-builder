"""Startup language resolution - Spec 25 §Public API `app.py`, TC-25-08/11."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication, Qt

from album_builder import i18n
from album_builder.app import setup_language
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player
from album_builder.ui.transport_bar import TransportBar


@pytest.fixture
def restore(qapp):
    yield qapp
    for t in getattr(qapp, "_album_builder_translators", []):
        qapp.removeTranslator(t)
    qapp._album_builder_translators = []
    qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    i18n.set_language("en")


# Spec: TC-25-08
def test_rtl_language_mirrors_app_but_not_transport(restore, qtbot) -> None:
    assert setup_language(restore, "ar", system_code="en") == "ar"
    assert restore.layoutDirection() == Qt.LayoutDirection.RightToLeft
    p = Player()
    bar = TransportBar(p, PlaybackController(p))
    qtbot.addWidget(bar)
    assert bar.layoutDirection() == Qt.LayoutDirection.LeftToRight


# Spec: TC-25-08
def test_ltr_language_keeps_ltr(restore) -> None:
    assert setup_language(restore, "de", system_code="en") == "de"
    assert restore.layoutDirection() == Qt.LayoutDirection.LeftToRight


# Spec: TC-25-11
def test_qt_own_strings_follow_language(restore) -> None:
    setup_language(restore, "de", system_code="en")
    assert QCoreApplication.translate("QPlatformTheme", "&Yes") != "&Yes"


# Spec: TC-25-11
def test_afrikaans_has_no_qt_catalog_and_starts(restore) -> None:
    assert setup_language(restore, "af", system_code="en") == "af"
    assert QCoreApplication.translate("QPlatformTheme", "&Yes") == "&Yes"


# Spec: TC-25-05
def test_system_setting_uses_system_code(restore) -> None:
    assert setup_language(restore, "system", system_code="ja") == "en"
