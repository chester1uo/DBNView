"""Prepare the splash background: desaturate, fade toward the dark theme color, resize, save as JPEG.

    python packaging/make_splash.py path/to/source-image  ->  src/dbnview/gui/assets/splash.jpg
"""
import os
import sys

import numpy as np
from PySide6 import QtCore, QtGui

SATURATION = 0.35   # keep 35% of the original color
OPACITY = 0.42      # image weight over the dark background
BG = np.array([12, 16, 24], dtype=np.float32)
WIDTH = 1280

app = QtGui.QGuiApplication(sys.argv[:1])
img = QtGui.QImage(sys.argv[1])
if img.isNull():
    sys.exit("cannot read %s" % sys.argv[1])
img = img.scaledToWidth(WIDTH, QtCore.Qt.SmoothTransformation).convertToFormat(QtGui.QImage.Format_RGB888)
w, h, bpl = img.width(), img.height(), img.bytesPerLine()
a = np.frombuffer(img.constBits(), dtype=np.uint8, count=bpl * h).reshape(h, bpl)[:, : w * 3].reshape(h, w, 3)
rgb = a.astype(np.float32)
gray = (rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[..., None]
rgb = gray + SATURATION * (rgb - gray)
rgb = BG + OPACITY * (rgb - BG)
out = np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8))
res = QtGui.QImage(out.data, w, h, w * 3, QtGui.QImage.Format_RGB888).copy()
dst = os.path.join(os.path.dirname(__file__), "..", "src", "dbnview", "gui", "assets", "splash.jpg")
res.save(dst, "JPG", 86)
print("wrote", os.path.abspath(dst), w, h, os.path.getsize(dst))
