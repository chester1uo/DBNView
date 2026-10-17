"""Desktop entry point: `dbnview [file | ssh://host/path]` (also `python -m dbnview`)."""
import os
import sys
import time

from PySide6 import QtCore, QtWidgets

from .. import i18n, reference
from ..engine import is_remote
from .common import APP_NAME
from .main_window import MainWindow


def apply_lang(code):
    i18n.set_lang(code)
    reference.set_lang(i18n.get_lang())


class App(QtWidgets.QApplication):
    """Handles Finder/Explorer 'Open With' documents and language switching (which rebuilds the window)."""

    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationName(APP_NAME)
        self.setOrganizationName("dbnview")
        self.win = None
        self.pending = []
        self.opened = set()

    def switch_lang(self, code):
        if code == i18n.get_lang():
            return
        QtCore.QSettings("dbnview", "dbnview").setValue("lang", code)
        apply_lang(code)
        old = self.win
        path = old.fi.path if old and old.fi else None
        old.close()
        self.win = MainWindow()
        self.win.show()
        if path:
            self.win.open_path(path)
        old.deleteLater()

    def event(self, e):
        if e.type() == QtCore.QEvent.FileOpen:
            # macOS also turns command-line arguments into FileOpen events: skip duplicates and non-files
            p = e.file()
            if not os.path.isfile(p) or not p.lower().endswith((".dbn", ".zst")):
                return True
            if self.win is None:
                self.pending.append(p)
            elif not (self.win.fi and self.win.fi.path == os.path.abspath(p)) and p not in self.opened:
                self.win.open_path(p)
            return True
        return super().event(e)


def _selftest(app, win, prefix):
    """DBNVIEW_SELFTEST=/path/prefix: render every tab to PNG once the scan finishes, then quit (packaging check)."""
    def pump(n, dt=0.03):
        for _ in range(n):
            app.processEvents()
            time.sleep(dt)

    def step():
        if win.job is None or not win.job.done or win.timer.isActive():
            return QtCore.QTimer.singleShot(200, step)
        for i in range(win.tabs.count()):
            win.tabs.setCurrentIndex(i)
            pump(30)
            if win.tabs.widget(i) is win.iv and win.iv.root.count():
                win.iv.compute()
                t0 = time.time()
                while win.iv.s is None and time.time() - t0 < 60:
                    pump(1, 0.05)
                pump(30)
            win.grab().save("%s_%d.png" % (prefix, i))
        app.quit()

    QtCore.QTimer.singleShot(500, step)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = App(argv)
    apply_lang(QtCore.QSettings("dbnview", "dbnview").value("lang") or i18n.system_lang())
    win = MainWindow()
    app.win = win
    win.show()
    args = [a for a in argv[1:] if not a.startswith("-psn")]
    app.opened = {os.path.abspath(os.path.expanduser(a)) for a in args}
    for p in (args[:1] or app.pending[:1]):
        win.open_path(p if is_remote(p) else os.path.abspath(os.path.expanduser(p)))
    if os.environ.get("DBNVIEW_SELFTEST"):
        _selftest(app, win, os.environ["DBNVIEW_SELFTEST"])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
