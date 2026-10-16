"""Shared GUI helpers: background tasks, theme colors, number/time formatting, ssh host list."""
import html
import re
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from ..display import TsFmt, display_name, fmt_bytes, fmt_dur, fmt_n, fmt_px, ssh_hosts


APP_NAME = "DBNView"
IS_MAC = sys.platform == "darwin"
# monospace stack that exists on macOS, Windows and Linux (used inside rich-text HTML)
MONO_CSS = "font-family:Menlo,Consolas,'DejaVu Sans Mono','Liberation Mono',monospace"


def native_shortcuts(text):
    """Turn macOS shortcut glyphs in UI text into Ctrl/Shift on Windows and Linux."""
    if IS_MAC:
        return text
    return text.replace("⇧⌘", "Ctrl+Shift+").replace("⌘", "Ctrl+")


TZS = [("ET", "America/New_York"), ("CT", "America/Chicago"), ("UTC", "UTC"),
       ("London", "Europe/London"), ("HKT", "Asia/Hong_Kong"), ("JST", "Asia/Tokyo")]


QTY = re.compile(r"sz|size|ct_|count|qty|quantity|volume")


esc = html.escape


class _Sig(QtCore.QObject):
    done = QtCore.Signal(object)
    fail = QtCore.Signal(str)


class _Task(QtCore.QRunnable):
    live = set()

    def __init__(self, fn, args):
        super().__init__()
        self.fn, self.args, self.sig = fn, args, _Sig()
        self.setAutoDelete(True)

    def run(self):
        try:
            res = self.fn(*self.args)
        except Exception as e:  # noqa: BLE001
            self.sig.fail.emit("%s: %s" % (type(e).__name__, e))
        else:
            self.sig.done.emit(res)


def run_bg(fn, *args, done=None, fail=None):
    """Run fn(*args) on the thread pool; callbacks are delivered on the GUI thread."""
    t = _Task(fn, args)
    sig = t.sig
    _Task.live.add(sig)

    def fin(*_):
        _Task.live.discard(sig)

    if done:
        sig.done.connect(done)
    if fail:
        sig.fail.connect(fail)
    sig.done.connect(fin)
    sig.fail.connect(fin)
    QtCore.QThreadPool.globalInstance().start(t)


def is_dark():
    return QtWidgets.QApplication.palette().color(QtGui.QPalette.Window).lightness() < 128


def theme():
    d = is_dark()
    return {
        "bid": "#3ccf8e" if d else "#139a5b", "ask": "#ff6b6b" if d else "#d63b3b",
        "accent": "#5b9dff" if d else "#2f6fde", "warn": "#e3b341" if d else "#a87400",
        "muted": "#8a94a3" if d else "#5f6b7a", "faint": "#5d6674" if d else "#a0a8b4",
        "bg": QtWidgets.QApplication.palette().color(QtGui.QPalette.Base).name(),
        "text": QtWidgets.QApplication.palette().color(QtGui.QPalette.Text).name(),
        "line": "#2a313c" if d else "#e3e6ea",
    }


def blend(hex_color, alpha, bg):
    c, b = QtGui.QColor(hex_color), QtGui.QColor(bg)
    mix = lambda x, y: int(round(x * alpha + y * (1 - alpha)))
    return QtGui.QColor(mix(c.red(), b.red()), mix(c.green(), b.green()), mix(c.blue(), b.blue())).name()


FIELD_HUES = ["#5b9dff", "#3ccf8e", "#e3b341", "#ff6b6b", "#b48cff", "#4fc1c9"]


def field_color(name, i, bg):
    if re.match(r"^_reserved|^_dummy|padding", name):
        return blend("#888888", 0.18, bg)
    return blend(FIELD_HUES[i % len(FIELD_HUES)], 0.35, bg)


__all__ = ["APP_NAME", "IS_MAC", "MONO_CSS", "QTY", "TZS", "TsFmt", "blend", "display_name", "esc", "field_color",
           "fmt_bytes", "fmt_dur", "fmt_n", "fmt_px", "is_dark", "native_shortcuts", "run_bg", "ssh_hosts", "theme"]
