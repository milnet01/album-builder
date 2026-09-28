"""No unwrapped English on built widgets - Spec 25 TC-25-07."""

from __future__ import annotations

import re

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QAbstractButton,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTabBar,
    QWidget,
)

from album_builder import i18n
from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow
from album_builder.ui.theme import Glyphs
from tests.i18n.keys import collect

MARK = "⟦"
# Text with no Latin letters needs no translation: glyphs, digits, "0:00", "3 / 12".
_NO_LETTERS = re.compile(r"^[^A-Za-z]*$")
# Widgets Qt builds itself (a QTabBar's scroll arrows); qtbase_<code> translates them.
_QT_OWN = {"ScrollLeftButton", "ScrollRightButton"}


def _texts(win: MainWindow) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for w in win.findChildren(QWidget):
        if w.objectName() in _QT_OWN:
            continue
        kind = type(w).__name__
        if isinstance(w, (QLabel, QAbstractButton)):
            out.append((kind, w.text()))
        if isinstance(w, QLineEdit):
            out.append((kind + ".placeholder", w.placeholderText()))
        if isinstance(w, QTabBar):
            out += [(kind, w.tabText(i)) for i in range(w.count())]
        if isinstance(w, QHeaderView):
            model = w.model()
            if model is not None:
                out += [
                    (kind, str(model.headerData(i, w.orientation()) or ""))
                    for i in range(w.count())
                ]
        out.append((kind + ".toolTip", w.toolTip()))
        out.append((kind + ".accessibleName", w.accessibleName()))
        out.append((kind + ".accessibleDescription", w.accessibleDescription()))
    for a in win.findChildren(QAction):
        out.append(("QAction", a.text().replace("&", "")))
        out.append(("QAction.toolTip", a.toolTip()))
    return out


# Spec: TC-25-07
def test_every_built_widget_text_is_translated(qtbot, tracks_dir, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    keys, _ = collect()
    i18n.set_catalog({k: f"{MARK}{k}⟧" for k in keys})
    try:
        watcher = LibraryWatcher(tracks_dir)
        win = MainWindow(AlbumStore(tmp_path / "Albums"), watcher, AppState(), tmp_path)
        qtbot.addWidget(win)
        allowed = {"Album Builder"}  # the product name
        for t in watcher.library().tracks:
            allowed |= {t.title, t.artist, t.album, t.album_artist, t.composer, t.comment}
            allowed.add(t.path.name)
        allowed |= {i18n.language_name(c) for c in i18n.SUPPORTED}
        allowed |= {v for k, v in vars(Glyphs).items() if not k.startswith("_")}
        bad = sorted({
            (kind, text) for kind, text in _texts(win)
            if text and MARK not in text and text not in allowed
            and not _NO_LETTERS.match(text)
        })
        assert not bad, "untranslated widget text:\n" + "\n".join(f"{k}: {t!r}" for k, t in bad)
    finally:
        i18n.set_language("en")
