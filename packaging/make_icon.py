"""Draw the app icon: packaging/icon.png (Linux), dbnview.ico (Windows) and dbnview.icns (macOS, needs iconutil)."""
import os, shutil, subprocess, sys
from PySide6 import QtCore, QtGui, QtWidgets

here = os.path.dirname(os.path.abspath(__file__))
app = QtWidgets.QApplication(sys.argv[:1])


def draw(size):
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    s = size / 1024.0
    rect = QtCore.QRectF(100 * s, 100 * s, 824 * s, 824 * s)
    g = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QtGui.QColor("#1d2b45"))
    g.setColorAt(1, QtGui.QColor("#0d1117"))
    p.setBrush(g)
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(rect, 185 * s, 185 * s)
    # order-book ladder: asks (red) above, bids (green) below
    widths = [0.30, 0.48, 0.62, 0.40]
    for i, w in enumerate(widths):
        p.setBrush(QtGui.QColor("#ff6b6b"))
        p.drawRoundedRect(QtCore.QRectF(250 * s, (250 + i * 62) * s, w * 524 * s, 40 * s), 10 * s, 10 * s)
    for i, w in enumerate(reversed(widths)):
        p.setBrush(QtGui.QColor("#3ccf8e"))
        p.drawRoundedRect(QtCore.QRectF(250 * s, (530 + i * 62) * s, w * 524 * s, 40 * s), 10 * s, 10 * s)
    p.setPen(QtGui.QPen(QtGui.QColor("#5b9dff"), 14 * s))
    p.drawLine(QtCore.QPointF(230 * s, 505 * s), QtCore.QPointF(794 * s, 505 * s))
    f = QtGui.QFont("Menlo")
    f.setPixelSize(int(120 * s))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QtGui.QColor("#e4e8ee"))
    p.drawText(QtCore.QRectF(560 * s, 230 * s, 260 * s, 140 * s), QtCore.Qt.AlignRight, "DBN")
    p.end()
    return img


draw(1024).save(os.path.join(here, "icon.png"))
draw(256).save(os.path.join(here, "dbnview.ico"))
if shutil.which("iconutil"):
    iconset = os.path.join(here, "dbnview.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)
    for n in (16, 32, 128, 256, 512):
        draw(n).save(os.path.join(iconset, "icon_%dx%d.png" % (n, n)))
        draw(n * 2).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (n, n)))
    subprocess.check_call(["iconutil", "-c", "icns", iconset, "-o", os.path.join(here, "dbnview.icns")])
    shutil.rmtree(iconset)
print("ok")
