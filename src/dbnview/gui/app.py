"""Desktop entry point: `dbnview [file | ssh://host/path]` (also `python -m dbnview`)."""
import os
import sys
import time

from PySide6 import QtCore, QtWidgets

from .. import i18n, reference
from ..engine import is_remote
from .common import APP_NAME


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
        from .main_window import MainWindow
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


class _SelftestLog:
    """Progress log for the self-test at <prefix>_selftest.log.

    A windowed build (Windows) has no console, so this file is the only trace of a run. faulthandler writes every
    thread's stack to it and exits if the run is still going after DBNVIEW_SELFTEST_TIMEOUT seconds (default 240),
    which turns a hang into a failure that says where it stopped.
    """

    def __init__(self, prefix):
        import faulthandler
        import traceback
        self.t0 = time.time()
        self.f = open(prefix + "_selftest.log", "w", buffering=1, encoding="utf-8")
        faulthandler.enable(file=self.f)
        faulthandler.dump_traceback_later(float(os.environ.get("DBNVIEW_SELFTEST_TIMEOUT", 240)), exit=True,
                                          file=self.f)

        def hook(*exc):
            self.f.write("".join(traceback.format_exception(*exc)))
            self.f.flush()
            os._exit(3)
        sys.excepthook = hook
        self("start %s, Qt platform %s" % (sys.platform, QtWidgets.QApplication.platformName()))

    def __call__(self, msg):
        self.f.write("%7.2f  %s\n" % (time.time() - self.t0, msg))
        self.f.flush()


def _selftest(app, win, prefix, note):
    """DBNVIEW_SELFTEST=/path/prefix: render every tab to PNG once the scan finishes, then quit (packaging check)."""
    def pump(n, dt=0.03):
        for _ in range(n):
            app.processEvents()
            time.sleep(dt)

    def step():
        if win.job is None or not win.job.done or win.timer.isActive():
            return QtCore.QTimer.singleShot(200, step)
        note("scan done: %d records" % win.job.n)
        for i in range(win.tabs.count()):
            note("tab %d (%s)" % (i, win.tabs.tabText(i)))
            win.tabs.setCurrentIndex(i)
            pump(30)
            if win.tabs.widget(i) is win.iv and win.iv.root.count():
                win.iv.compute()
                t0 = time.time()
                while win.iv.s is None and time.time() - t0 < 60:
                    pump(1, 0.05)
                pump(30)
            win.grab().save("%s_%d.png" % (prefix, i))
            note("tab %d saved" % i)
        note("done")
        app.quit()

    QtCore.QTimer.singleShot(500, step)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = App(argv)
    note = _SelftestLog(os.environ["DBNVIEW_SELFTEST"]) if os.environ.get("DBNVIEW_SELFTEST") else (lambda msg: None)
    apply_lang(QtCore.QSettings("dbnview", "dbnview").value("lang") or i18n.system_lang())
    from ..i18n import T
    from .splash import Splash, app_icon
    app.setWindowIcon(app_icon())
    shown = time.time()
    splash = Splash()
    splash.show()
    app.processEvents()
    splash.message(T("正在載入圖表與分析模組…"))
    from .main_window import MainWindow  # the heavy imports (pyqtgraph, OpenGL) happen here
    note("imported main window")
    win = MainWindow()
    note("main window built")
    app.win = win
    splash.message(T("準備就緒"))
    while time.time() - shown < 1.2 and not os.environ.get("DBNVIEW_SELFTEST"):  # keep it readable
        app.processEvents()
        time.sleep(0.02)
    win.show()
    splash.finish(win)
    args = [a for a in argv[1:] if not a.startswith("-psn")]
    app.opened = {os.path.abspath(os.path.expanduser(a)) for a in args}
    for p in (args[:1] or app.pending[:1]):
        win.open_path(p if is_remote(p) else os.path.abspath(os.path.expanduser(p)))
    if os.environ.get("DBNVIEW_SELFTEST"):
        note("opened %s" % (args[:1] or app.pending[:1]))
        _selftest(app, win, os.environ["DBNVIEW_SELFTEST"], note)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
