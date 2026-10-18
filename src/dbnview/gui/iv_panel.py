"""IV surface tab for option chains (OPRA symbology): 3D surface / heatmap, smile and term-structure slices."""
import csv
import datetime as dt

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from ..analysis import options
from ..engine import parse_time
from ..i18n import T
from . import gestures
from .common import native_shortcuts

try:
    import pyqtgraph.opengl as gl
    HAVE_GL = True
except Exception:  # noqa: BLE001
    HAVE_GL = False

XAXES = [("k", "Log-Moneyness ln(K/F)"), ("K", "Strike K"), ("delta", "Call Delta")]
SIDES = [("otm", "Out-of-the-Money (OTM)"), ("call", "Call"), ("put", "Put"), ("both", "Call + Put")]
PALETTE = ["#5b9dff", "#3ccf8e", "#e3b341", "#ff6b6b", "#b48cff", "#4fc1c9", "#f08bd0", "#9aa4b1",
           "#ff9f43", "#26de81", "#a55eea", "#45aaf2"]


def exp_label(ordinal, days):
    return "%s (%.1fd)" % (dt.date.fromordinal(int(ordinal)).isoformat(), days)


class IVPanel(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.s = None
        self.ch = None
        self.g = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        bar = QtWidgets.QHBoxLayout()
        self.root = QtWidgets.QComboBox()
        self.root.setMinimumWidth(90)
        self.time_edit = QtWidgets.QLineEdit()
        self.time_edit.setPlaceholderText("15:45")
        self.time_edit.setMinimumWidth(150)
        self.time_edit.setMaximumWidth(200)
        self.time_edit.returnPressed.connect(self.compute)
        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(1000)
        self.slider.setMinimumWidth(160)
        self.slider.valueChanged.connect(self.on_slider)
        self.slider.sliderReleased.connect(self.compute)
        self.spot = QtWidgets.QLineEdit()
        self.spot.setPlaceholderText(T("Auto (Parity)"))
        self.spot.setMaximumWidth(110)
        self.rate = QtWidgets.QDoubleSpinBox()
        self.rate.setRange(-5, 20)
        self.rate.setDecimals(2)
        self.rate.setValue(4.0)
        self.rate.setSuffix(" %")
        self.side = QtWidgets.QComboBox()
        for k, label in SIDES:
            self.side.addItem(T(label), k)
        self.xaxis = QtWidgets.QComboBox()
        for k, label in XAXES:
            self.xaxis.addItem(T(label), k)
        self.xaxis.currentIndexChanged.connect(lambda _: self.redraw())
        self.maxspread = QtWidgets.QSpinBox()
        self.maxspread.setRange(1, 1000)
        self.maxspread.setValue(50)
        self.maxspread.setSuffix(" %")
        self.mindays = QtWidgets.QDoubleSpinBox()
        self.mindays.setRange(0, 365)
        self.mindays.setValue(2.0)
        self.maxage = QtWidgets.QSpinBox()
        self.maxage.setRange(0, 100000)
        self.maxage.setValue(30)
        self.maxage.setSuffix(T(" min"))
        self.maxage.setSpecialValueText(T("No Limit"))
        self.maxage.setToolTip(T("Only use quotes updated within this time (0 = no limit)"))
        self.mindays.setSuffix(T(" days"))
        go = QtWidgets.QPushButton(T("Compute"))
        go.clicked.connect(self.compute)
        exp_btn = QtWidgets.QPushButton(T("Export CSV…"))
        exp_btn.clicked.connect(self.export)
        # two rows so nothing overlaps in a narrow window
        bar2 = QtWidgets.QHBoxLayout()
        for label, w in ((T("Underlying"), self.root), (T("Time"), self.time_edit)):
            bar.addWidget(QtWidgets.QLabel(label))
            bar.addWidget(w)
        bar.addWidget(self.slider, 1)
        bar.addWidget(go)
        bar.addWidget(exp_btn)
        for label, w in ((T("Underlying Price"), self.spot), ("r", self.rate), (T("Options"), self.side),
                         (T("X Axis"), self.xaxis),
                         (T("Max Spread"), self.maxspread), (T("Min Expiry"), self.mindays),
                         (T("Max Quote Age"), self.maxage)):
            bar2.addWidget(QtWidgets.QLabel(label))
            bar2.addWidget(w)
        bar2.addStretch()
        lay.addLayout(bar)
        lay.addLayout(bar2)
        self.note = QtWidgets.QLabel(T("Open a file with option quotes (e.g. OPRA cbbo-1m / cmbp-1 / tcbbo / trades "
                                       "/ ohlcv), then press “Compute”."))
        self.note.setStyleSheet("color:gray")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        split = QtWidgets.QSplitter(Qt.Horizontal)
        self.views = QtWidgets.QTabWidget()
        self.views.setDocumentMode(True)
        gl_ok, gl_desc = gestures.opengl_status() if HAVE_GL and gestures.ZoomGLView is not None else (False, "")
        if gl_ok:
            self.gl = gestures.ZoomGLView()
            self.gl.setCameraPosition(distance=40, elevation=26, azimuth=-60)
            box = QtWidgets.QWidget()
            bl = QtWidgets.QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            cam = QtWidgets.QHBoxLayout()
            for text, fn in (("＋", lambda: self.gl.zoom(0.8)), ("－", lambda: self.gl.zoom(1.25)),
                             (T("Top"), lambda: self.gl.preset("top")), (T("Front"), lambda: self.gl.preset("front")),
                             (T("view|Side"), lambda: self.gl.preset("side")), (T("Reset View"), self.reset_camera)):
                b = QtWidgets.QPushButton(text)
                b.setAutoDefault(False)
                b.clicked.connect(fn)
                cam.addWidget(b)
            hint = QtWidgets.QLabel(native_shortcuts(T("Drag to rotate · scroll or pinch to zoom · middle-drag or "
                                                       "⌘+drag to pan")))
            hint.setStyleSheet("color:gray")
            cam.addWidget(hint)
            cam.addStretch()
            bl.addLayout(cam)
            bl.addWidget(self.gl, 1)
            self.views.addTab(box, T("3D Surface"))
        else:
            self.gl = None
        self.heat = pg.PlotWidget()
        self.heat.setLabel("left", T("Expiry (days)"))
        self.heat_img = None
        self.heat.scene().sigMouseClicked.connect(self.on_heat_click)
        self.views.addTab(self.heat, T("Heatmap (Click to Pick a Slice)"))
        if self.gl is None and gl_desc:  # after the heatmap (the default view): say why there is no 3D view
            msg = QtWidgets.QLabel(T("OpenGL on this computer cannot show the 3D view (%s). Use the heatmap and "
                                     "slice charts instead.") % gl_desc)
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet("color:gray; padding:24px")
            self.views.addTab(msg, T("3D Surface"))
        split.addWidget(self.views)

        right = QtWidgets.QSplitter(Qt.Vertical)
        smile_box = QtWidgets.QWidget()
        sl = QtWidgets.QHBoxLayout(smile_box)
        sl.setContentsMargins(0, 0, 0, 0)
        self.exp_list = QtWidgets.QListWidget()
        self.exp_list.setMaximumWidth(190)
        self.exp_list.itemChanged.connect(lambda _: self.draw_smile())
        self.smile = pg.PlotWidget()
        self.smile.addLegend(offset=(5, 5))
        self.smile.setLabel("left", "IV")
        self.smile.showGrid(x=True, y=True, alpha=0.15)
        for w_ in (self.smile, self.heat):
            for a_ in ("left", "bottom"):
                w_.getAxis(a_).enableAutoSIPrefix(False)
        el = QtWidgets.QVBoxLayout()
        el.addWidget(QtWidgets.QLabel(T("Expiries (Checked = Smile Slice)")))
        el.addWidget(self.exp_list, 1)
        sl.addLayout(el)
        sl.addWidget(self.smile, 1)
        right.addWidget(smile_box)
        term_box = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(term_box)
        tl.setContentsMargins(0, 0, 0, 0)
        tbar = QtWidgets.QHBoxLayout()
        self.term_x = QtWidgets.QLineEdit("0")
        self.term_x.setMaximumWidth(110)
        self.term_x.returnPressed.connect(self.draw_term)
        self.term_label = QtWidgets.QLabel()
        tbar.addWidget(self.term_label)
        tbar.addWidget(self.term_x)
        tbar.addStretch()
        tl.addLayout(tbar)
        self.term = pg.PlotWidget()
        self.term.setLabel("left", "IV")
        self.term.setLabel("bottom", T("Expiry (days)"))
        self.term.showGrid(x=True, y=True, alpha=0.15)
        for a_ in ("left", "bottom"):
            self.term.getAxis(a_).enableAutoSIPrefix(False)
        tl.addWidget(self.term, 1)
        right.addWidget(term_box)
        right.setSizes([520, 300])
        for w_ in (self.heat, self.smile, self.term):
            gestures.enable_pinch(w_)
        split.addWidget(right)
        split.setSizes([700, 640])
        lay.addWidget(split, 1)
        self.update_term_label()

    def reset_camera(self):
        if self.gl is not None:
            self.gl.setCameraPosition(distance=40, elevation=26, azimuth=-60)
            self.gl.opts["center"] = pg.Vector(0, 0, 5)
            self.gl.update()

    # ---- state ------------------------------------------------------------
    def reset(self):
        self.s = None
        self.ch = None
        self.root.clear()
        self.exp_list.clear()
        for p in (self.smile, self.term, self.heat):
            p.clear()
        if self.gl is not None:
            for it in list(self.gl.items):
                self.gl.removeItem(it)

    def prepare(self):
        """Called when a scan finishes: detect option symbology and fill the root list."""
        job = self.win.job
        self.reset()
        if job is None or not options.is_option_data(job):
            self.note.setText(T("This file doesn't look like options data (no OSI option symbols found, e.g. SPY   "
                                "260116C00690000)."))
            return False
        self.ch = options.chain(job)
        for r in options.roots(self.ch):
            self.root.addItem(r)
        st = self.win.status
        self.t_lo = int(st["tmin"]) if st and st.get("tmin") else job.fi.md["start"]
        self.t_hi = int(st["tmax"]) if st and st.get("tmax") else (job.fi.md["end"] or self.t_lo)
        self.slider.blockSignals(True)
        self.slider.setValue(1000)
        self.slider.blockSignals(False)
        self.on_slider(1000)
        self.note.setText(T("Found %d option contracts, %d underlyings. Press “Compute” to build the surface.")
                          % (len(self.ch), self.root.count()))
        return True

    def on_slider(self, v):
        if not hasattr(self, "t_lo"):
            return
        t = self.t_lo + (self.t_hi - self.t_lo) * v / 1000.0
        self.time_edit.setText(self.win.tsfmt.fmt(int(t), "dt")[:19])

    def update_term_label(self):
        x = self.xaxis.currentData()
        self.term_label.setText({"k": T("Term Structure: Fixed ln(K/F) ="), "K": T("Term Structure: Fixed Strike K ="),
                                 "delta": T("Term Structure: Fixed Call Delta =")}[x])

    # ---- compute ------------------------------------------------------------
    def compute(self):
        job = self.win.job
        if job is None or not self.root.count():
            return
        try:
            t_ns = parse_time(self.time_edit.text(), self.win.tsfmt.tz, self.t_lo) if self.time_edit.text().strip() \
                else self.t_hi
        except Exception as e:  # noqa: BLE001
            self.note.setText(T("Invalid time format: %s") % e)
            return
        spot = float(self.spot.text()) if self.spot.text().strip() else None
        args = dict(root=self.root.currentText(), r=self.rate.value() / 100.0, spot=spot, side=self.side.currentData(),
                    max_spread=self.maxspread.value() / 100.0, min_days=self.mindays.value(), ch=self.ch,
                    max_age_s=self.maxage.value() * 60 or None)
        self.note.setText(T("Computing…"))
        self._prog = [0, 1]
        args["progress"] = lambda done, tot: self._prog.__setitem__(slice(0, 2), [done, tot])
        token = object()
        self._token = token
        args["cancel"] = lambda: self._token is not token
        timer = QtCore.QTimer(self)
        timer.setInterval(300)
        timer.timeout.connect(lambda: self.note.setText(T("Loaded rows don't cover this time; streaming from the "
                                                          "start of the file… %.0f%%")
                                                       % (100.0 * self._prog[0] / max(self._prog[1], 1))) if self._prog[0] else None)
        timer.start()

        def done(s):
            timer.stop()
            if token is not self._token:
                return
            if s is None or len(s["iv"]) == 0:
                self.note.setText(T("No usable option quotes at this time (try a later time, or relax the spread / "
                                    "expiry limits)."))
                return
            self.s = s
            self.fill_exp_list()
            self.redraw()
            fw = s["forwards"]
            age = np.nanmedian(s["age_s"]) if len(s["age_s"]) else 0
            self.note.setText(T("%s @ %s %s · %d IV points (%d quotes) · %d expiries · forward from put-call parity "
                                "· median quote age %.0f s%s") % (
                s["root"], self.win.tsfmt.fmt(s["t_ns"], "dt")[:19], self.win.tsfmt.tz_short, len(s["iv"]), s["n_quotes"],
                len(fw), age, T(" (streamed from file)") if s.get("streamed") else ""))

        def fail(e):
            timer.stop()
            self.note.setText(e)

        self.win.run_bg(lambda: options.surface(job, t_ns, **args), done=done, fail=fail)

    def fill_exp_list(self):
        s = self.s
        self.exp_list.blockSignals(True)
        prev = {self.exp_list.item(i).data(Qt.UserRole) for i in range(self.exp_list.count())
                if self.exp_list.item(i).checkState() == Qt.Checked}
        self.exp_list.clear()
        exps = sorted(set(s["exp"].tolist()))
        default = set(exps[:: max(1, len(exps) // 4)][:4]) if not prev else prev
        for e in exps:
            m = s["exp"] == e
            it = QtWidgets.QListWidgetItem("%s · %d" % (exp_label(e, s["days"][m][0]), m.sum()))
            it.setData(Qt.UserRole, e)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if e in default else Qt.Unchecked)
            self.exp_list.addItem(it)
        self.exp_list.blockSignals(False)

    # ---- drawing ------------------------------------------------------------
    def xvals(self):
        return self.s[self.xaxis.currentData()]

    def xlabel(self):
        return dict((k, T(v)) for k, v in XAXES)[self.xaxis.currentData()]

    def redraw(self):
        self.update_term_label()
        if self.s is None:
            return
        self.g = options.grid(self.s, x=self.xaxis.currentData())
        self.draw_heat()
        self.draw_3d()
        self.draw_smile()
        self.draw_term()

    def draw_heat(self):
        p = self.heat
        p.clear()
        g = self.g
        if g is None:
            return
        Z = g["Z"]
        fin = np.isfinite(Z)
        if not fin.any():
            return
        lo, hi = np.nanpercentile(Z[fin], 2), np.nanpercentile(Z[fin], 98)
        cmap = pg.colormap.get("viridis")
        norm = np.clip((Z - lo) / max(hi - lo, 1e-9), 0, 1)
        rgba = cmap.map(np.nan_to_num(norm), mode="byte")
        rgba[~fin] = [0, 0, 0, 0]
        img = pg.ImageItem(rgba.reshape(Z.shape + (4,)), axisOrder="col-major")
        nexp = Z.shape[1]
        img.setRect(QtCore.QRectF(g["x"][0], 0, g["x"][-1] - g["x"][0], nexp))
        p.addItem(img)
        ax = p.getAxis("left")
        step = max(1, nexp // 12)
        ax.setTicks([[(j + 0.5, "%s %.0fd" % (dt.date.fromordinal(int(e)).strftime("%m-%d"), d))
                      for j, (e, d) in enumerate(zip(g["exps"], g["days"])) if j % step == 0]])
        p.setLabel("bottom", self.xlabel())
        p.setTitle(T("IV heatmap (%.1f%% – %.1f%%), click to pick a slice") % (lo * 100, hi * 100))
        p.autoRange()
        self.heat_img = img

    def on_heat_click(self, ev):
        if self.g is None:
            return
        pos = self.heat.plotItem.vb.mapSceneToView(ev.scenePos())
        j = int(np.floor(pos.y()))
        if not (0 <= j < len(self.g["exps"])):
            return
        e = self.g["exps"][j]
        self.exp_list.blockSignals(True)
        for i in range(self.exp_list.count()):
            it = self.exp_list.item(i)
            if it.data(Qt.UserRole) == e:
                it.setCheckState(Qt.Checked)
        self.exp_list.blockSignals(False)
        self.term_x.setText("%.4g" % pos.x())
        self.draw_smile()
        self.draw_term()

    def draw_3d(self):
        if self.gl is None:
            return
        for it in list(self.gl.items):
            self.gl.removeItem(it)
        g = self.g
        if g is None:
            return
        Z = g["Z"].copy()
        fin = np.isfinite(Z)
        if not fin.any():
            return
        # fill gaps along x (per expiry) for a continuous mesh; shown slightly transparent
        for j in range(Z.shape[1]):
            col = Z[:, j]
            ok = np.isfinite(col)
            if ok.sum() >= 2:
                Z[:, j] = np.interp(np.arange(len(col)), np.flatnonzero(ok), col[ok])
            elif ok.sum() == 1:
                Z[:, j] = col[ok][0]
        filled = np.isfinite(Z).all(axis=0)
        Z = Z[:, filled]
        if Z.shape[1] < 2:
            return
        exps = [e for e, f in zip(g["exps"], filled) if f]
        days = g["days"][filled]
        lo, hi = np.nanpercentile(Z, 2), np.nanpercentile(Z, 98)
        Z = np.clip(Z, lo, hi)
        X = np.linspace(-10, 10, Z.shape[0])
        Y = np.linspace(-10, 10, Z.shape[1])
        Zs = (Z - lo) / max(hi - lo, 1e-9) * 10
        cmap = pg.colormap.get("viridis")
        cols = cmap.map((Zs / 10).ravel(), mode="float").reshape(Z.shape + (4,))
        surf = gl.GLSurfacePlotItem(x=X, y=Y, z=Zs, colors=cols, shader=None, smooth=True, drawEdges=True,
                                    edgeColor=(0.1, 0.1, 0.1, 0.25))
        surf.setGLOptions("opaque")
        self.gl.addItem(surf)
        self.gl.opts["center"] = pg.Vector(0, 0, 5)
        grid = gl.GLGridItem()
        grid.setSize(20, 20)
        grid.setSpacing(2, 2)
        self.gl.addItem(grid)
        txt = self.win.colors["text"]
        col = QtGui.QColor(txt)
        lab = lambda pos, s: self.gl.addItem(gl.GLTextItem(pos=pos, text=s, color=col))
        xs = g["x"]
        for f in (0, 0.5, 1):
            v = xs[0] + (xs[-1] - xs[0]) * f
            lab((-10 + 20 * f, -11.5, 0), ("%.2f" % v) if self.xaxis.currentData() != "K" else "%g" % v)
        lab((0, -13.5, 0), self.xlabel())
        step = max(1, len(exps) // 5)
        for j in range(0, len(exps), step):
            lab((11, Y[j], 0), "%.0fd" % days[j])
        lab((12.5, 0, 0), T("Expiry"))
        for f in (0, 0.5, 1):
            lab((-11, 11, 10 * f), "%.1f%%" % ((lo + (hi - lo) * f) * 100))
        lab((-11, 11, 11.5), "IV")

    def selected_exps(self):
        return [self.exp_list.item(i).data(Qt.UserRole) for i in range(self.exp_list.count())
                if self.exp_list.item(i).checkState() == Qt.Checked]

    def draw_smile(self):
        p = self.smile
        p.clear()
        if p.plotItem.legend is not None:
            p.plotItem.legend.clear()
        s = self.s
        if s is None:
            return
        xs = self.xvals()
        for n, e in enumerate(self.selected_exps()):
            m = s["exp"] == e
            if not m.any():
                continue
            col = PALETTE[n % len(PALETTE)]
            o = np.argsort(xs[m])
            x, y = xs[m][o], s["iv"][m][o]
            cp = s["cp"][m][o]
            p.plot(x, y, pen=pg.mkPen(col, width=1.6), name=exp_label(e, s["days"][m][0]))
            for kind, sym in (("C", "o"), ("P", "t")):
                mm = cp == kind
                if mm.any():
                    p.plot(x[mm], y[mm], pen=None, symbol=sym, symbolSize=6, symbolBrush=col, symbolPen=None)
            yb, ya = s["iv_bid"][m][o], s["iv_ask"][m][o]
            ok = np.isfinite(yb) & np.isfinite(ya)
            if ok.any():
                err = pg.ErrorBarItem(x=x[ok], y=(yb[ok] + ya[ok]) / 2, height=ya[ok] - yb[ok],
                                      pen=pg.mkPen(_alpha(col, 110), width=1), beam=0)
                p.addItem(err)
        sel = np.isin(s["exp"], self.selected_exps())
        if sel.any():
            ys = s["iv"][sel]
            lo, hi = np.nanpercentile(ys, 1), np.nanpercentile(ys, 97)
            p.setYRange(max(0, lo - 0.1 * (hi - lo)), hi + 0.15 * (hi - lo), padding=0)
        if self.xaxis.currentData() == "k":
            p.addItem(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(self.win.colors["muted"], style=Qt.DashLine)))
        p.setLabel("bottom", self.xlabel())
        p.setTitle(T("Smile slice (○ call, △ put; vertical lines = bid/ask IV range)"))

    def draw_term(self):
        p = self.term
        p.clear()
        s = self.s
        if s is None:
            return
        try:
            v = float(self.term_x.text())
        except ValueError:
            return
        d, iv, _ = options.term_at(s, self.xaxis.currentData(), v)
        if len(d) == 0:
            p.setTitle(T("Not enough data here"))
            return
        col = self.win.colors["accent"]
        p.plot(d, iv, pen=pg.mkPen(col, width=1.8), symbol="o", symbolSize=6, symbolBrush=col, symbolPen=None)
        p.setTitle(T("Term structure @ %s = %s") % (self.xlabel(), self.term_x.text()))

    def export(self):
        s = self.s
        if s is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, T("Export CSV…"), "iv_%s.csv" % s["root"], "CSV (*.csv)")
        if not path:
            return
        cols = ["sym", "iid", "exp", "days", "cp", "K", "F", "k", "delta", "bid", "ask", "mid", "iv", "iv_bid", "iv_ask", "age_s"]
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for i in range(len(s["iv"])):
                row = []
                for c in cols:
                    v = s[c][i]
                    if c == "exp":
                        v = dt.date.fromordinal(int(v)).isoformat()
                    elif isinstance(v, (float, np.floating)):
                        v = "" if not np.isfinite(v) else round(float(v), 8)
                    elif isinstance(v, np.generic):
                        v = v.item()
                    row.append(v)
                w.writerow(row)
        self.note.setText(T("Exported %d rows → %s") % (len(s["iv"]), path))


def _alpha(hex_color, a):
    c = QtGui.QColor(hex_color)
    c.setAlpha(a)
    return c
