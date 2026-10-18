"""Trackpad pinch-to-zoom for pyqtgraph 2D plots and the 3D GL view (macOS native gestures), and an OpenGL check."""
import os
import sys

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt
import pyqtgraph as pg

try:
    import pyqtgraph.opengl as gl
except Exception:  # noqa: BLE001
    gl = None


_GL_STATUS = None


def opengl_status():
    """(usable, description) for the OpenGL a 3D view would get; probed once with an offscreen context.

    pyqtgraph's 3D view needs OpenGL 2.0 or newer. Without it (virtual machines, Remote Desktop, Windows' built-in
    "GDI Generic" 1.1 driver) the first paint raises GLError and the next GL call can crash the process, so the
    caller falls back to 2D views. DBNVIEW_NO_GL=1 forces the fallback.
    """
    global _GL_STATUS
    if _GL_STATUS is None:
        _GL_STATUS = _probe_opengl()
    return _GL_STATUS


def _probe_opengl():
    if gl is None:
        return False, "pyqtgraph.opengl is not available"
    if os.environ.get("DBNVIEW_NO_GL"):
        return False, "disabled by DBNVIEW_NO_GL"
    ctx = QtGui.QOpenGLContext()
    if not ctx.create():
        return False, "no OpenGL context"
    surface = QtGui.QOffscreenSurface()
    surface.setFormat(ctx.format())
    surface.create()
    try:
        if not surface.isValid() or not ctx.makeCurrent(surface):
            return False, "cannot use an OpenGL context"
        f = ctx.functions()
        version = (ctx.format().majorVersion(), ctx.format().minorVersion())
        text = lambda name: str(f.glGetString(name) or "").strip()
        desc = "OpenGL %s (%s)" % (text(0x1F02) or "%d.%d" % version, text(0x1F01) or "unknown renderer")
        if version < (2, 0) or "GDI Generic" in desc:
            return False, desc + ": 2.0 or newer is required"
        # pyqtgraph draws through PyOpenGL, which calls the system OpenGL library directly. When Qt has switched to
        # its own software renderer (opengl32sw.dll on a machine without a GPU driver) that library has no current
        # context: the first call raises GLError and the next one crashes. Try the first call pyqtgraph makes.
        from OpenGL import GL
        try:
            GL.glClearColor(0.0, 0.0, 0.0, 1.0)
        except Exception as e:  # noqa: BLE001
            return False, desc + ": PyOpenGL cannot draw with this context (%s)" % type(e).__name__
        return True, desc
    except Exception as e:  # noqa: BLE001 - any failure here means: do not create GL widgets
        return False, "OpenGL check failed: %s" % e
    finally:
        ctx.doneCurrent()
        surface.destroy()


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

        gl_failed = False

        def paintGL(self, *args, **kwargs):
            # After one failed paint, more GL calls on a broken context can crash the process: stop drawing.
            if self.gl_failed:
                return
            try:
                super().paintGL(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                self.gl_failed = True
                print("DBNView: 3D view disabled after an OpenGL error: %s" % e, file=sys.stderr)

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
