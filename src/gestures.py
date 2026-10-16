"""Trackpad pinch-to-zoom for pyqtgraph 2D plots and the 3D GL view (macOS native gestures)."""
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
import pyqtgraph as pg

try:
    import pyqtgraph.opengl as gl
except Exception:  # noqa: BLE001
    gl = None


class _PinchFilter(QtCore.QObject):
    """Event filter for a pyqtgraph GraphicsView: zoom the ViewBox under the fingers."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.NativeGesture and ev.gestureType() == Qt.ZoomNativeGesture:
            factor = 1.0 / (1.0 + ev.value())
            vp = self.view.viewport() if hasattr(self.view, "viewport") else self.view
            pos = vp.mapFromGlobal(ev.globalPosition().toPoint())
            sp = self.view.mapToScene(pos)
            for item in self.view.scene().items(sp):
                if isinstance(item, pg.ViewBox):
                    item.scaleBy(s=(factor, factor), center=item.mapSceneToView(sp))
                    break
            return True
        return False


def enable_pinch(view):
    """view: pg.PlotWidget or pg.GraphicsLayoutWidget."""
    f = _PinchFilter(view)
    view.viewport().installEventFilter(f)
    view.installEventFilter(f)
    view._pinch_filter = f
    return view


if gl is not None:
    class ZoomGLView(gl.GLViewWidget):
        """GLViewWidget with pinch zoom, two-finger rotate and fixed camera presets."""

        def event(self, ev):
            if ev.type() == QtCore.QEvent.NativeGesture:
                t = ev.gestureType()
                if t == Qt.ZoomNativeGesture:
                    self.opts["distance"] = max(2.0, self.opts["distance"] / (1.0 + ev.value()))
                    self.update()
                    return True
                if t == Qt.RotateNativeGesture:
                    self.orbit(-ev.value(), 0)
                    return True
            return super().event(ev)

        def zoom(self, factor):
            self.opts["distance"] = max(2.0, self.opts["distance"] * factor)
            self.update()

        def preset(self, name):
            el, az = {"top": (89, -90), "front": (0, -90), "side": (0, 0), "iso": (24, -60)}[name]
            self.setCameraPosition(distance=self.opts["distance"], elevation=el, azimuth=az)
else:
    ZoomGLView = None
