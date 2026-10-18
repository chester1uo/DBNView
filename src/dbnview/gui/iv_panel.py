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

XAXES = [("k", "log-moneyness ln(K/F)"), ("K", "履約價 K"), ("delta", "call delta")]
SIDES = [("otm", "價外 (OTM)"), ("call", "Call"), ("put", "Put"), ("both", "Call + Put")]
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
        self.spot.setPlaceholderText(T("自動（parity）"))
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
        self.maxage.setSuffix(T(" 分"))
        self.maxage.setSpecialValueText(T("不限"))
        self.maxage.setToolTip(T("只用這段時間內有更新的報價（0 = 不限）"))
        self.mindays.setSuffix(T(" 天"))
        go = QtWidgets.QPushButton(T("計算"))
        go.clicked.connect(self.compute)
        exp_btn = QtWidgets.QPushButton(T("匯出 CSV…"))
        exp_btn.clicked.connect(self.export)
        # two rows so nothing overlaps in a narrow window
        bar2 = QtWidgets.QHBoxLayout()
        for label, w in ((T("標的"), self.root), (T("時間"), self.time_edit)):
            bar.addWidget(QtWidgets.QLabel(label))
            bar.addWidget(w)
        bar.addWidget(self.slider, 1)
        bar.addWidget(go)
        bar.addWidget(exp_btn)
        for label, w in ((T("標的價"), self.spot), ("r", self.rate), (T("選擇權"), self.side), (T("X 軸"), self.xaxis),
                         (T("最大價差"), self.maxspread), (T("最短到期"), self.mindays),
                         (T("報價年齡上限"), self.maxage)):
            bar2.addWidget(QtWidgets.QLabel(label))
            bar2.addWidget(w)
        bar2.addStretch()
        lay.addLayout(bar)
        lay.addLayout(bar2)
        self.note = QtWidgets.QLabel(T("開啟含期權報價的檔案（例如 OPRA cbbo-1m / cmbp-1 / tcbbo / trades / ohlcv）後按「計算」。"))
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
                             (T("俯視"), lambda: self.gl.preset("top")), (T("正視"), lambda: self.gl.preset("front")),
                             (T("側視"), lambda: self.gl.preset("side")), (T("重設視角"), self.reset_camera)):
                b = QtWidgets.QPushButton(text)
                b.setAutoDefault(False)
                b.clicked.connect(fn)
                cam.addWidget(b)
            hint = QtWidgets.QLabel(native_shortcuts(T("拖曳旋轉 · 滾輪或雙指捏合縮放 · 中鍵或 ⌘+拖曳平移")))
            hint.setStyleSheet("color:gray")
            cam.addWidget(hint)
            cam.addStretch()
            bl.addLayout(cam)
            bl.addWidget(self.gl, 1)
            self.views.addTab(box, T("3D 曲面"))
        else:
            self.gl = None
        self.heat = pg.PlotWidget()
        self.heat.setLabel("left", T("到期（天）"))
        self.heat_img = None
        self.heat.scene().sigMouseClicked.connect(self.on_heat_click)
        self.views.addTab(self.heat, T("熱圖（點選截面）"))
        if self.gl is None and gl_desc:  # after the heatmap (the default view): say why there is no 3D view
            msg = QtWidgets.QLabel(T("這台電腦的 OpenGL 不支援 3D 檢視（%s），請改用熱圖與截面圖。") % gl_desc)
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet("color:gray; padding:24px")
            self.views.addTab(msg, T("3D 曲面"))
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
        el.addWidget(QtWidgets.QLabel(T("到期日（勾選＝smile 截面）")))
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
        self.term.setLabel("bottom", T("到期（天）"))
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
            self.note.setText(T("這個檔案看起來不是期權資料（找不到 OSI 期權代碼，例如 SPY   260116C00690000）。"))
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
        self.note.setText(T("偵測到 %d 個期權合約、%d 個標的。按「計算」產生曲面。") % (len(self.ch), self.root.count()))
        return True

    def on_slider(self, v):
        if not hasattr(self, "t_lo"):
            return
        t = self.t_lo + (self.t_hi - self.t_lo) * v / 1000.0
        self.time_edit.setText(self.win.tsfmt.fmt(int(t), "dt")[:19])

    def update_term_label(self):
        x = self.xaxis.currentData()
        self.term_label.setText({"k": T("期限結構：固定 ln(K/F) ="), "K": T("期限結構：固定履約價 K ="),
                                 "delta": T("期限結構：固定 call delta =")}[x])

    # ---- compute ------------------------------------------------------------
    def compute(self):
        job = self.win.job
        if job is None or not self.root.count():
            return
        try:
            t_ns = parse_time(self.time_edit.text(), self.win.tsfmt.tz, self.t_lo) if self.time_edit.text().strip() \
                else self.t_hi
        except Exception as e:  # noqa: BLE001
            self.note.setText(T("時間格式錯誤：%s") % e)
            return
        spot = float(self.spot.text()) if self.spot.text().strip() else None
        args = dict(root=self.root.currentText(), r=self.rate.value() / 100.0, spot=spot, side=self.side.currentData(),
                    max_spread=self.maxspread.value() / 100.0, min_days=self.mindays.value(), ch=self.ch,
                    max_age_s=self.maxage.value() * 60 or None)
        self.note.setText(T("計算中…"))
        self._prog = [0, 1]
        args["progress"] = lambda done, tot: self._prog.__setitem__(slice(0, 2), [done, tot])
        token = object()
        self._token = token
        args["cancel"] = lambda: self._token is not token
        timer = QtCore.QTimer(self)
        timer.setInterval(300)
        timer.timeout.connect(lambda: self.note.setText(T("已載入的列不涵蓋這個時間點，正從檔案開頭串流到該時間… %.0f%%")
                                                       % (100.0 * self._prog[0] / max(self._prog[1], 1))) if self._prog[0] else None)
        timer.start()

        def done(s):
            timer.stop()
            if token is not self._token:
                return
            if s is None or len(s["iv"]) == 0:
                self.note.setText(T("這個時間點沒有可用的期權報價（試試較晚的時間，或放寬價差 / 到期條件）。"))
                return
            self.s = s
            self.fill_exp_list()
            self.redraw()
            fw = s["forwards"]
            age = np.nanmedian(s["age_s"]) if len(s["age_s"]) else 0
            self.note.setText(T("%s @ %s %s · %d 個 IV 點（%d 檔報價）· %d 個到期日 · forward 由 put-call parity 推得 · 報價中位數年齡 %.0f 秒%s") % (
                s["root"], self.win.tsfmt.fmt(s["t_ns"], "dt")[:19], self.win.tsfmt.tz_short, len(s["iv"]), s["n_quotes"],
                len(fw), age, T("（從檔案串流取得）") if s.get("streamed") else ""))

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
        p.setTitle(T("IV 熱圖（%.1f%% – %.1f%%），點一下選定截面") % (lo * 100, hi * 100))
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
        lab((12.5, 0, 0), T("到期"))
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
        p.setTitle(T("Smile 截面（○ call、△ put；直線為 bid/ask IV 區間）"))

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
            p.setTitle(T("此位置沒有足夠資料"))
            return
        col = self.win.colors["accent"]
        p.plot(d, iv, pen=pg.mkPen(col, width=1.8), symbol="o", symbolSize=6, symbolBrush=col, symbolPen=None)
        p.setTitle(T("期限結構 @ %s = %s") % (self.xlabel(), self.term_x.text()))

    def export(self):
        s = self.s
        if s is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, T("匯出 CSV…"), "iv_%s.csv" % s["root"], "CSV (*.csv)")
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
        self.note.setText(T("已匯出 %d 列 → %s") % (len(s["iv"]), path))


def _alpha(hex_color, a):
    c = QtGui.QColor(hex_color)
    c.setAlpha(a)
    return c
