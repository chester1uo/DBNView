"""Chart tab: K-line, quotes, order flow, order-book heatmap and a plain price line."""
import datetime as dt

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

import json

from ..analysis import indicators as ind
from ..analysis import market
from ..display import pretty_field
from ..engine import get_tz
from ..i18n import T
from . import gestures

MODES = [("kline", "K 線"), ("quotes", "報價"), ("flow", "訂單流"), ("heatmap", "訂單簿熱圖"), ("line", "價格線")]
INTERVAL_CHOICES = [(None, "自動"), (1, "1s"), (5, "5s"), (15, "15s"), (30, "30s"), (60, "1m"), (300, "5m"),
                    (900, "15m"), (1800, "30m"), (3600, "1h"), (14400, "4h"), (86400, "1D"), (604800, "1W")]
SOURCES = [("auto", "自動"), ("trades", "成交"), ("mid", "報價 mid")]


def fmt_iv(s):
    for v, label in INTERVAL_CHOICES:
        if v == s:
            return label
    return "%ss" % s


class TzAxis(pg.AxisItem):
    def __init__(self, win, **kw):
        super().__init__(orientation="bottom", **kw)
        self.win = win

    def tickStrings(self, values, scale, spacing):
        tz = get_tz(self.win.tsfmt.tz)
        out = []
        for v in values:
            try:
                d = dt.datetime.fromtimestamp(v, tz)
            except (OverflowError, OSError, ValueError):
                out.append("")
                continue
            out.append(d.strftime("%m-%d" if spacing >= 86400 else "%H:%M" if spacing >= 60 else
                                  "%H:%M:%S" if spacing >= 1 else "%H:%M:%S.%f")[:12 if spacing < 1 else None])
        return out


def add_candles(plot, x, o, h, lo, c, width, up, down):
    """Wicks as line pairs + bodies as bars (robust at any zoom level)."""
    ok = np.isfinite(o) & np.isfinite(c) & np.isfinite(h) & np.isfinite(lo)
    x, o, h, lo, c = x[ok], o[ok], h[ok], lo[ok], c[ok]
    rising = c >= o
    for mask, col in ((rising, up), (~rising, down)):
        if not mask.any():
            continue
        xs = np.repeat(x[mask], 2)
        ys = np.column_stack([lo[mask], h[mask]]).ravel()
        plot.plot(xs, ys, connect="pairs", pen=pg.mkPen(col, width=1))
        body_lo = np.minimum(o[mask], c[mask])
        body_h = np.abs(c[mask] - o[mask])
        tiny = (np.nanmax(h) - np.nanmin(lo)) * 0.002 if len(h) else 0
        plot.addItem(pg.BarGraphItem(x=x[mask], y0=body_lo, height=np.maximum(body_h, tiny), width=width,
                                     brush=pg.mkBrush(col), pen=pg.mkPen(col, width=1)))


class ChartPanel(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.data = None
        self.readout_fn = None
        self.pending_iid = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        bar = QtWidgets.QHBoxLayout()
        self.inst = QtWidgets.QComboBox()
        self.inst.setMinimumWidth(300)
        self.inst.setFont(win.mono)
        self.inst.activated.connect(lambda _: (self.iid.clear(), self.on_instrument()))
        self.iid = QtWidgets.QLineEdit()
        self.iid.setPlaceholderText(T("或輸入 instrument_id"))
        self.iid.setMaximumWidth(170)
        self.iid.returnPressed.connect(self.on_instrument)
        self.mode = QtWidgets.QComboBox()
        for k, label in MODES:
            self.mode.addItem(T(label), k)
        self.user_mode = None
        self.mode.activated.connect(lambda _: (setattr(self, "user_mode", self.mode.currentData()), self.draw()))
        self.ivbox = QtWidgets.QComboBox()
        for v, label in INTERVAL_CHOICES:
            self.ivbox.addItem(T(label), v)
        self.ivbox.activated.connect(lambda _: self.draw())
        self.src = QtWidgets.QComboBox()
        for k, label in SOURCES:
            self.src.addItem(T(label), k)
        self.src.activated.connect(lambda _: self.draw())
        btn = QtWidgets.QPushButton(T("畫圖"))
        btn.clicked.connect(self.draw)
        self.src_label = QtWidgets.QLabel(T("來源"))
        self.ind_btn = QtWidgets.QToolButton()
        self.ind_btn.setText(T("技術指標"))
        self.ind_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.ind_menu = QtWidgets.QMenu(self)
        self.ind_menu.aboutToShow.connect(self.fill_ind_menu)
        self.ind_btn.setMenu(self.ind_menu)
        settings = win.settings
        self.active_inds = [k for k in json.loads(settings.value("indicators", '["sma", "sma2"]')) if k in ind.INDICATORS]
        self.ind_params = {k: v for k, v in json.loads(settings.value("indicator_params", "{}")).items()
                           if k in ind.INDICATORS}
        for w in (self.inst, self.iid, QtWidgets.QLabel(T("圖型")), self.mode, QtWidgets.QLabel(T("週期")), self.ivbox,
                  self.src_label, self.src, self.ind_btn, btn):
            bar.addWidget(w)
        bar.addStretch()
        lay.addLayout(bar)
        self.note = QtWidgets.QLabel("")
        self.note.setStyleSheet("color:gray")
        self.readout = QtWidgets.QLabel(" ")
        self.readout.setFont(win.mono)
        self.readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.note)
        lay.addWidget(self.readout)
        pg.setConfigOptions(antialias=True)
        self.glw = pg.GraphicsLayoutWidget()
        gestures.enable_pinch(self.glw)
        lay.addWidget(self.glw, 1)
        self.proxy = None
        self.main = None

    # ---- instrument list -------------------------------------------------
    def fill_inst(self):
        st = self.win.stats
        if not st:
            return
        cur = self.inst.currentData()
        self.inst.clear()
        for iid, c, sym in st["top"][:200]:
            self.inst.addItem("%s  #%d  (%s)" % (sym or "", iid, "{:,}".format(c)), iid)
        if cur is not None and self.inst.findData(cur) >= 0:
            self.inst.setCurrentIndex(self.inst.findData(cur))

    def show_iid(self, iid):
        self.iid.setText(str(iid))
        self.on_instrument()

    def current_iid(self):
        t = self.iid.text().strip()
        if t.isdigit():
            return int(t)
        return self.inst.currentData()

    def on_instrument(self):
        """New instrument: pick the most useful default chart for its record type."""
        job, iid = self.win.job, self.current_iid()
        if job is None or iid is None:
            return
        caps, cls = market.capabilities(job, iid)
        model = self.mode.model()
        for i in range(self.mode.count()):
            k = self.mode.itemData(i)
            ok = k == "line" or (k in ("kline",) and "bars" in caps) or (k in caps)
            model.item(i).setEnabled(ok)
        if cls in market.BAR_CLASSES or (cls == "TradeMsg"):
            want = "kline"
        elif cls in ("MBOMsg", "MBP10Msg"):
            want = "heatmap"
        elif "quotes" in caps:
            want = "quotes"
        elif "bars" in caps:
            want = "kline"
        else:
            want = "line"
        um = self.user_mode
        if um is None or not model.item(self.mode.findData(um)).isEnabled():
            self.mode.setCurrentIndex(self.mode.findData(want))
        else:
            self.mode.setCurrentIndex(self.mode.findData(um))
        self.draw()

    # ---- technical indicators -------------------------------------------------
    def fill_ind_menu(self):
        m = self.ind_menu
        m.clear()
        for title, kind in ((T("疊加在價格圖"), "overlay"), (T("獨立副圖"), "pane")):
            m.addSection(title)
            for key, spec in ind.INDICATORS.items():
                if spec["kind"] != kind:
                    continue
                a = m.addAction(ind.label(key, self.ind_params.get(key)))
                a.setCheckable(True)
                a.setChecked(key in self.active_inds)
                a.toggled.connect(lambda on, key=key: self.toggle_indicator(key, on))
        m.addSeparator()
        m.addAction(T("指標參數…")).triggered.connect(self.edit_params)
        m.addAction(T("全部清除")).triggered.connect(lambda: self.set_indicators([]))

    def toggle_indicator(self, key, on):
        keys = [k for k in self.active_inds if k != key] + ([key] if on else [])
        self.set_indicators(keys)

    def set_indicators(self, keys):
        self.active_inds = keys
        self.win.settings.setValue("indicators", json.dumps(keys))
        if self.mode.currentData() == "kline":
            self.draw()

    def edit_params(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(T("指標參數…"))
        form = QtWidgets.QFormLayout(dlg)
        boxes = {}
        for key, spec in ind.INDICATORS.items():
            if not spec["params"]:
                continue
            row = QtWidgets.QHBoxLayout()
            cur = dict(spec["params"], **self.ind_params.get(key, {}))
            for name, default in spec["params"].items():
                if isinstance(default, float):
                    b = QtWidgets.QDoubleSpinBox()
                    b.setDecimals(2)
                    b.setRange(0.1, 10)
                    b.setSingleStep(0.5)
                else:
                    b = QtWidgets.QSpinBox()
                    b.setRange(1, 1000)
                b.setValue(cur[name])
                b.setPrefix(name + " ")
                boxes[(key, name)] = b
                row.addWidget(b)
            form.addRow("%s%s" % (spec["name"], " (2)" if key == "sma2" else ""), row)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec():
            params = {}
            for (key, name), b in boxes.items():
                params.setdefault(key, {})[name] = b.value()
            self.ind_params = params
            self.win.settings.setValue("indicator_params", json.dumps(params))
            if self.mode.currentData() == "kline":
                self.draw()

    def ind_color(self, role):
        t = self.colors()
        return {"accent": t["accent"], "warn": t["warn"], "muted": t["muted"], "teal": "#4fc1c9",
                "violet": "#b48cff"}.get(role, t["accent"])

    def draw_indicators(self, bars, x, panes):
        """Overlays on the price pane; each oscillator in one of `panes`. Returns [(label, values)] for the readout."""
        readout = []
        legend = self.main.addLegend(offset=(10, 10)) if any(
            ind.INDICATORS[k]["kind"] == "overlay" for k in self.active_inds) else None
        pane_iter = iter(panes)
        for key in self.active_inds:
            spec = ind.INDICATORS[key]
            params = self.ind_params.get(key)
            out = ind.compute(key, bars, params)
            name = ind.label(key, params)
            if spec["kind"] == "overlay":
                fill = None
                for (line_name, role), y in zip(spec["lines"], out):
                    item = self.main.plot(x, y, pen=pg.mkPen(self.ind_color(role), width=1.3), connect="finite",
                                          name=name if line_name == spec["lines"][0][0] else None)
                    if key == "boll" and line_name in ("Upper", "Lower"):
                        fill = (fill or []) + [item]
                    readout.append((name if len(out) == 1 else "%s %s" % (spec["name"], line_name), y))
                if fill and len(fill) == 2:
                    band = QtGui.QColor("#4fc1c9")
                    band.setAlpha(28)
                    self.main.addItem(pg.FillBetweenItem(fill[0], fill[1], brush=pg.mkBrush(band)))
            else:
                p = next(pane_iter)
                p.setLabel("left", name)
                for (line_name, role), y in zip(spec["lines"], out):
                    if role == "hist":
                        t = self.colors()
                        brushes = [pg.mkBrush(t["bid"] if v >= 0 else t["ask"]) for v in np.nan_to_num(y)]
                        p.addItem(pg.BarGraphItem(x=x, height=np.nan_to_num(y), width=bars["interval"] * 0.7,
                                                  brushes=brushes, pen=None))
                    else:
                        p.plot(x, y, pen=pg.mkPen(self.ind_color(role), width=1.3), connect="finite")
                    readout.append((spec["name"] if line_name == spec["name"] else
                                    "%s %s" % (spec["name"], line_name), y))
                for lvl in spec.get("levels", []):
                    p.addItem(pg.InfiniteLine(pos=lvl, angle=0, pen=pg.mkPen(self.colors()["muted"], style=Qt.DotLine)))
        if legend is not None:
            legend.setBrush(pg.mkBrush(QtGui.QColor(0, 0, 0, 0)))
        return readout

    # ---- drawing ------------------------------------------------------------
    def colors(self):
        return self.win.colors

    def new_layout(self, sub_rows=0, profile=False):
        self.glw.clear()
        self.glw.setBackground(self.colors()["bg"])
        t = self.colors()
        self.main = self.glw.addPlot(row=0, col=0, axisItems={"bottom": TzAxis(self.win)})
        plots = [self.main]
        self.profile = None
        if profile:
            self.profile = self.glw.addPlot(row=0, col=1)
            self.profile.setYLink(self.main)
            self.profile.hideAxis("left")
            self.profile.setMaximumWidth(150)
            self.profile.setLabel("bottom", T("量"))
            plots.append(self.profile)
        self.subs = []
        for r in range(sub_rows):
            sp = self.glw.addPlot(row=1 + r, col=0, axisItems={"bottom": TzAxis(self.win)})
            sp.setXLink(self.main)
            sp.setMaximumHeight(170 if sub_rows <= 2 else 140)
            self.subs.append(sp)
            plots.append(sp)
        lay = self.glw.ci.layout
        lay.setRowStretchFactor(0, 4)
        for r in range(1, 1 + sub_rows):
            lay.setRowStretchFactor(r, 1)
        self.main.setMinimumHeight(260)
        if self.profile is not None:
            self.profile.getAxis("bottom").setStyle(showValues=False)
        for p in plots:
            p.showGrid(x=True, y=True, alpha=0.12)
            for ax in ("left", "bottom"):
                p.getAxis(ax).enableAutoSIPrefix(False)
            for ax in ("left", "bottom"):
                p.getAxis(ax).setPen(pg.mkPen(t["muted"]))
                p.getAxis(ax).setTextPen(pg.mkPen(t["muted"]))
            p.getAxis("left").setWidth(70)
        if sub_rows:
            self.main.getAxis("bottom").setStyle(showValues=False)
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(t["muted"], style=Qt.DashLine))
        self.main.addItem(self.vline, ignoreBounds=True)
        self.sub_vlines = []
        for sp in self.subs:
            v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(t["muted"], style=Qt.DashLine))
            sp.addItem(v, ignoreBounds=True)
            self.sub_vlines.append(v)
        self.proxy = pg.SignalProxy(self.glw.scene().sigMouseMoved, rateLimit=60, slot=self.on_mouse)
        self.readout.setText(" ")

    def on_mouse(self, evt):
        if self.main is None or self.readout_fn is None:
            return
        pos = evt[0]
        if not self.main.sceneBoundingRect().contains(pos) and not any(
                s.sceneBoundingRect().contains(pos) for s in self.subs):
            return
        x = self.main.vb.mapSceneToView(pos).x()
        y = self.main.vb.mapSceneToView(pos).y()
        self.vline.setPos(x)
        for v in self.sub_vlines:
            v.setPos(x)
        try:
            self.readout.setText(self.readout_fn(x, y))
        except Exception:  # noqa: BLE001
            pass

    def ts(self, x):
        return dt.datetime.fromtimestamp(x, get_tz(self.win.tsfmt.tz)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def draw(self):
        job, iid = self.win.job, self.current_iid()
        if job is None or iid is None:
            return
        mode = self.mode.currentData()
        iv = self.ivbox.currentData()
        src = self.src.currentData()
        self.src.setVisible(mode == "kline")
        self.src_label.setVisible(mode == "kline")
        self.ivbox.setEnabled(mode in ("kline", "flow"))
        fn = {"kline": lambda: (market.bars(job, iid, iv, src),
                                market.flow(job, iid, iv) if src != "mid" else None),
              "quotes": lambda: market.quotes(job, iid),
              "flow": lambda: market.flow(job, iid, iv),
              "heatmap": lambda: market.heatmap(job, iid),
              "line": lambda: market.price_series(job, int(iid), 8000)}[mode]
        self.note.setText(T("計算中…"))
        sym = self.win.fi.symmap.lookup(int(iid)) or ""

        def done(r):
            if job is not self.win.job:
                return
            try:
                getattr(self, "draw_" + mode)(r, sym, iid)
            except Exception as e:  # noqa: BLE001
                self.note.setText("%s: %s" % (type(e).__name__, e))

        self.win.run_bg(fn, done=done, fail=lambda e: self.note.setText(e))

    def head(self, sym, iid, extra):
        trunc = self.win.status and self.win.status.get("truncated")
        return "%s #%s · %s%s" % (sym, iid, extra, T(" · 僅已載入的列") if trunc else "")

    def empty(self, msg):
        self.glw.clear()
        self.main = None
        self.readout_fn = None
        self.note.setText(msg)

    # -- K-line --------------------------------------------------------------
    def draw_kline(self, r, sym, iid):
        bars, fl = r
        if bars is None or len(bars["t"]) == 0:
            return self.empty(T("此商品沒有可畫 K 線的資料"))
        t = self.colors()
        has_flow = bars.get("buy") is not None
        n_panes = sum(1 for k in self.active_inds if ind.INDICATORS[k]["kind"] == "pane")
        base_rows = 2 if has_flow else 1
        self.new_layout(sub_rows=base_rows + n_panes, profile=fl is not None)
        ivs = bars["interval"]
        x = bars["t"] + ivs / 2
        add_candles(self.main, x, bars["o"], bars["h"], bars["l"], bars["c"], ivs * 0.7, t["bid"], t["ask"])
        if fl is not None:
            self.main.addItem(pg.InfiniteLine(pos=fl["vwap"], angle=0, pen=pg.mkPen(t["warn"], style=Qt.DotLine),
                                              label="VWAP", labelOpts={"color": t["warn"], "position": 0.97, "anchors": [(1, 1), (1, 1)]}))
            self.draw_profile(fl)
        vol = self.subs[0]
        if has_flow:
            vol.addItem(pg.BarGraphItem(x=x, height=bars["buy"], width=ivs * 0.8, brush=t["bid"], pen=None))
            vol.addItem(pg.BarGraphItem(x=x, height=-bars["sell"], width=ivs * 0.8, brush=t["ask"], pen=None))
            vol.setLabel("left", T("買／賣量"))
            cvd = np.cumsum(bars["buy"] - bars["sell"])
            self.subs[1].plot(x, cvd, pen=pg.mkPen(t["accent"], width=1.4), stepMode=None)
            self.subs[1].setLabel("left", "CVD")
        else:
            rising = bars["c"] >= bars["o"]
            brushes = [pg.mkBrush(t["bid"] if u else t["ask"]) for u in rising]
            vol.addItem(pg.BarGraphItem(x=x, height=bars["v"], width=ivs * 0.8, brushes=brushes, pen=None))
            vol.setLabel("left", T("筆數") if bars.get("v_is_count") else T("成交量"))
        src = {"bars": T("原始 K 線"), "trades": T("由成交聚合"), "mid": T("由報價 mid 聚合")}[bars["source"]]
        self.note.setText(self.head(sym, iid, "%s · %s · %d %s" % (fmt_iv(ivs), src, len(x), T("根"))))
        cvd_all = np.cumsum(bars["buy"] - bars["sell"]) if has_flow else None
        ind_values = self.draw_indicators(bars, x, self.subs[base_rows:])
        vol_word = T("筆數") if bars.get("v_is_count") else T("成交量")

        def ro(xv, yv):
            i = int(np.clip(np.searchsorted(bars["t"], xv, side="right") - 1, 0, len(x) - 1))
            s = "%s   %s %s   %s %s   %s %s   %s %s   %s %s" % (
                self.ts(bars["t"][i]), T("開盤"), _p(bars["o"][i]), T("最高"), _p(bars["h"][i]), T("最低"),
                _p(bars["l"][i]), T("收盤"), _p(bars["c"][i]), vol_word, _n(bars["v"][i]))
            if has_flow:
                s += "   %s %s   %s %s   Delta %s   CVD %s" % (
                    T("主動買量"), _n(bars["buy"][i]), T("主動賣量"), _n(bars["sell"][i]),
                    _n(bars["buy"][i] - bars["sell"][i]), _n(cvd_all[i]))
            if ind_values:
                s += "\n" + "   ".join("%s %s" % (name, _p(round(vals[i], 4)) if np.isfinite(vals[i]) else "—")
                                       for name, vals in ind_values)
            return s
        self.readout_fn = ro
        self.main.autoRange()

    def draw_profile(self, fl):
        t = self.colors()
        y, h = fl["vp_price"], fl["vp_step"] * 0.85
        self.profile.addItem(pg.BarGraphItem(x0=0, y=y, width=fl["vp_buy"], height=h, brush=t["bid"], pen=None))
        self.profile.addItem(pg.BarGraphItem(x0=fl["vp_buy"], y=y, width=fl["vp_sell"], height=h, brush=t["ask"], pen=None))
        if fl["vp_other"].any():
            self.profile.addItem(pg.BarGraphItem(x0=fl["vp_buy"] + fl["vp_sell"], y=y, width=fl["vp_other"], height=h,
                                                 brush=t["muted"], pen=None))

    # -- quotes --------------------------------------------------------------
    def draw_quotes(self, q, sym, iid):
        if q is None or len(q["t"]) == 0:
            return self.empty(T("此商品沒有報價（bid/ask）欄位"))
        t = self.colors()
        self.new_layout(sub_rows=2)
        x = q["t"]
        xs = np.r_[x, x[-1] + max((x[-1] - x[0]) / max(len(x), 1), 1e-3)]
        bid = self.main.plot(xs, q["bid"], stepMode="center", pen=pg.mkPen(t["bid"], width=1.3), name="Bid")
        ask = self.main.plot(xs, q["ask"], stepMode="center", pen=pg.mkPen(t["ask"], width=1.3), name="Ask")
        band = QtGui.QColor(t["accent"])
        band.setAlpha(40)
        self.main.addItem(pg.FillBetweenItem(bid, ask, brush=pg.mkBrush(band)))
        self.main.plot(x, q["mid"], pen=pg.mkPen(t["muted"], width=1, style=Qt.DashLine), connect="finite")
        if q.get("trades"):
            self.add_bubbles(self.main, q["trades"])
        sp = self.subs[0]
        sp.plot(xs, q["spread"], stepMode="center", pen=pg.mkPen(t["warn"], width=1.2))
        sp.setLabel("left", "Spread")
        im = self.subs[1]
        imb = np.nan_to_num(q["imb"])
        im.plot(xs, imb, stepMode="center", fillLevel=0, brush=pg.mkBrush(_alpha(t["accent"], 70)),
                pen=pg.mkPen(t["accent"], width=1))
        im.setYRange(-1, 1)
        im.setLabel("left", T("盤口失衡"))
        self.note.setText(self.head(sym, iid, "%s %s · %s" % ("{:,}".format(q["n"]), T("筆報價"),
                                                             T("上：bid/ask 與 spread 帶；中：spread；下：(bid量−ask量)/(bid量+ask量)"))))

        def ro(xv, yv):
            i = int(np.clip(np.searchsorted(x, xv, side="right") - 1, 0, len(x) - 1))
            return "%s   Bid %s × %s   Ask %s × %s   Spread %s   %s %+.2f" % (
                self.ts(x[i]), _p(q["bid"][i]), _n(q["bid_sz"][i]), _p(q["ask"][i]), _n(q["ask_sz"][i]),
                _p(q["spread"][i]), T("失衡"), np.nan_to_num(q["imb"][i]))
        self.readout_fn = ro
        self.main.autoRange()

    def add_bubbles(self, plot, tr, max_px=22):
        t = self.colors()
        if len(tr["t"]) == 0:
            return
        sz = tr["size"]
        scale = np.sqrt(sz / max(np.percentile(sz, 99), 1e-9))
        sizes = 4 + np.clip(scale, 0, 1.6) * max_px
        cols = {b"B": pg.mkBrush(_alpha(t["bid"], 150)), b"A": pg.mkBrush(_alpha(t["ask"], 150))}
        other = pg.mkBrush(_alpha(t["muted"], 130))
        brushes = [cols.get(s, other) for s in tr["side"].tolist()]
        plot.addItem(pg.ScatterPlotItem(x=tr["t"], y=tr["price"], size=sizes, brush=brushes, pen=None))

    # -- order flow -----------------------------------------------------------
    def draw_flow(self, fl, sym, iid):
        if fl is None:
            return self.empty(T("此商品沒有成交紀錄（需要 trades / tbbo / mbp / cmbp / mbo 等含成交的資料）"))
        t = self.colors()
        self.new_layout(sub_rows=2, profile=True)
        self.add_bubbles(self.main, fl["trades"])
        self.main.addItem(pg.InfiniteLine(pos=fl["vwap"], angle=0, pen=pg.mkPen(t["warn"], style=Qt.DotLine),
                                          label="VWAP %s" % _p(fl["vwap"]), labelOpts={"color": t["warn"], "position": 0.97, "anchors": [(1, 1), (1, 1)]}))
        self.draw_profile(fl)
        iv = fl["interval"]
        x = fl["bar_t"] + iv / 2
        sp = self.subs[0]
        sp.addItem(pg.BarGraphItem(x=x, height=fl["buy"], width=iv * 0.8, brush=t["bid"], pen=None))
        sp.addItem(pg.BarGraphItem(x=x, height=-fl["sell"], width=iv * 0.8, brush=t["ask"], pen=None))
        sp.setLabel("left", T("買／賣量"))
        self.subs[1].plot(fl["cvd_t"], fl["cvd"], pen=pg.mkPen(t["accent"], width=1.4))
        self.subs[1].setLabel("left", "CVD")
        tb, ts_ = fl["trades"]["t"], fl["trades"]
        self.note.setText(self.head(sym, iid, "%s %s · VWAP %s · %s" % (
            "{:,}".format(fl["n"]), T("筆成交"), _p(fl["vwap"]),
            T("泡泡大小＝成交量，綠＝主動買、紅＝主動賣；右側為價格成交量分布"))))

        def ro(xv, yv):
            if len(tb) == 0:
                return ""
            i = int(np.clip(np.searchsorted(tb, xv), 0, len(tb) - 1))
            j = int(np.clip(np.searchsorted(fl["cvd_t"], xv, side="right") - 1, 0, len(fl["cvd"]) - 1))
            return "%s   %s %s × %s   Side %s   CVD %s" % (self.ts(tb[i]), T("成交"), _p(ts_["price"][i]),
                                                     _n(ts_["size"][i]), ts_["side"][i].decode(), _n(fl["cvd"][j]))
        self.readout_fn = ro
        self.main.autoRange()

    # -- heatmap --------------------------------------------------------------
    def draw_heatmap(self, hm, sym, iid):
        if hm is None:
            return self.empty(T("此商品沒有盤口資料可畫熱圖"))
        t = self.colors()
        self.new_layout(sub_rows=1)
        zb, za = np.log1p(hm["bid"]), np.log1p(hm["ask"])
        top = max(np.percentile(np.r_[zb[zb > 0], za[za > 0]], 99) if (zb > 0).any() or (za > 0).any() else 1, 1e-9)
        nb, na = np.clip(zb / top, 0, 1)[..., None], np.clip(za / top, 0, 1)[..., None]
        bg = np.array(QtGui.QColor(t["bg"]).getRgb()[:3], float)
        gb = np.array(QtGui.QColor(t["bid"]).getRgb()[:3], float)
        ga = np.array(QtGui.QColor(t["ask"]).getRgb()[:3], float)
        rgb = bg * (1 - np.maximum(nb, na)) + gb * nb + ga * na
        rgba = np.concatenate([np.clip(rgb, 0, 255), np.full(nb.shape, 255.0)], axis=2).astype(np.ubyte)
        img = pg.ImageItem(rgba, axisOrder="col-major")
        npb = hm["bid"].shape[1]
        img.setRect(QtCore.QRectF(hm["t0"], hm["p0"], hm["t1"] - hm["t0"], npb * hm["tick"]))
        self.main.addItem(img)
        ec = (hm["edges"][:-1] + hm["edges"][1:]) / 2
        self.main.plot(ec, hm["best_bid"], pen=pg.mkPen(t["bid"], width=1.2), connect="finite")
        self.main.plot(ec, hm["best_ask"], pen=pg.mkPen(t["ask"], width=1.2), connect="finite")
        if hm.get("trades"):
            self.add_bubbles(self.main, hm["trades"], max_px=14)
        depth_b, depth_a = hm["bid"].sum(1), hm["ask"].sum(1)
        sp = self.subs[0]
        sp.plot(ec, depth_b, pen=pg.mkPen(t["bid"], width=1.2))
        sp.plot(ec, depth_a, pen=pg.mkPen(t["ask"], width=1.2))
        sp.setLabel("left", T("可見深度"))
        how = T("由 MBO 重建（每格取樣）") if hm["cls"] == "MBOMsg" else T("取自盤口檔位")
        self.note.setText(self.head(sym, iid, "%s · tick %s · %s" % (
            how, _p(hm["tick"]), T("綠＝買方掛單量、紅＝賣方掛單量（log 色階）；線＝最優買賣價；泡泡＝成交"))))

        def ro(xv, yv):
            i = int(np.clip(np.searchsorted(hm["edges"], xv, side="right") - 1, 0, len(ec) - 1))
            k = int(np.clip(round((yv - hm["p0"]) / hm["tick"] - 0.5), 0, npb - 1))
            price = hm["p0"] + (k + 0.5) * hm["tick"]
            return "%s   %s %s   Bid %s   Ask %s   Best %s / %s" % (
                self.ts(ec[i]), T("價格"), _p(price), _n(hm["bid"][i, k]), _n(hm["ask"][i, k]),
                _p(hm["best_bid"][i]), _p(hm["best_ask"][i]))
        self.readout_fn = ro
        self.main.autoRange()

    # -- plain line -------------------------------------------------------------
    def draw_line(self, r, sym, iid):
        names = list(r["series"])
        if not r["x"] or not names:
            return self.empty(T("此商品在已載入的列中沒有價格資料"))
        t = self.colors()
        self.new_layout(sub_rows=1)
        self.main.addLegend(offset=(10, 10))
        x = np.asarray(r["x"], dtype=float)
        palette = ["#b48cff", "#e3b341", "#4fc1c9", "#f08bd0"]
        ys = {}
        for i, n in enumerate(names):
            y = np.array([np.nan if v is None else v for v in r["series"][n]], dtype=float)
            ys[n] = y
            col = t["bid"] if n.startswith("bid_px") else t["ask"] if n.startswith("ask_px") else \
                t["accent"] if n in ("price", "close") else palette[i % len(palette)]
            self.main.plot(x, y, name=pretty_field(n), pen=pg.mkPen(col, width=1.3), connect="finite",
                           symbol="o" if len(x) < 300 else None, symbolSize=4, symbolBrush=col, symbolPen=None)
        m = (self.win.stats or {}).get("minutes") or []
        if m:
            mx = np.array([a for a, _ in m], dtype=float) * 60
            my = np.array([b for _, b in m], dtype=float)
            self.subs[0].plot(np.append(mx, mx[-1] + 60), my, stepMode="center", fillLevel=0,
                              brush=pg.mkBrush(_alpha(t["accent"], 70)), pen=pg.mkPen(t["accent"], width=1))
            self.subs[0].setLabel("left", T("筆數/分"))
        self.note.setText(self.head(sym, iid, "%s %s%s" % ("{:,}".format(r["n"]), T("筆"),
                                                          T("（min/max 降採樣）") if r.get("downsampled") else "")))

        def ro(xv, yv):
            i = int(np.clip(np.searchsorted(x, xv), 0, len(x) - 1))
            return "%s   " % self.ts(x[i]) + "   ".join("%s %s" % (pretty_field(n), _p(ys[n][i])) for n in names)
        self.readout_fn = ro
        self.main.autoRange()


def _alpha(hex_color, a):
    c = QtGui.QColor(hex_color)
    c.setAlpha(a)
    return c


def _p(v):
    if v is None or not np.isfinite(v):
        return "—"
    s = "%.9f" % v
    return s.rstrip("0").rstrip(".")


def _n(v):
    if v is None or not np.isfinite(v):
        return "—"
    return "{:,.0f}".format(v) if abs(v - round(v)) < 1e-9 else "{:,.2f}".format(v)
