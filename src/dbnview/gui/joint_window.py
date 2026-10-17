"""Joint stock + option analysis window (opened from the Tools menu)."""
import datetime as dt
import os

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from ..analysis import joint, options, walls
from ..display import display_name
from ..engine import get_tz
from ..i18n import T
from . import gestures
from .charts import TzAxis, add_candles
from .walls_panel import BigAxis

INTERVALS = [(60, "1m"), (300, "5m"), (900, "15m"), (1800, "30m")]


class _PathRow(QtWidgets.QWidget):
    def __init__(self, label, placeholder, settings, key):
        super().__init__()
        self.settings, self.key = settings, key
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QtWidgets.QLineEdit(settings.value(key, ""))
        self.edit.setPlaceholderText(placeholder)
        b = QtWidgets.QPushButton(T("瀏覽…"))
        b.clicked.connect(self.browse)
        lab = QtWidgets.QLabel(label)
        lab.setMinimumWidth(110)
        lay.addWidget(lab)
        lay.addWidget(self.edit, 1)
        lay.addWidget(b)

    def browse(self):
        start = os.path.dirname(self.edit.text()) if self.edit.text() and not self.edit.text().startswith("ssh://") \
            else os.path.expanduser("~")
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, T("開啟 DBN 檔"), start, "DBN (*.dbn *.zst *.dbn.zst)")
        if p:
            self.edit.setText(p)

    def path(self):
        p = self.edit.text().strip()
        if p:
            self.settings.setValue(self.key, p)
        return p or None


class JointWindow(QtWidgets.QMainWindow):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(T("股票＋期權聯合分析"))
        self.resize(1400, 950)
        self.res = None
        self._token = None
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        st = win.settings
        self.stock = _PathRow(T("股票／標的檔"), T("例如 XNAS trades / mbp-1 / ohlcv-1m，或 ssh://host/path"), st, "joint/stock")
        self.opt = _PathRow(T("期權檔"), T("例如 OPRA cbbo-1m / cmbp-1 / tcbbo / trades"), st, "joint/options")
        self.oi = _PathRow(T("持倉量（選填）"), T("同一天的 OPRA statistics 檔；留空會自動在期權檔旁邊尋找"), st, "joint/oi")
        if win.fi is not None and not self.opt.edit.text() and options.is_option_data(win.job):
            self.opt.edit.setText(win.fi.path)
        for row in (self.stock, self.opt, self.oi):
            lay.addWidget(row)
        bar = QtWidgets.QHBoxLayout()
        self.interval = QtWidgets.QComboBox()
        for v, label in INTERVALS:
            self.interval.addItem(label, v)
        self.interval.setCurrentIndex(1)
        self.root = QtWidgets.QLineEdit()
        self.root.setPlaceholderText(T("自動"))
        self.root.setMaximumWidth(90)
        self.rate = QtWidgets.QDoubleSpinBox()
        self.rate.setRange(-5, 20)
        self.rate.setValue(4.0)
        self.rate.setSuffix(" %")
        self.go = QtWidgets.QPushButton(T("分析"))
        self.go.setDefault(True)
        self.go.clicked.connect(self.run)
        self.stop_btn = QtWidgets.QPushButton(T("停止"))
        self.stop_btn.clicked.connect(self.stop)
        for label, w in ((T("週期"), self.interval), (T("期權標的"), self.root), ("r", self.rate)):
            bar.addWidget(QtWidgets.QLabel(label))
            bar.addWidget(w)
        bar.addWidget(self.go)
        bar.addWidget(self.stop_btn)
        self.status = QtWidgets.QLabel(T("選擇股票檔與期權檔後按「分析」。兩者應為同一天、同一標的。"))
        self.status.setStyleSheet("color:gray")
        bar.addWidget(self.status, 1)
        lay.addLayout(bar)
        self.readout = QtWidgets.QLabel(" ")
        self.readout.setFont(win.mono)
        self.readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.readout)
        self.glw = pg.GraphicsLayoutWidget()
        gestures.enable_pinch(self.glw)
        lay.addWidget(self.glw, 1)
        self.setCentralWidget(central)
        self.plots = []

    # ---- run -------------------------------------------------------------------------
    def stop(self):
        self._token = None
        self.status.setText(T("已停止"))

    def run(self):
        stock, opt, oi_path = self.stock.path(), self.opt.path(), self.oi.path()
        if not stock and not opt:
            self.status.setText(T("請至少選一個檔案"))
            return
        interval = self.interval.currentData()
        root = self.root.text().strip().upper() or None
        r = self.rate.value() / 100
        token = object()
        self._token = token
        cancel = lambda: self._token is not token
        prog = {"opt": 0}
        self.status.setText(T("計算中…"))
        timer = QtCore.QTimer(self)
        timer.setInterval(400)
        timer.timeout.connect(lambda: self.status.setText(T("讀取期權檔… %s") % _mb(prog["opt"])) if prog["opt"] else None)
        timer.start()

        def work():
            res = {"interval": interval}
            if stock:
                res["stock"] = joint.underlying_series(stock, interval, cancel)
            rt = root or (joint.symbol_root(res["stock"]["symbol"]) if res.get("stock") else None)
            if opt:
                res["opt"] = joint.option_series(opt, rt, interval, r=r, cancel=cancel,
                                                 progress=lambda n: prog.__setitem__("opt", n))
                rt = res["opt"]["root"]
                o = res["opt"]
                if not o["call_vol"].any() and not o["put_vol"].any():
                    vf = joint.find_volume_file(opt)
                    if vf:
                        joint.merge_flow(o, joint.option_series(vf, rt, interval, r=r, cancel=cancel))
                        res["vol_file"] = vf
                oi_file = oi_path or walls.find_statistics_file(opt)
                if oi_file:
                    res["oi_file"] = oi_file
                    res["oi"] = walls.load_open_interest(oi_file)
            res["root"] = rt
            return res

        def done(res):
            timer.stop()
            if token is not self._token:
                return
            self.res = res
            self.draw()

        def fail(e):
            timer.stop()
            self.status.setText(e)

        self.win.run_bg(work, done=done, fail=fail)

    # ---- drawing -----------------------------------------------------------------------
    def draw(self):
        res, t = self.res, self.win.colors
        self.glw.clear()
        self.glw.setBackground(t["bg"])
        stock, opt = res.get("stock"), res.get("opt")
        rows = [("price", T("價格"))]
        has_flow = opt is not None and (opt["call_vol"].any() or opt["put_vol"].any())
        if opt is not None:
            rows += [("iv", T("隱含波動率 vs 實現波動率")), ("skew", T("偏斜（Put − Call IV）"))]
            if has_flow:
                rows += [("flow", T("期權成交量（Put 向下）")), ("pc", T("Put/Call 比"))]
        elif stock is not None:
            rows += [("iv", T("實現波動率"))]
        self.plots = {}
        first = None
        for i, (key, label) in enumerate(rows):
            axes = {"bottom": TzAxis(self.win)}
            if key == "flow":
                axes["left"] = BigAxis(orientation="left")
            p = self.glw.addPlot(row=i, col=0, axisItems=axes)
            p.showGrid(x=True, y=True, alpha=0.12)
            for ax in ("left", "bottom"):
                p.getAxis(ax).enableAutoSIPrefix(False)
                p.getAxis(ax).setPen(pg.mkPen(t["muted"]))
                p.getAxis(ax).setTextPen(pg.mkPen(t["muted"]))
            p.getAxis("left").setWidth(70)
            p.setTitle(label, size="9pt", color=t["muted"])
            p.addLegend(offset=(10, 5))
            if first is None:
                first = p
            else:
                p.setXLink(first)
                p.setMaximumHeight(190)
            if i < len(rows) - 1:
                p.getAxis("bottom").setStyle(showValues=False)
            self.plots[key] = p
        self.glw.ci.layout.setRowStretchFactor(0, 4)
        pp = self.plots["price"]
        notes = []
        if stock:
            b = stock["bars"]
            iv = res["interval"]
            x = b["t"] + iv / 2
            add_candles(pp, x, b["o"], b["h"], b["l"], b["c"], iv * 0.7, t["bid"], t["ask"])
            notes.append("%s %s · %d %s" % (T("股票"), stock["symbol"], len(x), T("根")))
            self.plots["iv"].plot(x, 100 * stock["rv"], pen=pg.mkPen(t["warn"], width=1.4), name=T("實現波動率"),
                                  connect="finite")
        if opt is not None and len(opt["t"]):
            ox = opt["t"]
            pp.plot(ox, opt["spot"], pen=pg.mkPen(t["accent"], width=1.4, style=Qt.DashLine),
                    name=T("期權隱含標的價（parity）"), connect="finite")
            up, dn = opt["spot"] * (1 + opt["move"]), opt["spot"] * (1 - opt["move"])
            cu = pp.plot(ox, up, pen=pg.mkPen(t["muted"], width=0.8), connect="finite", name=T("前月跨式預期波動區間"))
            cd = pp.plot(ox, dn, pen=pg.mkPen(t["muted"], width=0.8), connect="finite")
            band = QtGui.QColor(t["accent"])
            band.setAlpha(28)
            pp.addItem(pg.FillBetweenItem(cu, cd, brush=pg.mkBrush(band)))
            ivp = self.plots["iv"]
            ivp.plot(ox, 100 * opt["front_iv"], pen=pg.mkPen(t["accent"], width=1.4), name=T("前月 ATM IV"), connect="finite")
            ivp.plot(ox, 100 * opt["iv30"], pen=pg.mkPen("#b48cff", width=1.4), name=T("約 30 天 ATM IV"), connect="finite")
            self.plots["skew"].plot(ox, 100 * opt["skew"], pen=pg.mkPen("#4fc1c9", width=1.4), connect="finite")
            if has_flow:
                w = res["interval"] * 0.8
                fp = self.plots["flow"]
                fp.addItem(pg.BarGraphItem(x=ox - res["interval"] / 2, height=opt["call_vol"], width=w, brush=t["bid"], pen=None))
                fp.addItem(pg.BarGraphItem(x=ox - res["interval"] / 2, height=-opt["put_vol"], width=w, brush=t["ask"], pen=None))
                pc = self.plots["pc"]
                pc.plot(ox, opt["pc_ratio"], pen=pg.mkPen(t["warn"], width=1.3), connect="finite")
                pc.addItem(pg.InfiniteLine(pos=1, angle=0, pen=pg.mkPen(t["muted"], style=Qt.DotLine)))
            notes.append("%s %s · %d %s" % (T("期權"), opt["root"], len(ox), T("個時間點")))
            if not has_flow:
                notes.append(T("期權檔沒有成交紀錄（成交量需要 trades / tcbbo / cmbp-1）"))
            elif res.get("vol_file"):
                notes.append(T("成交量來源：%s") % display_name(res["vol_file"]))
            # walls at the last grid time, from open interest if available
            if res.get("oi"):
                self._draw_walls(pp, res, t)
                notes.append(T("持倉量來源：%s") % display_name(res["oi_file"]))
        self.status.setText(" · ".join(notes) or T("此位置沒有足夠資料"))
        first.autoRange()
        self.proxy = pg.SignalProxy(self.glw.scene().sigMouseMoved, rateLimit=60, slot=self.on_mouse)

    def _draw_walls(self, pp, res, t):
        opt = res["opt"]
        spot = opt["spot"][np.isfinite(opt["spot"])]
        if not len(spot):
            return
        w = walls.walls(res["root"], oi=res["oi"], spot=float(spot[-1]), max_days=30,
                        asof=dt.datetime.fromtimestamp(opt["t"][-1], dt.timezone.utc).date())
        if w is None:
            return
        for y, col, name in ((w["call_wall"], t["bid"], T("Call 牆")), (w["put_wall"], t["ask"], T("Put 牆"))):
            if y:
                pp.addItem(pg.InfiniteLine(pos=y, angle=0, pen=pg.mkPen(col, style=Qt.DotLine, width=1.2),
                                           label="%s %g" % (name, y),
                                           labelOpts={"color": col, "position": 0.97, "anchors": [(1, 1), (1, 1)]}))

    def on_mouse(self, evt):
        if not self.plots or self.res is None:
            return
        x = self.plots["price"].vb.mapSceneToView(evt[0]).x()
        parts = [dt.datetime.fromtimestamp(x, get_tz(self.win.tsfmt.tz)).strftime("%Y-%m-%d %H:%M:%S")]
        stock, opt = self.res.get("stock"), self.res.get("opt")
        if stock:
            b = stock["bars"]
            i = int(np.clip(np.searchsorted(b["t"], x, side="right") - 1, 0, len(b["t"]) - 1))
            parts.append("%s %s  %s %s  %s %.1f%%" % (T("收盤"), _p(b["c"][i]), T("成交量"), "{:,.0f}".format(b["v"][i]),
                                                     T("實現波動率"), 100 * np.nan_to_num(stock["rv"][i])))
        if opt is not None and len(opt["t"]):
            j = int(np.clip(np.searchsorted(opt["t"], x), 0, len(opt["t"]) - 1))
            parts.append("%s %s  %s %.1f%%  30d %.1f%%  Skew %.1f  %s ±%.2f%%  P/C %s" % (
                T("隱含標的價"), _p(opt["spot"][j]), T("前月 ATM IV"), 100 * np.nan_to_num(opt["front_iv"][j]),
                100 * np.nan_to_num(opt["iv30"][j]), 100 * np.nan_to_num(opt["skew"][j]), T("預期波動"),
                100 * np.nan_to_num(opt["move"][j]), _p(opt["pc_ratio"][j])))
        self.readout.setText("   ".join(parts))


def _p(v):
    if v is None or not np.isfinite(v):
        return "—"
    return ("%.4f" % v).rstrip("0").rstrip(".")


def _mb(n):
    return "%.1f MB" % (n / 1e6)
