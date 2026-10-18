"""Startup splash (also used by Help -> About): product name, version, disclaimer and loading messages."""
from importlib import resources

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import __version__
from ..i18n import T

WIDTH, HEIGHT = 860, 516


def asset_pixmap(name):
    data = resources.files("dbnview.gui").joinpath("assets/" + name).read_bytes()
    pm = QtGui.QPixmap()
    pm.loadFromData(data)
    return pm


def app_icon():
    return QtGui.QIcon(asset_pixmap("icon.png"))


def _render(message):
    """Draw the whole splash into a HiDPI pixmap."""
    screen = QtGui.QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 2.0
    pm = QtGui.QPixmap(int(WIDTH * dpr), int(HEIGHT * dpr))
    pm.setDevicePixelRatio(dpr)
    p = QtGui.QPainter(pm)
    p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing | QtGui.QPainter.SmoothPixmapTransform)
    rect = QtCore.QRectF(0, 0, WIDTH, HEIGHT)
    bg = asset_pixmap("splash.jpg")
    p.drawPixmap(rect, bg, QtCore.QRectF(bg.rect()))
    # darker band on the left and bottom so the text stays readable
    g = QtGui.QLinearGradient(0, 0, WIDTH, 0)
    g.setColorAt(0.0, QtGui.QColor(8, 11, 18, 235))
    g.setColorAt(0.55, QtGui.QColor(8, 11, 18, 150))
    g.setColorAt(1.0, QtGui.QColor(8, 11, 18, 40))
    p.fillRect(rect, g)
    gb = QtGui.QLinearGradient(0, HEIGHT * 0.62, 0, HEIGHT)
    gb.setColorAt(0.0, QtGui.QColor(8, 11, 18, 0))
    gb.setColorAt(1.0, QtGui.QColor(8, 11, 18, 235))
    p.fillRect(rect, gb)

    x = 48
    p.drawPixmap(QtCore.QRectF(x, 52, 64, 64), asset_pixmap("icon.png"), QtCore.QRectF(0, 0, 256, 256))
    f = QtGui.QFont(QtWidgets.QApplication.font())
    f.setPixelSize(46)
    f.setWeight(QtGui.QFont.Bold)
    p.setFont(f)
    p.setPen(QtGui.QColor("#eef2f7"))
    p.drawText(QtCore.QPointF(x + 80, 102), "DBNView")
    f.setPixelSize(17)
    f.setWeight(QtGui.QFont.Normal)
    p.setFont(f)
    p.setPen(QtGui.QColor("#aab4c3"))
    p.drawText(QtCore.QRectF(x, 132, 520, 26), Qt.AlignLeft | Qt.AlignVCenter, T(
            "Market-data viewer for Databento DBN files"))
    f.setPixelSize(13)
    p.setFont(f)
    p.setPen(QtGui.QColor("#5b9dff"))
    p.drawText(QtCore.QRectF(x, 162, 520, 22), Qt.AlignLeft | Qt.AlignVCenter, T("Version %s") % __version__)
    p.setPen(QtGui.QColor("#7f8a9a"))
    p.drawText(QtCore.QRectF(x, 186, 600, 22), Qt.AlignLeft | Qt.AlignVCenter,
               "DBN v1–v3 · MBO · MBP · CBBO · OHLCV · Options · Desktop / Terminal / Browser")

    # disclaimer
    f.setPixelSize(11)
    p.setFont(f)
    box = QtCore.QRectF(x, HEIGHT - 128, WIDTH - 2 * x, 76)
    p.setPen(QtGui.QColor("#9aa4b1"))
    p.drawText(box, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, T("Disclaimer: ") + T(
        "This software is for research and educational use only and is not investment advice or a basis "
        "for trading. Market data and computed results (such as implied volatility and gamma exposure) may "
        "be inaccurate or delayed; you use them at your own judgment and risk. DBNView is an independent "
        "project with no affiliation to Databento, Inc.; Databento is a trademark of its owner."))
    # status line
    f.setPixelSize(12)
    p.setFont(f)
    p.setPen(QtGui.QColor("#cfd6e0"))
    p.drawText(QtCore.QRectF(x, HEIGHT - 40, WIDTH - 2 * x, 22), Qt.AlignLeft | Qt.AlignVCenter, message or "")
    p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 30), 1))
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
    p.end()
    return pm


class Splash(QtWidgets.QSplashScreen):
    """Startup splash; click to dismiss. `about=True` makes it stay until clicked (Help -> About)."""

    def __init__(self, about=False):
        super().__init__(_render(T("Click to close") if about else T("Loading…")))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, not about)

    def message(self, text):
        self.setPixmap(_render(text))
        QtWidgets.QApplication.processEvents()
