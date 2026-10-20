"""MBO order-book replay window (Tools menu): scrub or play back the book of an MBO day."""
import datetime as dt
import threading
import time

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from ..analysis import replay
from ..display import display_name, fmt_n
from ..engine import get_tz, parse_time
from ..i18n import T
from . import gestures
from .charts import TzAxis
from .common import blend, native_shortcuts, run_bg, theme

SPEEDS = [0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 1800]
WINDOWS = [(10, "10s"), (60, "1m"), (300, "5m"), (1800, "30m")]
TAPE_ROWS = 40
FPS = 30


def _fmt_px(p):
    return ("%.6f" % p).rstrip("0").rstrip(".") if p is not None else "—"


class LadderView(QtWidgets.QWidget):
    """Depth ladder: asks above, bids below, size bars growing away from the price column. With queues, each bar is
    split into the resting orders in queue order (first in queue next to the price); hovering shows the order."""

    ROW = 22

    def __init__(self):
        super().__init__()
        self.snap = None
        self.queues = False
        self.prev = {}
        self.flash = {}  # (side, price) -> (time, +1/-1)
        self.hits = []
        self.setMouseTracking(True)
        self.setMinimumWidth(420)
        self._fade = QtCore.QTimer(self, interval=60, timeout=self._tick)

    def set_snapshot(self, snap, queues):
        now = time.monotonic()
        cur = {}
        for side, levels in (("B", snap["bids"]), ("A", snap["asks"])):
            for p, s, _, _ in levels:
                cur[(side, p)] = s
                old = self.prev.get((side, p))
                if old is not None and old != s:
                    self.flash[(side, p)] = (now, 1 if s > old else -1)
                elif old is None and self.prev:
                    self.flash[(side, p)] = (now, 1)
        self.prev = cur
        self.snap, self.queues = snap, queues
        if self.flash and not self._fade.isActive():
            self._fade.start()
        self.update()

    def _tick(self):
        now = time.monotonic()
        self.flash = {k: v for k, v in self.flash.items() if now - v[0] < 0.8}
        if not self.flash:
            self._fade.stop()
        self.update()

    def sizeHint(self):
        return QtCore.QSize(520, 600)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        t = theme()
        p.fillRect(self.rect(), QtGui.QColor(t["bg"]))
        self.hits = []
        if not self.snap:
            return
        f = QtGui.QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        fm = QtGui.QFontMetrics(f)
        asks, bids = self.snap["asks"], self.snap["bids"]
        rows = [("A", lv) for lv in reversed(asks)] + [None] + [("B", lv) for lv in bids]
        h = self.ROW
        top = max(4, (self.height() - h * len(rows)) // 2)
        w = self.width()
        px_w = 96
        cx0 = (w - px_w) // 2
        cx1 = cx0 + px_w
        bar_room = cx0 - 70
        vmax = max([lv[1] for lv in asks + bids] + [1])
        now = time.monotonic()
        best = {("A", asks[0][0]) if asks else None, ("B", bids[0][0]) if bids else None}
        for i, row in enumerate(rows):
            y = top + i * h
            if row is None:  # spread line
                if asks and bids:
                    spread = asks[0][0] - bids[0][0]
                    mid = (asks[0][0] + bids[0][0]) / 2
                    p.setPen(QtGui.QColor(t["muted"]))
                    p.drawText(QtCore.QRect(0, y, w, h), Qt.AlignCenter,
                               "%s %s · %s %s" % (T("Spread"), _fmt_px(round(spread, 9)), T("Mid"), _fmt_px(round(mid, 9))))
                continue
            side, (price, size, count, orders) = row
            col = QtGui.QColor(t["bid"] if side == "B" else t["ask"])
            if (side, price) in best:
                p.fillRect(QtCore.QRect(0, y, w, h), QtGui.QColor(blend(col.name(), 0.10, t["bg"])))
            fl = self.flash.get((side, price))
            if fl:
                a = max(0.0, 1 - (now - fl[0]) / 0.8) * 0.35
                fcol = t["bid"] if fl[1] > 0 else t["ask"]
                p.fillRect(QtCore.QRect(cx0, y + 1, px_w, h - 2), QtGui.QColor(blend(fcol, a, t["bg"])))
            # price
            p.setPen(QtGui.QColor(t["text"]))
            p.drawText(QtCore.QRect(cx0, y, px_w, h), Qt.AlignCenter, _fmt_px(price))
            # bar
            length = max(2, int(bar_room * size / vmax))
            if side == "B":
                bar = QtCore.QRectF(cx0 - 4 - length, y + 3, length, h - 6)
            else:
                bar = QtCore.QRectF(cx1 + 4, y + 3, length, h - 6)
            if self.queues and orders:
                self._queue_bar(p, bar, orders, size, side, col, t)
            else:
                p.fillRect(bar, QtGui.QColor(blend(col.name(), 0.55, t["bg"])))
            # size inside the bar near the price, count at the outer end
            p.setPen(QtGui.QColor(t["text"]))
            label = fmt_n(size)
            if side == "B":
                p.drawText(QtCore.QRectF(cx0 - 4 - max(length, fm.horizontalAdvance(label) + 8), y, max(length, fm.horizontalAdvance(label) + 8) - 4, h),
                           Qt.AlignRight | Qt.AlignVCenter, label)
                p.setPen(QtGui.QColor(t["muted"]))
                p.drawText(QtCore.QRectF(4, y, 60, h), Qt.AlignLeft | Qt.AlignVCenter, "%d" % count)
            else:
                p.drawText(QtCore.QRectF(cx1 + 8, y, max(length, fm.horizontalAdvance(label) + 8), h),
                           Qt.AlignLeft | Qt.AlignVCenter, label)
                p.setPen(QtGui.QColor(t["muted"]))
                p.drawText(QtCore.QRectF(w - 64, y, 60, h), Qt.AlignRight | Qt.AlignVCenter, "%d" % count)

    def _queue_bar(self, p, bar, orders, size, side, col, t):
        """Segments in queue order, first in queue next to the price column."""
        total = max(size, sum(o[1] for o in orders), 1)
        shades = [QtGui.QColor(blend(col.name(), 0.70, t["bg"])), QtGui.QColor(blend(col.name(), 0.42, t["bg"]))]
        x = bar.right() if side == "B" else bar.left()
        for k, (oid, sz) in enumerate(orders):
            wseg = bar.width() * sz / total
            r = QtCore.QRectF(x - wseg, bar.top(), wseg, bar.height()) if side == "B" else \
                QtCore.QRectF(x, bar.top(), wseg, bar.height())
            p.fillRect(r, shades[k % 2])
            self.hits.append((r, k, oid, sz, len(orders)))
            x = x - wseg if side == "B" else x + wseg

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        for r, k, oid, sz, n in self.hits:
            if r.contains(pos):
                QtWidgets.QToolTip.showText(ev.globalPosition().toPoint(), T("Queue position %d of %d · order %s · size %s")
                                            % (k + 1, n, oid, fmt_n(sz)), self)
                return
        QtWidgets.QToolTip.hideText()


class ReplayWindow(QtWidgets.QMainWindow):
    def __init__(self, win, path, iid=None, start_ts=None):
        super().__init__(win)
        self.win, self.path, self.iid, self.start_ts = win, path, iid, start_ts
        self.r = None
        self.snap = None
        self.t = None
        self.playing = False
        self._last = None
        self._tape_at = 0
        self._cache = None  # (t0, t1, bbo, trades) for the chart
        self._cancel = threading.Event()
        self._progress = {}
        self.setWindowTitle("%s · %s" % (T("MBO Order Book Replay"), display_name(path)))
        self.resize(1450, 900)
        self._build_ui()
        self._prepare()

    # ---- UI ------------------------------------------------------------------------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        bar = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel()
        self.title.setStyleSheet("font-weight:600")
        bar.addWidget(self.title)
        bar.addSpacing(12)

        def button(text, tip, fn):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setToolTip(native_shortcuts(tip))
            b.clicked.connect(fn)
            bar.addWidget(b)
            return b
        button("⏮", T("Start of the day"), lambda: self.seek(self.r.t0))
        button("◀▏", T("Previous event (⇧←)"), lambda: self.step_event(-1))
        button("◀ 1s", T("Back 1 second (←)"), lambda: self.seek(self.t - 1_000_000_000))
        self.play_btn = button("▶", T("Play / pause (Space)"), self.toggle_play)
        self.play_btn.setMinimumWidth(36)
        button("1s ▶", T("Forward 1 second (→)"), lambda: self.seek(self.t + 1_000_000_000))
        button("▕▶", T("Next event (⇧→)"), lambda: self.step_event(1))
        bar.addSpacing(8)
        bar.addWidget(QtWidgets.QLabel(T("Speed")))
        self.speed = QtWidgets.QComboBox()
        for s in SPEEDS:
            self.speed.addItem(("%g×" % s), s)
        self.speed.setCurrentIndex(SPEEDS.index(1))
        bar.addWidget(self.speed)
        bar.addSpacing(8)
        self.time_edit = QtWidgets.QLineEdit()
        self.time_edit.setPlaceholderText(T("Jump to, e.g. 10:30 or 10:30:15.250"))
        self.time_edit.setMaximumWidth(230)
        self.time_edit.returnPressed.connect(self.jump)
        bar.addWidget(self.time_edit)
        bar.addSpacing(8)
        bar.addWidget(QtWidgets.QLabel(T("Depth")))
        self.depth = QtWidgets.QSpinBox()
        self.depth.setRange(1, 50)
        self.depth.setValue(int(self.win.settings.value("replay/depth", 15)))
        self.depth.valueChanged.connect(lambda v: (self.win.settings.setValue("replay/depth", v), self.refresh()))
        bar.addWidget(self.depth)
        self.queues = QtWidgets.QCheckBox(T("Show queues (L3)"))
        self.queues.setChecked(self.win.settings.value("replay/queues", "false") == "true")
        self.queues.toggled.connect(lambda v: (self.win.settings.setValue("replay/queues", "true" if v else "false"),
                                               self.refresh()))
        bar.addWidget(self.queues)
        bar.addStretch()
        lay.addLayout(bar)

        srow = QtWidgets.QHBoxLayout()
        self.t0_label = QtWidgets.QLabel()
        self.t1_label = QtWidgets.QLabel()
        for lab in (self.t0_label, self.t1_label):
            lab.setStyleSheet("color:gray")
        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.seek(self.r.t0 + v * 1_000_000))
        self.slider.sliderPressed.connect(lambda: self.seek(self.r.t0 + self.slider.value() * 1_000_000))
        srow.addWidget(self.t0_label)
        srow.addWidget(self.slider, 1)
        srow.addWidget(self.t1_label)
        lay.addLayout(srow)

        split = QtWidgets.QSplitter(Qt.Horizontal)
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.clock = QtWidgets.QLabel()
        self.clock.setAlignment(Qt.AlignCenter)
        self.clock.setStyleSheet("font-size:18px; font-weight:600")
        ll.addWidget(self.clock)
        self.ladder = LadderView()
        ll.addWidget(self.ladder, 1)
        split.addWidget(left)

        right = QtWidgets.QSplitter(Qt.Vertical)
        chart_box = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(chart_box)
        cl.setContentsMargins(0, 0, 0, 0)
        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(QtWidgets.QLabel(T("Window")))
        self.window_box = QtWidgets.QComboBox()
        for sec, label in WINDOWS:
            self.window_box.addItem(label, sec)
        self.window_box.setCurrentIndex(1)
        self.window_box.currentIndexChanged.connect(lambda _: (setattr(self, "_cache", None), self.update_chart()))
        crow.addWidget(self.window_box)
        hint = QtWidgets.QLabel(T("Click the chart to jump there"))
        hint.setStyleSheet("color:gray")
        crow.addWidget(hint)
        crow.addStretch()
        cl.addLayout(crow)
        self.plot = pg.PlotWidget(axisItems={"bottom": TzAxis(self.win)})
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        gestures.enable_pinch(self.plot)
        self.bid_line = self.plot.plot([], [], stepMode="left", name=T("Bid"))
        self.ask_line = self.plot.plot([], [], stepMode="left", name=T("Ask"))
        self.trade_dots = pg.ScatterPlotItem()
        self.plot.addItem(self.trade_dots)
        self.now_line = pg.InfiniteLine(angle=90, movable=False)
        self.plot.addItem(self.now_line)
        self.plot.scene().sigMouseClicked.connect(self.on_chart_click)
        cl.addWidget(self.plot, 1)
        right.addWidget(chart_box)
        self.tape = QtWidgets.QTableWidget(0, 7)
        self.tape.setHorizontalHeaderLabels([T("Receive Time"), T("Action"), T("Side"), T("Price"), T("Size"),
                                             T("Order ID"), T("Flags")])
        self.tape.verticalHeader().setVisible(False)
        self.tape.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tape.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tape.horizontalHeader().setStretchLastSection(True)
        self.tape.setFont(self.win.mono)
        right.addWidget(self.tape)
        right.setSizes([520, 330])
        split.addWidget(right)
        split.setSizes([560, 890])
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self.status = QtWidgets.QLabel()
        self.statusBar().addWidget(self.status, 1)

        self.timer = QtCore.QTimer(self, interval=int(1000 / FPS), timeout=self._frame)
        for key, fn in ((Qt.Key_Space, self.toggle_play), (Qt.Key_Left, lambda: self.seek(self.t - 1_000_000_000)),
                        (Qt.Key_Right, lambda: self.seek(self.t + 1_000_000_000)),
                        (QtGui.QKeySequence(Qt.SHIFT | Qt.Key_Left), lambda: self.step_event(-1)),
                        (QtGui.QKeySequence(Qt.SHIFT | Qt.Key_Right), lambda: self.step_event(1))):
            sc = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(lambda fn=fn: self.r is not None and fn())
        self._set_enabled(False)

    def _set_enabled(self, on):
        for w in self.findChildren(QtWidgets.QAbstractButton) + [self.slider, self.time_edit, self.speed, self.depth,
                                                                self.window_box]:
            w.setEnabled(on)

    # ---- opening -------------------------------------------------------------------------
    def _prepare(self):
        self.status.setText(T("Preparing the replay…"))
        prog = self._progress

        def progress(stage, done, total):
            prog.update(stage=stage, done=done, total=total)

        poll = QtCore.QTimer(self, interval=300)

        def show():
            st = prog.get("stage")
            if st == "download":
                self.status.setText(T("Downloading the file for indexing… %.0f%%") % (100.0 * prog["done"] / max(prog["total"], 1)))
            elif st == "index":
                self.status.setText(T("Indexing the day for replay (first time only)…") if not prog.get("total") else
                                    T("Replaying the loaded rows… %.0f%%") % (100.0 * prog["done"] / max(prog["total"], 1)))
        poll.timeout.connect(show)
        poll.start()

        def done(res):
            poll.stop()
            self.r, note = res
            self._ready(note)

        def fail(e):
            poll.stop()
            self.status.setText(T("Cannot replay this file: %s") % e)

        run_bg(lambda: replay.open_replay(self.path, self.win.job, self.iid, self._symbol(), progress,
                                          self._cancel.is_set), done=done, fail=fail)

    def _symbol(self):
        fi = getattr(self.win, "fi", None)
        if fi is None:
            return ""
        syms = fi.md.get("symbols") or []
        return syms[0] if len(syms) == 1 else ""

    def _ready(self, note):
        r = self.r
        sym = r.symbol or self._symbol()
        self.title.setText("%s · %s" % (sym or display_name(self.path), r.dataset))
        self.slider.setRange(0, int((r.t1 - r.t0) // 1_000_000))
        self.t0_label.setText(self.win.tsfmt.fmt(r.t0, "t")[:12])
        self.t1_label.setText(self.win.tsfmt.fmt(r.t1, "t")[:12])
        self.backend = (T("LOB-WASR (exact L3)") if r.exact_queues else
                        T("Loaded rows only (approximate queues)")) + (" · " + note if note else "")
        self._set_enabled(True)
        self.seek(self.start_ts if self.start_ts is not None else self._default_start())

    def _default_start(self):
        """09:30 New York for Nasdaq days when it lies inside the file, else the first event."""
        r = self.r
        if r.dataset.startswith("XNAS") or r.dataset.startswith("EQUS"):
            ny = get_tz("America/New_York")
            d = dt.datetime.fromtimestamp(r.t0 / 1e9, ny).date()
            t = int(dt.datetime.combine(d, dt.time(9, 30), ny).timestamp()) * 1_000_000_000
            if r.t0 <= t <= r.t1:
                return t
        return r.t0

    # ---- navigation ----------------------------------------------------------------------
    def seek(self, ts):
        if self.r is None:
            return
        ts = min(max(int(ts), self.r.t0), self.r.t1)
        self.t = ts
        self.snap = self.r.seek(ts, self.depth.value(), self.queues.isChecked())
        self.render()

    def step_event(self, d):
        if self.r is None or self.snap is None:
            return
        self.pause()
        self.snap = self.r.seek_pos(self.snap["pos"] + d, self.depth.value(), self.queues.isChecked())
        self.t = self.snap["ts"]
        self.render()

    def refresh(self):
        if self.r is not None and self.snap is not None:
            self.snap = self.r.seek_pos(self.snap["pos"], self.depth.value(), self.queues.isChecked())
            self.render()

    def jump(self):
        if self.r is None:
            return
        ts = parse_time(self.time_edit.text(), self.win.tsfmt.tz, self.t or self.r.t0)
        if ts is None:
            return
        self.pause()
        self.seek(ts)

    def on_chart_click(self, ev):
        if self.r is None or ev.button() != Qt.LeftButton:
            return
        vb = self.plot.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(ev.scenePos()):
            return
        x = vb.mapSceneToView(ev.scenePos()).x()
        self.pause()
        self.seek(int(x * 1e9))

    def toggle_play(self):
        self.pause() if self.playing else self.play()

    def play(self):
        if self.r is None:
            return
        if self.t >= self.r.t1:
            self.seek(self.r.t0)
        self.playing = True
        self.play_btn.setText("❚❚")
        self._last = time.perf_counter()
        self.timer.start()

    def pause(self):
        self.playing = False
        self.play_btn.setText("▶")
        self.timer.stop()

    def _frame(self):
        now = time.perf_counter()
        dt_wall, self._last = now - self._last, now
        t = self.t + int(dt_wall * self.speed.currentData() * 1e9)
        if t >= self.r.t1:
            t = self.r.t1
            self.pause()
        self.seek(t)

    # ---- drawing -------------------------------------------------------------------------
    def render(self):
        s, r = self.snap, self.r
        self.ladder.set_snapshot(s, self.queues.isChecked())
        self.clock.setText("%s  %s" % (self.win.tsfmt.fmt(self.t, "t")[:15], self.win.tsfmt.tz_short))
        self.slider.blockSignals(True)
        self.slider.setValue(int((self.t - r.t0) // 1_000_000))
        self.slider.blockSignals(False)
        self.update_chart()
        if not self.playing or time.perf_counter() - self._tape_at > 0.1:
            self.update_tape()
        self.status.setText(T("Event %s / %s · %s resting orders · seek %.2f ms · %s") % (
            fmt_n(s["pos"]), fmt_n(r.n_events), fmt_n(s["n_orders"]), s["ms"], self.backend))

    def update_chart(self):
        if self.r is None or self.t is None:
            return
        w = self.window_box.currentData() * 1_000_000_000
        a, b = self.t - int(w * 0.8), self.t + int(w * 0.2)
        c = self._cache
        if c is None or a < c[0] or b > c[1]:
            c0, c1 = self.t - 2 * w, self.t + 2 * w
            c = self._cache = (c0, c1, self.r.bbo(c0, c1), self.r.trades(c0, c1))
        t = theme()
        self.plot.setBackground(t["bg"])
        bbo, tr = c[2], c[3]
        self.bid_line.setData(bbo["t"], bbo["bid"], stepMode="left", pen=pg.mkPen(t["bid"], width=1.4), connect="finite")
        self.ask_line.setData(bbo["t"], bbo["ask"], stepMode="left", pen=pg.mkPen(t["ask"], width=1.4), connect="finite")
        if len(tr["t"]):
            sizes = 4 + 10 * np.sqrt(tr["size"] / max(1.0, float(np.percentile(tr["size"], 95))))
            brushes = [pg.mkBrush(t["bid"] if s == b"B" else t["ask"] if s == b"A" else t["muted"]) for s in tr["side"]]
            self.trade_dots.setData(tr["t"], tr["px"], size=np.minimum(sizes, 16), brush=brushes, pen=None)
        else:
            self.trade_dots.setData([], [])
        self.now_line.setPen(pg.mkPen(t["warn"], width=1.2))
        self.now_line.setValue(self.t / 1e9)
        self.plot.setXRange(a / 1e9, b / 1e9, padding=0)
        m = (bbo["t"] >= a / 1e9) & (bbo["t"] <= b / 1e9)
        ys = np.concatenate([bbo["bid"][m], bbo["ask"][m], tr["px"][(tr["t"] >= a / 1e9) & (tr["t"] <= b / 1e9)]])
        if self.snap and self.snap["bids"]:
            ys = np.append(ys, self.snap["bids"][0][0])
        if self.snap and self.snap["asks"]:
            ys = np.append(ys, self.snap["asks"][0][0])
        ys = ys[np.isfinite(ys)]
        if len(ys):
            lo, hi = float(ys.min()), float(ys.max())
            pad = max((hi - lo) * 0.15, 1e-6 if hi > lo else abs(hi) * 1e-4 + 1e-4)
            self.plot.setYRange(lo - pad, hi + pad, padding=0)

    def update_tape(self):
        self._tape_at = time.perf_counter()
        ev = self.r.events(self.snap["pos"], TAPE_ROWS)
        t = theme()
        self.tape.setRowCount(len(ev))
        n = len(ev)
        for i in range(n):
            e = ev[n - 1 - i]  # newest first
            side = e["side"].decode()
            vals = [self.win.tsfmt.fmt(int(e["ts_recv"]), "t")[:18], e["action"].decode(), side,
                    _fmt_px(None if int(e["price"]) == replay.UNDEF_PRICE else int(e["price"]) / replay.PRICE_SCALE),
                    fmt_n(int(e["size"])), str(int(e["order_id"])), "0x%02x" % int(e["flags"])]
            for j, v in enumerate(vals):
                it = self.tape.item(i, j)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tape.setItem(i, j, it)
                it.setText(v)
                it.setForeground(QtGui.QColor(t["bid"] if side == "B" and j == 2 else t["ask"] if side == "A" and j == 2
                                              else t["text"] if i == 0 else t["muted"]))
        self.tape.resizeColumnsToContents()

    def closeEvent(self, ev):
        self.pause()
        self._cancel.set()
        super().closeEvent(ev)
