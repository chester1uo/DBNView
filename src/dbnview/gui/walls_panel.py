"""Option walls tab: open interest / volume / gamma exposure by strike, with call/put walls and the gamma flip."""
import os

import numpy as np
import pyqtgraph as pg
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt

from ..analysis import options, walls
from ..display import display_name
from ..engine import parse_time
from ..i18n import T
from . import gestures

METRICS = [("gex", "Gamma Exposure"), ("oi", "Open Interest"), ("vol", "Volume")]
RANGES = [(None, "All Expiries"), (0, "Same Day (0DTE)"), (7, "Within 7 Days"), (30, "Within 30 Days"),
          (90, "Within 90 Days")]


def _fmt_big(v):
    if v is None or not np.isfinite(v):
        return "—"
    a = abs(v)
    for unit, n in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if a >= n:
            return "%.2f%s" % (v / n, unit)
    return "%.0f" % v


class BigAxis(pg.AxisItem):
    """Axis labels in K / M / B instead of scientific notation."""

    def tickStrings(self, values, scale, spacing):
        return [_fmt_big(v) for v in values]


class WallsPanel(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.oi_path = None
        self.oi = None
        self.result = None
        self._oi_cache = {}
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        bar1, bar2 = QtWidgets.QHBoxLayout(), QtWidgets.QHBoxLayout()
        self.root = QtWidgets.QComboBox()
        self.time_edit = QtWidgets.QLineEdit()
        self.time_edit.setPlaceholderText("15:59")
        self.time_edit.setMinimumWidth(150)
        self.time_edit.returnPressed.connect(self.compute)
        self.spot = QtWidgets.QLineEdit()
        self.spot.setPlaceholderText(T("Auto (Parity)"))
        self.spot.setMaximumWidth(110)
        go = QtWidgets.QPushButton(T("Compute"))
        go.clicked.connect(self.compute)
        self.oi_label = QtWidgets.QLabel()
        self.oi_label.setStyleSheet("color:gray")
        oi_btn = QtWidgets.QPushButton(T("Load Open Interest…"))
        oi_btn.setToolTip(T("Pick the OPRA statistics file for the same trading day (open interest, stat_type 9)"))
        oi_btn.clicked.connect(self.choose_oi)
        for label, w in ((T("Underlying"), self.root), (T("Time"), self.time_edit), (T("Underlying Price"), self.spot)):
            bar1.addWidget(QtWidgets.QLabel(label))
            bar1.addWidget(w)
        bar1.addWidget(go)
        bar1.addWidget(oi_btn)
        bar1.addWidget(self.oi_label, 1)

        self.metric_box = QtWidgets.QComboBox()
        for k, label in METRICS:
            self.metric_box.addItem(T(label), k)
        self.metric_box.currentIndexChanged.connect(lambda _: self.draw())
        self.range = QtWidgets.QComboBox()
        for v, label in RANGES:
            self.range.addItem(T(label), v)
        self.range.setCurrentIndex(3)
        self.range.currentIndexChanged.connect(lambda _: self.recompute_walls())
        self.width_pct = QtWidgets.QSpinBox()
        self.width_pct.setRange(1, 100)
        self.width_pct.setValue(8)
        self.width_pct.setSuffix(" %")
        self.width_pct.valueChanged.connect(lambda _: self.draw())
        for label, w in ((T("Metric"), self.metric_box), (T("Expiries"), self.range),
                         (T("Strike Range ±"), self.width_pct)):
            bar2.addWidget(QtWidgets.QLabel(label))
            bar2.addWidget(w)
        bar2.addStretch()
        lay.addLayout(bar1)
        lay.addLayout(bar2)

        self.note = QtWidgets.QLabel(T("Open a file with option quotes, load the same day's open interest "
                                       "(statistics), then click Compute."))
        self.note.setStyleSheet("color:gray")
        self.note.setWordWrap(True)
        self.levels = QtWidgets.QLabel(" ")
        self.levels.setFont(win.mono)
        self.levels.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.note)
        lay.addWidget(self.levels)

        split = QtWidgets.QSplitter(Qt.Horizontal)
        self.bars = pg.PlotWidget(axisItems={"bottom": BigAxis(orientation="bottom")})
        self.profile = pg.PlotWidget(axisItems={"left": BigAxis(orientation="left")})
        for p in (self.bars, self.profile):
            p.showGrid(x=True, y=True, alpha=0.15)
            for ax in ("left", "bottom"):
                p.getAxis(ax).enableAutoSIPrefix(False)
            gestures.enable_pinch(p)
        self.bars.setLabel("left", T("Strike"))
        self.profile.setLabel("bottom", T("Underlying Price"))
        self.profile.setLabel("left", T("Total Gamma Exposure (per 1% Move)"))
        self.readout = QtWidgets.QLabel(" ")
        self.readout.setFont(win.mono)
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.readout)
        ll.addWidget(self.bars, 1)
        split.addWidget(left)
        split.addWidget(self.profile)
        split.setSizes([900, 450])
        lay.addWidget(split, 1)
        self.proxy = pg.SignalProxy(self.bars.scene().sigMouseMoved, rateLimit=60, slot=self.on_mouse)

    # ---- data sources ----------------------------------------------------------------
    def prepare(self):
        """After a scan: list option roots and look for a statistics file next to the open file."""
        job = self.win.job
        self.root.clear()
        self.result = None
        if job is None:
            return
        ch = options.chain(job) if options.is_option_data(job) else {}
        for r in options.roots(ch):
            self.root.addItem(r)
        if "StatMsg" in job.rts:  # the open file itself carries open interest
            self.set_oi_path(job.fi.path)
        elif self.oi_path is None:
            found = walls.find_statistics_file(job.fi.path)
            if found:
                self.set_oi_path(found)
        self._update_oi_label()

    def set_oi_path(self, path):
        self.oi_path = path
        self.oi = self._oi_cache.get(path)
        self._update_oi_label()

    def _update_oi_label(self):
        if self.oi_path:
            self.oi_label.setText(T("Open interest: %s") % display_name(self.oi_path))
        else:
            self.oi_label.setText(T("No open interest loaded; volume only"))

    def choose_oi(self):
        start = os.path.dirname(self.win.fi.path) if self.win.fi and not self.win.fi.path.startswith("ssh://") else ""
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, T("Load Open Interest…"), start,
                                                     "DBN (*.dbn *.zst *.dbn.zst)")
        if p:
            self.set_oi_path(p)
            self.compute()

    # ---- compute ---------------------------------------------------------------------
    def compute(self):
        job = self.win.job
        if job is None:
            return
        root = self.root.currentText() or None
        if root is None:
            # statistics-only file: take the roots from the open interest itself
            if self.oi_path is None:
                self.note.setText(T("This file doesn't look like options data (no OSI option symbols found, e.g. "
                                    "SPY   260116C00690000)."))
                return
        st = self.win.status or {}
        text = self.time_edit.text().strip()
        try:
            t_ns = parse_time(text, self.win.tsfmt.tz, int(st["tmin"])) if text else (int(st["tmax"]) if st.get("tmax") else None)
        except Exception as e:  # noqa: BLE001
            self.note.setText(T("Invalid time format: %s") % e)
            return
        spot = float(self.spot.text()) if self.spot.text().strip() else None
        oi_path, cache = self.oi_path, self._oi_cache
        self.note.setText(T("Computing…"))

        def work():
            oi = cache.get(oi_path) if oi_path else None
            if oi_path and oi is None:
                oi = walls.load_open_interest(oi_path)
                cache[oi_path] = oi
            r = root or (sorted({k[0] for k in oi})[0] if oi else None)
            s = None
            if r and options.is_option_data(job) and t_ns:
                s = options.surface(job, t_ns, r, side="otm", max_spread=0.5, min_days=0, max_age_s=3600)
            vol = walls.volume_by_contract(job) if options.is_option_data(job) else {}
            return r, s, oi, vol

        def done(res):
            r, s, oi, vol = res
            self.inputs = (r, s, oi, vol, spot)
            self.recompute_walls()

        self.win.run_bg(work, done=done, fail=lambda e: self.note.setText(e))

    def recompute_walls(self):
        if not getattr(self, "inputs", None):
            return
        r, s, oi, vol, spot = self.inputs
        w = walls.walls(r, surface=s, oi=oi, vol=vol, spot=spot, max_days=self.range.currentData())
        self.result = w
        if w is None:
            self.note.setText(T("Not enough data here"))
            self.bars.clear()
            self.profile.clear()
            return
        parts = ["%s · %d %s" % (r, len(w["strike"]), T("strikes"))]
        if not w["has_oi"]:
            parts.append(T("No open interest: showing volume; gamma exposure needs open interest"))
        if s is None:
            parts.append(T("No quotes: implied volatility and gamma unavailable"))
        self.note.setText(" · ".join(parts))
        lv = []
        if w["spot"]:
            lv.append("%s %.2f" % (T("Underlying Price"), w["spot"]))
        if w["call_wall"]:
            lv.append("%s %g" % (T("Call Wall"), w["call_wall"]))
        if w["put_wall"]:
            lv.append("%s %g" % (T("Put Wall"), w["put_wall"]))
        if w["zero_gamma"]:
            lv.append("%s %.2f" % (T("Gamma Flip"), w["zero_gamma"]))
        if w["total_gex"] is not None:
            lv.append("%s %s" % (T("Total Gamma Exposure"), _fmt_big(w["total_gex"])))
        if w["has_vol"]:
            lv.append("%s %s / %s" % (T("Volume Walls Call/Put"), _fmt_g(w["vol_call_wall"]),
                                      _fmt_g(w["vol_put_wall"])))
        self.levels.setText("   ".join(lv))
        if self.metric_box.currentData() == "gex" and not w["has_gex"]:
            self.metric_box.setCurrentIndex(1 if w["has_oi"] else 2)
        self.draw()

    # ---- drawing ---------------------------------------------------------------------
    def draw(self):
        w = self.result
        if w is None:
            return
        t = self.win.colors
        for p in (self.bars, self.profile):
            p.clear()
            p.setBackground(t["bg"])
        metric = self.metric_box.currentData()
        k = w["strike"]
        if metric == "gex":
            call, put, label = w["call_gex"], w["put_gex"], T("Gamma Exposure (per 1% Move)")
        elif metric == "oi":
            call, put, label = w["call_oi"], -w["put_oi"], T("Open Interest (Puts to the Left)")
        else:
            call, put, label = w["call_vol"], -w["put_vol"], T("Volume (Puts to the Left)")
        spot = w["spot"]
        if spot:
            keep = np.abs(k - spot) <= spot * self.width_pct.value() / 100.0
        else:
            keep = np.ones(len(k), bool)
        k, call, put = k[keep], call[keep], put[keep]
        if not len(k):
            return
        h = max(float(np.min(np.diff(k))) * 0.8 if len(k) > 1 else 1.0, 1e-6)
        self.bars.addItem(pg.BarGraphItem(x0=0, y=k, width=call, height=h, brush=t["bid"], pen=None))
        self.bars.addItem(pg.BarGraphItem(x0=0, y=k, width=put, height=h, brush=t["ask"], pen=None))
        if metric == "gex":
            net = (call + put)
            self.bars.plot(net, k, pen=pg.mkPen(t["text"], width=1.2), symbol="o", symbolSize=3,
                           symbolBrush=t["text"], symbolPen=None, name=T("Net Gamma"))
        self.bars.setLabel("bottom", label)
        self.bars.addItem(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(t["muted"])))
        marks = [(spot, t["accent"], T("Underlying Price")), (w["call_wall"], t["bid"], T("Call Wall")),
                 (w["put_wall"], t["ask"], T("Put Wall")), (w["zero_gamma"], t["warn"], T("Gamma Flip"))]
        for y, col, name in marks:
            if y:
                self.bars.addItem(pg.InfiniteLine(pos=y, angle=0, pen=pg.mkPen(col, style=Qt.DashLine, width=1.2),
                                                  label="%s %s" % (name, _fmt_g(y)),
                                                  labelOpts={"color": col, "position": 0.92, "anchors": [(1, 1), (1, 1)]}))
        self.bars.autoRange()
        if w["profile_spot"] is not None:
            xs, ys = w["profile_spot"], w["profile_gex"]
            self.profile.plot(xs, ys, pen=pg.mkPen(t["accent"], width=1.6), fillLevel=0,
                              brush=pg.mkBrush(QtGui.QColor(t["accent"]).lighter(160)))
            self.profile.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(t["muted"])))
            for (x, col, name), pos in zip(marks[:1] + marks[3:], (0.95, 0.85)):
                if x:
                    self.profile.addItem(pg.InfiniteLine(pos=x, angle=90, pen=pg.mkPen(col, style=Qt.DashLine),
                                                         label="%s %.2f" % (name, x),
                                                         labelOpts={"color": col, "position": pos}))
            self.profile.setTitle(T("Gamma Exposure vs. Underlying Price (Fixed IV)"))
        else:
            self.profile.setTitle(T("The gamma curve needs quotes and open interest"))

    def on_mouse(self, evt):
        w = self.result
        if w is None or not self.bars.sceneBoundingRect().contains(evt[0]):
            return
        y = self.bars.plotItem.vb.mapSceneToView(evt[0]).y()
        i = int(np.argmin(np.abs(w["strike"] - y)))
        self.readout.setText("%s %g   Call OI %s   Put OI %s   Call %s %s   Put %s %s   %s %s" % (
            T("Strike"), w["strike"][i], _fmt_big(w["call_oi"][i]), _fmt_big(w["put_oi"][i]),
            T("Volume"), _fmt_big(w["call_vol"][i]), T("Volume"), _fmt_big(w["put_vol"][i]),
            T("Net Gamma"), _fmt_big(w["net_gex"][i])))


def _fmt_g(v):
    return "—" if v is None else "%g" % v
