#!/usr/bin/env python3
"""dbnview — native desktop viewer for Databento DBN files (.dbn / .dbn.zst).

    python src/app.py [file.dbn.zst | ssh://host/path/file.dbn.zst]
"""
import collections
import csv
import datetime as dt
import html
import os
import re
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
import pyqtgraph as pg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402
import analytics  # noqa: E402,F401
import charts  # noqa: E402
import docs  # noqa: E402
import enum_values  # noqa: E402
import ivsurface  # noqa: E402
import i18n  # noqa: E402
from i18n import T  # noqa: E402

APP_NAME = "dbnview"
TZS = [("ET", "America/New_York"), ("CT", "America/Chicago"), ("UTC", "UTC"),
       ("London", "Europe/London"), ("HKT", "Asia/Hong_Kong"), ("JST", "Asia/Tokyo")]
QTY = re.compile(r"sz|size|ct_|count|qty|quantity|volume")
esc = html.escape


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
class _Sig(QtCore.QObject):
    done = QtCore.Signal(object)
    fail = QtCore.Signal(str)


class _Task(QtCore.QRunnable):
    live = set()

    def __init__(self, fn, args):
        super().__init__()
        self.fn, self.args, self.sig = fn, args, _Sig()
        self.setAutoDelete(True)

    def run(self):
        try:
            res = self.fn(*self.args)
        except Exception as e:  # noqa: BLE001
            self.sig.fail.emit("%s: %s" % (type(e).__name__, e))
        else:
            self.sig.done.emit(res)


def run_bg(fn, *args, done=None, fail=None):
    """Run fn(*args) on the thread pool; callbacks are delivered on the GUI thread."""
    t = _Task(fn, args)
    sig = t.sig
    _Task.live.add(sig)

    def fin(*_):
        _Task.live.discard(sig)

    if done:
        sig.done.connect(done)
    if fail:
        sig.fail.connect(fail)
    sig.done.connect(fin)
    sig.fail.connect(fin)
    QtCore.QThreadPool.globalInstance().start(t)


def is_dark():
    return QtWidgets.QApplication.palette().color(QtGui.QPalette.Window).lightness() < 128


def theme():
    d = is_dark()
    return {
        "bid": "#3ccf8e" if d else "#139a5b", "ask": "#ff6b6b" if d else "#d63b3b",
        "accent": "#5b9dff" if d else "#2f6fde", "warn": "#e3b341" if d else "#a87400",
        "muted": "#8a94a3" if d else "#5f6b7a", "faint": "#5d6674" if d else "#a0a8b4",
        "bg": QtWidgets.QApplication.palette().color(QtGui.QPalette.Base).name(),
        "text": QtWidgets.QApplication.palette().color(QtGui.QPalette.Text).name(),
        "line": "#2a313c" if d else "#e3e6ea",
    }


def blend(hex_color, alpha, bg):
    c, b = QtGui.QColor(hex_color), QtGui.QColor(bg)
    mix = lambda x, y: int(round(x * alpha + y * (1 - alpha)))
    return QtGui.QColor(mix(c.red(), b.red()), mix(c.green(), b.green()), mix(c.blue(), b.blue())).name()


FIELD_HUES = ["#5b9dff", "#3ccf8e", "#e3b341", "#ff6b6b", "#b48cff", "#4fc1c9"]


def field_color(name, i, bg):
    if re.match(r"^_reserved|^_dummy|padding", name):
        return blend("#888888", 0.18, bg)
    return blend(FIELD_HUES[i % len(FIELD_HUES)], 0.35, bg)


def fmt_bytes(b):
    if b is None:
        return "—"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return ("%.0f %s" if u == "B" else "%.1f %s") % (b, u)
        b /= 1024


def fmt_n(n):
    return "—" if n is None else "{:,}".format(n)


def fmt_px(v):
    if v is None:
        return None
    s = "%.9f" % v
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt_dur(s):
    return "%.1fs" % s if s < 60 else "%dm%02ds" % (s // 60, s % 60)


class TsFmt:
    def __init__(self):
        self.tz = "America/New_York"
        self.mode = "dt"
        self._cache = {}

    def set(self, tz=None, mode=None):
        self.tz = tz or self.tz
        self.mode = mode or self.mode
        self._cache.clear()

    def _sec(self, s):
        v = self._cache.get(s)
        if v is None:
            d = dt.datetime.fromtimestamp(s, core._tz(self.tz))
            v = (d.strftime("%Y-%m-%d"), d.strftime("%H:%M:%S"))
            if len(self._cache) > 100000:
                self._cache.clear()
            self._cache[s] = v
        return v

    def fmt(self, ns, mode=None):
        if ns is None:
            return None
        mode = mode or self.mode
        if mode == "ns":
            return str(ns)
        s, frac = divmod(int(ns), 1_000_000_000)
        d, t = self._sec(s)
        return "%s.%09d" % (t, frac) if mode == "t" else "%s %s.%09d" % (d, t, frac)

    @property
    def tz_short(self):
        return self.tz.split("/")[-1]


def ssh_hosts():
    hosts = []
    try:
        with open(os.path.expanduser("~/.ssh/config")) as f:
            for line in f:
                m = re.match(r"\s*Host\s+(.+)", line, re.I)
                if m:
                    hosts += [h for h in m.group(1).split() if not any(ch in h for ch in "*?!")]
    except OSError:
        pass
    return hosts


# ---------------------------------------------------------------------------
# table model
# ---------------------------------------------------------------------------
class RecordModel(QtCore.QAbstractTableModel):
    PAGE = 500

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.job = None
        self.n = 0
        self.allcols, self.cols, self.kinds, self.ci = [], [], {}, {}
        self.pages = collections.OrderedDict()

    def reset(self, job):
        self.beginResetModel()
        self.job, self.n = job, 0
        self.allcols, self.cols, self.kinds, self.ci = [], [], {}, {}
        self.pages.clear()
        self.endResetModel()

    def set_columns(self, allcols, kinds, hidden):
        cols = [c for c in allcols if c not in hidden]
        if allcols == self.allcols and cols == self.cols:
            return False
        self.beginResetModel()
        self.allcols, self.kinds = list(allcols), dict(kinds)
        self.ci = {c: i for i, c in enumerate(self.allcols)}
        self.cols = cols
        self.pages.clear()
        self.endResetModel()
        return True

    def set_rows(self, n):
        if n <= self.n:
            return
        self.pages.pop(self.n // self.PAGE, None)  # last page may have been partial
        self.beginInsertRows(QtCore.QModelIndex(), self.n, n - 1)
        self.n = n
        self.endInsertRows()

    def row(self, r):
        if self.job is None or r >= self.n:
            return None
        p = r // self.PAGE
        pg_ = self.pages.get(p)
        if pg_ is None:
            pg_ = self.job.rows(p * self.PAGE, self.PAGE, self.allcols)["rows"]
            self.pages[p] = pg_
            if len(self.pages) > 300:
                self.pages.popitem(last=False)
        else:
            self.pages.move_to_end(p)
        i = r - p * self.PAGE
        return pg_[i] if i < len(pg_) else None

    def row_dict(self, r):
        row = self.row(r)
        return None if row is None else dict(zip(self.allcols, row))

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else self.n

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.cols)

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        c = self.cols[idx.column()]
        k = self.kinds.get(c)
        if role == Qt.DisplayRole:
            r = self.row(idx.row())
            if r is None:
                return "…"
            return self.win.fmt_cell(c, r[self.ci[c]])
        if role == Qt.TextAlignmentRole:
            right = k in ("px", "int", "rec")
            return int((Qt.AlignRight if right else Qt.AlignLeft) | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            r = self.row(idx.row())
            v = None if r is None else r[self.ci[c]]
            t = self.win.colors
            if v is None:
                return QtGui.QColor(t["faint"])
            if c == "side":
                return QtGui.QColor(t["bid"] if v == "B" else t["ask"] if v == "A" else t["muted"])
            if c == "action":
                return QtGui.QColor({"A": t["accent"], "C": t["ask"], "T": t["warn"], "F": t["warn"],
                                     "R": t["ask"]}.get(v, t["text"]))
            if c.startswith("bid_px"):
                return QtGui.QColor(t["bid"])
            if c.startswith("ask_px"):
                return QtGui.QColor(t["ask"])
            if c in ("_rec", "rtype", "publisher_id"):
                return QtGui.QColor(t["muted"])
            return None
        if role == Qt.ToolTipRole:
            r = self.row(idx.row())
            v = None if r is None else r[self.ci[c]]
            if k == "flags" and v is not None:
                return "%d = %s" % (v, docs.flag_names(v))
            if k == "pub" and v is not None:
                return core.PUBLISHERS.get(v, str(v))
            et = self.win.enum_text(c, v)
            if et:
                return "%s = %s" % (v, et)
            if k == "ts" and v is not None:
                return "%s ns\n%s UTC" % (v, core.fmt_ts(v))
            return None
        return None

    def headerData(self, sec, orient, role=Qt.DisplayRole):
        if orient != Qt.Horizontal or sec >= len(self.cols):
            return None
        c = self.cols[sec]
        if role == Qt.DisplayRole:
            return "#rec" if c == "_rec" else c
        if role == Qt.ToolTipRole:
            return "%s\n%s" % (c, docs.field_doc(c))
        return None


# ---------------------------------------------------------------------------
# remote browser
# ---------------------------------------------------------------------------
class RemoteDialog(QtWidgets.QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle(T("開啟遠端檔案（ssh）"))
        self.resize(760, 520)
        self.settings = settings
        self.result_path = None
        self.host = QtWidgets.QComboBox()
        self.host.setEditable(True)
        hosts = ssh_hosts()
        self.host.addItems(hosts)
        self.host.setCurrentText(settings.value("remote/host", hosts[0] if hosts else ""))
        self.path = QtWidgets.QLineEdit(settings.value("remote/dir", "/data/databento"))
        up = QtWidgets.QPushButton(T("↑ 上一層"))
        go = QtWidgets.QPushButton(T("前往"))
        go.setDefault(True)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel(T("主機")))
        top.addWidget(self.host, 1)
        top.addWidget(QtWidgets.QLabel(T("路徑")))
        top.addWidget(self.path, 3)
        top.addWidget(up)
        top.addWidget(go)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels([T("名稱"), T("大小"), T("修改時間")])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.status = QtWidgets.QLabel(T("使用 ~/.ssh/config 的設定與金鑰（BatchMode，不會問密碼）。"))
        self.status.setStyleSheet("color:gray")
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Open | QtWidgets.QDialogButtonBox.Cancel)
        btns.button(QtWidgets.QDialogButtonBox.Open).setText(T("開啟"))
        btns.button(QtWidgets.QDialogButtonBox.Cancel).setText(T("取消"))
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.status)
        lay.addWidget(btns)
        go.clicked.connect(self.load)
        self.path.returnPressed.connect(self.load)
        up.clicked.connect(self.up)
        self.tree.itemDoubleClicked.connect(self.activate)
        btns.accepted.connect(lambda: self.activate(self.tree.currentItem()))
        btns.rejected.connect(self.reject)
        QtCore.QTimer.singleShot(0, self.load)

    def url(self, p=None):
        return "ssh://%s%s" % (self.host.currentText().strip(), p or self.path.text().strip())

    def load(self):
        self.tree.clear()
        self.status.setText(T("連線中… %s") % self.url())
        url = self.url()
        run_bg(core.list_dir, url, done=lambda ents: self.fill(url, ents),
               fail=lambda e: self.status.setText(T("錯誤：") + e))

    def fill(self, url, ents):
        if url != self.url():
            return
        self.settings.setValue("remote/host", self.host.currentText().strip())
        self.settings.setValue("remote/dir", self.path.text().strip())
        style = self.style()
        for e in ents:
            it = QtWidgets.QTreeWidgetItem([e["name"], "" if e["dir"] else fmt_bytes(e["size"]),
                                            "" if e["dir"] else dt.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d %H:%M")])
            it.setIcon(0, style.standardIcon(QtWidgets.QStyle.SP_DirIcon if e["dir"] else QtWidgets.QStyle.SP_FileIcon))
            it.setData(0, Qt.UserRole, e)
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(it)
        self.status.setText(T("%d 項 · 雙擊資料夾進入，雙擊檔案開啟") % len(ents))

    def up(self):
        p = self.path.text().rstrip("/")
        self.path.setText(p.rsplit("/", 1)[0] or "/")
        self.load()

    def activate(self, it):
        if it is None:
            return
        e = it.data(0, Qt.UserRole)
        p = self.path.text().rstrip("/") + "/" + e["name"]
        if e["dir"]:
            self.path.setText(p)
            self.load()
        else:
            self.result_path = self.url(p)
            self.accept()


# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QtCore.QSettings("dbnview", "dbnview")
        self.tsfmt = TsFmt()
        self.tsfmt.set(self.settings.value("tz", "America/New_York"), self.settings.value("tsmode", "dt"))
        self.hidden = set(self.settings.value("hidden", []) or [])
        self.colors = theme()
        self.fi = None
        self.meta = None
        self.job = None
        self.status = None
        self.stats = None
        self.last_stats = 0
        self.sym_patterns = []
        self.detail_row = None
        self.book_html = ""
        self.run_bg = run_bg
        self.mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.mono.setPointSize(11)

        self.setWindowTitle(APP_NAME)
        self.resize(1500, 900)
        self.setAcceptDrops(True)
        self._build_actions()
        self._build_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.poll)
        g = self.settings.value("geometry")
        if g is not None:
            self.restoreGeometry(g)
        s = self.settings.value("splitter")
        if s is not None:
            self.split.restoreState(s)
        self.update_actions()

    # ---- ui construction ------------------------------------------------
    def _build_actions(self):
        A = QtGui.QAction
        self.a_open = A(T("開啟檔案…"), self, shortcut=QtGui.QKeySequence.Open, triggered=self.open_local)
        self.a_remote = A(T("開啟遠端檔案（ssh）…"), self, shortcut="Ctrl+Shift+O", triggered=self.open_remote)
        self.a_scan = A(T("掃描"), self, shortcut="Ctrl+R", triggered=self.start_scan)
        self.a_stop = A(T("停止"), self, shortcut="Ctrl+.", triggered=self.stop_scan)
        self.a_export = A(T("匯出 CSV…"), self, shortcut="Ctrl+E", triggered=self.export_csv)
        self.a_detail = A(T("明細面板"), self, shortcut="Ctrl+I", checkable=True, checked=True,
                          triggered=lambda on: self.detail.setVisible(on))
        self.a_filters = A(T("檔案與篩選面板"), self, shortcut="Ctrl+L", checkable=True, checked=True,
                           triggered=lambda on: self.left.setVisible(on))
        self.a_quit = A(T("結束"), self, shortcut=QtGui.QKeySequence.Quit, triggered=self.close)
        self.recent_menu = QtWidgets.QMenu(T("最近開啟"), self)
        mb = self.menuBar()
        m = mb.addMenu(T("檔案"))
        m.addActions([self.a_open, self.a_remote])
        m.addMenu(self.recent_menu)
        m.addSeparator()
        m.addAction(self.a_export)
        m.addSeparator()
        m.addAction(self.a_quit)
        m = mb.addMenu(T("資料"))
        m.addActions([self.a_scan, self.a_stop])
        self.col_menu = mb.addMenu(T("欄位"))
        self.col_menu.aboutToShow.connect(self.fill_col_menu)
        m = mb.addMenu(T("檢視"))
        m.addActions([self.a_filters, self.a_detail])
        lm = mb.addMenu(T("語言") + ("" if i18n.get_lang() == "en" else " / Language"))
        grp = QtGui.QActionGroup(self)
        for code, label in i18n.LANGS:
            a = lm.addAction(label)
            a.setCheckable(True)
            a.setChecked(code == i18n.get_lang())
            grp.addAction(a)
            a.triggered.connect(lambda _=False, code=code: QtWidgets.QApplication.instance().switch_lang(code))
        self.rebuild_recent()

    def _build_ui(self):
        tb = self.addToolBar("main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addAction(self.a_open)
        tb.addAction(self.a_remote)
        rb = QtWidgets.QToolButton()
        rb.setText(T("最近"))
        rb.setMenu(self.recent_menu)
        rb.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        tb.addWidget(rb)
        tb.addSeparator()
        tb.addAction(self.a_scan)
        tb.addAction(self.a_stop)
        tb.addSeparator()
        tb.addWidget(QtWidgets.QLabel(T(" 時區 ")))
        self.tz_box = QtWidgets.QComboBox()
        for label, tz in TZS:
            self.tz_box.addItem(label, tz)
        self.tz_box.setCurrentIndex(max(0, self.tz_box.findData(self.tsfmt.tz)))
        self.tz_box.currentIndexChanged.connect(self.on_tz)
        tb.addWidget(self.tz_box)
        tb.addWidget(QtWidgets.QLabel(T(" 時間 ")))
        self.mode_box = QtWidgets.QComboBox()
        for label, m in ((T("日期+時間"), "dt"), (T("只顯示時間"), "t"), (T("原始 ns"), "ns")):
            self.mode_box.addItem(label, m)
        self.mode_box.setCurrentIndex(max(0, self.mode_box.findData(self.tsfmt.mode)))
        self.mode_box.currentIndexChanged.connect(self.on_tz)
        tb.addWidget(self.mode_box)
        tb.addSeparator()
        tb.addAction(self.a_export)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.a_detail)

        self.split = QtWidgets.QSplitter(Qt.Horizontal)
        self.left = self._build_left()
        self.tabs = self._build_tabs()
        self.detail = self._build_detail()
        self.split.addWidget(self.left)
        self.split.addWidget(self.tabs)
        self.split.addWidget(self.detail)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([310, 900, 380])
        self.split.setCollapsible(1, False)
        self.setCentralWidget(self.split)
        self.statusBar().showMessage(T("拖一個 .dbn / .dbn.zst 檔進來，或用 ⌘O / ⇧⌘O 開啟"))

    def _build_left(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 6, 8)
        self.info = QtWidgets.QLabel(T("尚未開啟檔案"))
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        box = QtWidgets.QGroupBox(T("檔案"))
        bl = QtWidgets.QVBoxLayout(box)
        bl.addWidget(self.info)
        lay.addWidget(box)

        fb = QtWidgets.QGroupBox(T("篩選"))
        form = QtWidgets.QFormLayout(fb)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.sym_edit = QtWidgets.QLineEdit()
        self.sym_edit.setPlaceholderText(T("輸入後 Enter：子字串；選建議：精確"))
        self.sym_edit.setFont(self.mono)
        self.sym_model = QtCore.QStringListModel()
        self.completer = QtWidgets.QCompleter(self.sym_model, self)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setMaxVisibleItems(16)
        self.sym_edit.setCompleter(self.completer)
        self.completer.activated[str].connect(lambda s: QtCore.QTimer.singleShot(0, lambda: self.add_symbol(s, True)))
        self.sym_edit.returnPressed.connect(lambda: self.add_symbol(self.sym_edit.text(), False))
        self.sym_list = QtWidgets.QListWidget()
        self.sym_list.setMaximumHeight(64)
        self.sym_list.setFont(self.mono)
        self.sym_list.setToolTip(T("雙擊或按 Delete 移除"))
        self.sym_list.itemDoubleClicked.connect(self.remove_symbol)
        QtGui.QShortcut(QtGui.QKeySequence.Delete, self.sym_list, activated=lambda: self.remove_symbol(self.sym_list.currentItem()))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.Key_Backspace), self.sym_list, activated=lambda: self.remove_symbol(self.sym_list.currentItem()))
        sw = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.sym_edit)
        sl.addWidget(self.sym_list)
        form.addRow("symbol", sw)
        self.iid_edit = QtWidgets.QLineEdit()
        self.iid_edit.setPlaceholderText(T("逗號分隔"))
        form.addRow("instrument_id", self.iid_edit)
        self.t0_edit = QtWidgets.QLineEdit()
        self.t0_edit.setPlaceholderText(T("09:30 或 2026-01-02 09:30:00"))
        self.t1_edit = QtWidgets.QLineEdit()
        self.t1_edit.setPlaceholderText(T("10:00（不含）"))
        form.addRow(T("起"), self.t0_edit)
        form.addRow(T("迄"), self.t1_edit)
        self.tf_box = QtWidgets.QComboBox()
        self.tf_box.addItem(T("自動（ts_recv 優先）"), "auto")
        self.tf_box.addItem("ts_recv", "ts_recv")
        self.tf_box.addItem("ts_event", "ts_event")
        form.addRow(T("時間欄位"), self.tf_box)
        self.act_boxes, self.side_boxes = {}, {}
        self.act_row = QtWidgets.QWidget()
        al = QtWidgets.QGridLayout(self.act_row)
        al.setContentsMargins(0, 0, 0, 0)
        al.setHorizontalSpacing(6)
        for i, a in enumerate("ACMRTFN"):
            cb = QtWidgets.QCheckBox(a)
            cb.setToolTip(dict(docs.enums()[0][1]).get(a, ""))
            self.act_boxes[a] = cb
            al.addWidget(cb, i // 4, i % 4)
        form.addRow("action", self.act_row)
        self.side_row = QtWidgets.QWidget()
        sl2 = QtWidgets.QHBoxLayout(self.side_row)
        sl2.setContentsMargins(0, 0, 0, 0)
        for s in "BAN":
            cb = QtWidgets.QCheckBox(s)
            self.side_boxes[s] = cb
            sl2.addWidget(cb)
        sl2.addStretch()
        form.addRow("side", self.side_row)
        self.where_edit = QtWidgets.QLineEdit()
        self.where_edit.setFont(self.mono)
        self.where_edit.setPlaceholderText("size >= 10 and side == 'B'")
        self.where_edit.setToolTip(T("欄位名直接用；價格為實際數值（未定義為 NaN）。\n支援 and / or / not、+ - * /、== != < <= > >=、in (…)、abs()、isnan()。\n"
                                   "例：ask_px_00 - bid_px_00 <= 0.05、action in ('T','F')"))
        form.addRow("where", self.where_edit)
        self.cap_edit = QtWidgets.QLineEdit("1000000")
        self.cap_edit.setValidator(QtGui.QIntValidator(1, 2_000_000_000))
        self.full_cb = QtWidgets.QCheckBox(T("掃完整檔"))
        self.full_cb.setToolTip(T("達到列數上限後繼續掃完整個檔案，以取得完整統計"))
        cw = QtWidgets.QWidget()
        cl = QtWidgets.QHBoxLayout(cw)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.cap_edit, 1)
        cl.addWidget(self.full_cb)
        form.addRow(T("最多列數"), cw)
        bw = QtWidgets.QWidget()
        bl2 = QtWidgets.QHBoxLayout(bw)
        bl2.setContentsMargins(0, 4, 0, 0)
        b_scan = QtWidgets.QPushButton(T("掃描"))
        b_scan.setDefault(True)
        b_scan.clicked.connect(self.start_scan)
        b_stop = QtWidgets.QPushButton(T("停止"))
        b_stop.clicked.connect(self.stop_scan)
        b_clear = QtWidgets.QPushButton(T("清除"))
        b_clear.clicked.connect(self.clear_filters)
        self.b_scan, self.b_stop = b_scan, b_stop
        bl2.addWidget(b_scan)
        bl2.addWidget(b_stop)
        bl2.addWidget(b_clear)
        form.addRow(bw)
        for e in (self.iid_edit, self.t0_edit, self.t1_edit, self.where_edit, self.cap_edit):
            e.returnPressed.connect(self.start_scan)
        lay.addWidget(fb)

        pb = QtWidgets.QGroupBox(T("進度"))
        pl = QtWidgets.QVBoxLayout(pb)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        self.prog_label = QtWidgets.QLabel("—")
        self.prog_label.setWordWrap(True)
        self.err_label = QtWidgets.QLabel("")
        self.err_label.setWordWrap(True)
        self.err_label.setStyleSheet("color:%s" % self.colors["ask"])
        self.err_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pl.addWidget(self.progress)
        pl.addWidget(self.prog_label)
        pl.addWidget(self.err_label)
        lay.addWidget(pb)
        lay.addStretch()
        sa = QtWidgets.QScrollArea()
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QtWidgets.QFrame.NoFrame)
        sa.setMinimumWidth(270)
        return sa

    def _build_tabs(self):
        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        # table
        tw = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(tw)
        tl.setContentsMargins(0, 4, 0, 0)
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(6, 0, 6, 0)
        self.seek_edit = QtWidgets.QLineEdit()
        self.seek_edit.setPlaceholderText(T("跳到時間，例如 15:45"))
        self.seek_edit.setMaximumWidth(240)
        self.seek_edit.returnPressed.connect(self.seek)
        self.rows_label = QtWidgets.QLabel("")
        self.rows_label.setStyleSheet("color:gray")
        bar.addWidget(self.seek_edit)
        bar.addStretch()
        bar.addWidget(self.rows_label)
        tl.addLayout(bar)
        self.model = RecordModel(self)
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.model)
        self.view.setFont(self.mono)
        vh = self.view.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        vh.setDefaultSectionSize(QtGui.QFontMetrics(self.mono).height() + 6)
        hh = self.view.horizontalHeader()
        hh.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        hh.setHighlightSections(False)
        hh.setContextMenuPolicy(Qt.CustomContextMenu)
        hh.customContextMenuRequested.connect(lambda pos: self.fill_col_menu(popup=hh.mapToGlobal(pos)))
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.view.setWordWrap(False)
        self.view.setShowGrid(False)
        self.view.setAlternatingRowColors(True)
        self.view.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.view.selectionModel().currentRowChanged.connect(lambda cur, prev: self.show_detail(cur.row()))
        tl.addWidget(self.view, 1)
        tabs.addTab(tw, T("表格"))
        # chart
        self.chart = charts.ChartPanel(self)
        tabs.addTab(self.chart, T("圖表"))
        self.iv = ivsurface.IVPanel(self)
        # stats + format
        self.stats_view = QtWidgets.QTextBrowser()
        self.stats_view.setOpenLinks(False)
        self.stats_view.anchorClicked.connect(self.on_stats_link)
        tabs.addTab(self.stats_view, T("統計"))
        self.format_view = QtWidgets.QTextBrowser()
        tabs.addTab(self.format_view, T("格式說明"))
        tabs.addTab(self.iv, T("IV 曲面"))
        tabs.currentChanged.connect(self.on_tab)
        return tabs

    def _build_detail(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(6, 8, 10, 8)
        self.detail_title = QtWidgets.QLabel(T("<b>明細</b>"))
        self.book_btn = QtWidgets.QPushButton(T("重建此刻的訂單簿（MBO）"))
        self.book_btn.clicked.connect(self.load_book)
        self.book_btn.hide()
        self.detail_view = QtWidgets.QTextBrowser()
        self.detail_view.setPlaceholderText(T("點表格任一列，查看全部欄位、買賣盤與原始位元組。"))
        lay.addWidget(self.detail_title)
        lay.addWidget(self.book_btn)
        lay.addWidget(self.detail_view, 1)
        w.setMinimumWidth(300)
        return w

    def enum_text(self, c, v):
        if self.job is None or v is None:
            return None
        for cls, rt in list(self.job.rts.items()):
            if c in rt.dtype.names:
                m = enum_values.lookup(cls, c, v)
                if m:
                    return m
        return None

    # ---- formatting -----------------------------------------------------
    def fmt_cell(self, c, v):
        if v is None:
            return "—"
        k = self.model.kinds.get(c)
        if k == "ts":
            return self.tsfmt.fmt(v)
        if k == "px":
            return fmt_px(v)
        if k == "flags":
            return docs.flag_short(v) or "·"
        if k == "pub":
            n = core.PUBLISHERS.get(v)
            return n.split(".")[-1] if n else str(v)
        if isinstance(v, int) and QTY.search(c):
            return "{:,}".format(v)
        return str(v)

    def col_width(self, c):
        k = self.model.kinds.get(c)
        fm = QtGui.QFontMetrics(self.mono)
        ch = fm.horizontalAdvance("0")
        if k == "ts":
            return ch * (20 if self.tsfmt.mode == "t" else 31) + 16
        if k == "sym":
            return ch * 24 + 16
        if k == "px":
            return ch * 12 + 16
        if k in ("chr", "flags"):
            return ch * 6 + 16
        if c in ("rtype", "depth", "channel_id", "publisher_id"):
            return ch * 8 + 16
        if c in ("order_id", "raw_instrument_id"):
            return ch * 16 + 16
        return ch * 12 + 16

    def apply_col_widths(self):
        hfm = QtGui.QFontMetrics(self.view.horizontalHeader().font())
        for i, c in enumerate(self.model.cols):
            label = "#rec" if c == "_rec" else c
            self.view.setColumnWidth(i, max(self.col_width(c), hfm.horizontalAdvance(label) + 28))

    # ---- open -------------------------------------------------------------
    def open_local(self):
        start = self.settings.value("lastdir", os.path.expanduser("~/Downloads"))
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, T("開啟 DBN 檔"), start,
                                                     T("DBN 檔 (*.dbn *.zst *.dbn.zst);;所有檔案 (*)"))
        if p:
            self.settings.setValue("lastdir", os.path.dirname(p))
            self.open_path(p)

    def open_remote(self):
        d = RemoteDialog(self, self.settings)
        if d.exec() and d.result_path:
            self.open_path(d.result_path)

    def open_path(self, path):
        self.err_label.setText("")
        self.statusBar().showMessage(T("讀取檔頭… %s") % path)
        QtWidgets.QApplication.setOverrideCursor(Qt.BusyCursor)

        def done(fi):
            QtWidgets.QApplication.restoreOverrideCursor()
            self.on_file(fi)

        def fail(e):
            QtWidgets.QApplication.restoreOverrideCursor()
            self.show_error(e)
            self.statusBar().showMessage(T("開啟失敗"))

        run_bg(core.FileInfo.get, path, done=done, fail=fail)

    def on_file(self, fi):
        self.fi = fi
        self.meta = fi.to_json()
        self.add_recent(fi.path)
        name = fi.path.rsplit("/", 1)[-1]
        self.setWindowTitle("%s — %s" % (name, APP_NAME))
        if not core.is_remote(fi.path):
            self.setWindowFilePath(fi.path)
        self.render_info()
        rec = self.meta["record"] or {}
        fields = rec.get("fields", [])
        kinds = rec.get("kinds", {})
        self.act_row.setEnabled("action" in fields and kinds.get("action") == "chr")
        self.side_row.setEnabled("side" in fields)
        names = sorted({n for ivs in fi.symmap.iv.values() for _, _, n in ivs})
        self.sym_model.setStringList(names)
        self.sym_patterns = []
        self.refresh_sym_list()
        self.render_format()
        self.start_scan()

    def render_info(self):
        m, rec = self.meta["metadata"], self.meta["record"]
        t = self.colors
        rng = "%s<br>%s" % (self.tsfmt.fmt(m["start"], "dt"), self.tsfmt.fmt(m["end"], "dt") if m["end"] else "—")
        syms = ", ".join(esc(s) for s in m["symbols_preview"][:6]) + (" … (+%d)" % (m["n_symbols"] - 6) if m["n_symbols"] > 6 else "")
        rows = [(T("檔案"), esc(self.meta["path"])), (T("大小"), fmt_bytes(self.meta["size"]) + (" (zst)" if self.meta["compressed"] else "")),
                ("dataset", esc(m["dataset"])),
                ("schema", "%s%s" % (esc(m["schema"] or "mixed"), T(" · %dB/筆") % rec["size"] if rec else "")),
                ("DBN", "v%d%s" % (m["version"], " · ts_out" if m["ts_out"] else "")),
                (T("時間 (%s)") % self.tsfmt.tz_short, rng), ("stype", "%s → %s" % (esc(m["stype_in"] or "—"), esc(m["stype_out"]))),
                ("symbols", syms or "—"), ("mappings", "%s · %s ids" % (fmt_n(m["n_mappings"]), fmt_n(m["n_instruments"])))]
        self.info.setText("<table cellspacing=0 cellpadding=1>" + "".join(
            "<tr><td style='color:%s;padding-right:8px' valign=top>%s</td><td style='font-family:Menlo'>%s</td></tr>" % (t["muted"], k, v)
            for k, v in rows) + "</table>")

    # ---- symbols ------------------------------------------------------
    def add_symbol(self, text, from_completer):
        text = text.strip()
        if not text:
            self.start_scan()
            return
        names = self.sym_model.stringList()
        exact = from_completer or text in names
        pat = text + "$" if exact else text
        if pat not in self.sym_patterns:
            self.sym_patterns.append(pat)
        self.sym_edit.clear()
        self.refresh_sym_list()

    def remove_symbol(self, item):
        if item is None:
            return
        self.sym_patterns.remove(item.data(Qt.UserRole))
        self.refresh_sym_list()

    def refresh_sym_list(self):
        self.sym_list.clear()
        for p in self.sym_patterns:
            it = QtWidgets.QListWidgetItem(("= " + p[:-1]) if p.endswith("$") else ("∋ " + p))
            it.setData(Qt.UserRole, p)
            it.setToolTip(T("精確比對") if p.endswith("$") else T("子字串比對"))
            self.sym_list.addItem(it)
        self.sym_list.setVisible(bool(self.sym_patterns))

    def clear_filters(self):
        self.sym_patterns = []
        self.refresh_sym_list()
        for e in (self.iid_edit, self.t0_edit, self.t1_edit, self.where_edit):
            e.clear()
        for cb in list(self.act_boxes.values()) + list(self.side_boxes.values()):
            cb.setChecked(False)
        self.tf_box.setCurrentIndex(0)

    # ---- scanning -----------------------------------------------------
    def build_query(self):
        return {"symbols": self.sym_patterns, "iids": self.iid_edit.text(), "t0": self.t0_edit.text(),
                "t1": self.t1_edit.text(), "tz": self.tsfmt.tz, "tfield": self.tf_box.currentData(),
                "actions": [a for a, cb in self.act_boxes.items() if cb.isChecked()] if self.act_row.isEnabled() else [],
                "sides": [s for s, cb in self.side_boxes.items() if cb.isChecked()] if self.side_row.isEnabled() else [],
                "where": self.where_edit.text(), "cap": int(self.cap_edit.text() or 1_000_000),
                "full": self.full_cb.isChecked()}

    def start_scan(self):
        if self.fi is None:
            return
        self.err_label.setText("")
        if self.job is not None:
            self.job.cancelled = True
        try:
            job = core.Job(self.fi.path, self.build_query())
        except Exception as e:  # noqa: BLE001
            self.show_error("%s: %s" % (type(e).__name__, e))
            return
        self.job, self.status, self.stats, self.last_stats = job, None, None, 0
        self.model.reset(job)
        self.detail_row = None
        self.detail_view.clear()
        self.book_btn.hide()
        self.timer.start()
        self.update_actions()
        self.poll()

    def stop_scan(self):
        if self.job is not None:
            self.job.cancelled = True

    def poll(self):
        job = self.job
        if job is None:
            return
        want = job.done or time.time() - self.last_stats > 1.0
        st = job.status(with_stats=want)
        if st.get("stats"):
            self.stats = st["stats"]
            self.last_stats = time.time()
        self.status = st
        if self.model.set_columns(st["columns"], st["kinds"], self.hidden):
            self.apply_col_widths()
        self.model.set_rows(st["rows"])
        self.render_progress()
        if want and self.tabs.currentIndex() == 2:
            self.render_stats()
        if st["done"]:
            self.timer.stop()
            if st["error"]:
                self.show_error(st["error"])
            self.chart.fill_inst()
            self.iv.prepare()
            self.render_stats()
            if self.tabs.currentIndex() == 1:
                self.chart.on_instrument()
            self.update_actions()
            if self.view.currentIndex().row() < 0 and st["rows"]:
                self.view.selectRow(0)

    def render_progress(self):
        st = self.status
        pct = st["bytes_done"] / st["bytes_total"] if st["bytes_total"] else 0
        complete = st["done"] and not st["truncated"] and not st["cancelled"] and not st["error"]
        self.progress.setValue(1000 if complete else int(pct * 1000))
        rate = st["bytes_done"] / st["elapsed"] if st["elapsed"] > 0 else 0
        state = (T("錯誤") if st["error"] else T("已停止") if st["cancelled"] else T("掃描中") if not st["done"]
                 else T("達上限，已停止（未掃完）") if st["truncated"] else T("完成"))
        self.prog_label.setText(
            T("<b>%s</b> · %s<br>已載入 <b>%s</b> 列%s<br>符合 %s / 已讀 %s 筆<br>%s / %s (%.1f%%) · %s/s%s") % (
                state, fmt_dur(st["elapsed"]), fmt_n(st["rows"]), T("（上限）") if st["rows"] >= st["cap"] else "",
                fmt_n(st["matched"]), fmt_n(st["seen"]), fmt_bytes(st["bytes_done"]), fmt_bytes(st["bytes_total"]),
                pct * 100, fmt_bytes(rate),
                "<br><span style='color:gray'>%s</span>" % esc(" · ".join(st["filter"])) if st["filter"] else ""))
        self.rows_label.setText(T("%s 列%s") % (fmt_n(st["rows"]), "" if st["done"] else T(" · 掃描中…")))
        self.statusBar().showMessage("%s · %s" % (state, self.fi.path if self.fi else ""))

    def update_actions(self):
        running = self.job is not None and not self.job.done
        self.a_stop.setEnabled(running)
        self.b_stop.setEnabled(running)
        self.a_scan.setEnabled(self.fi is not None)
        self.b_scan.setEnabled(self.fi is not None)
        self.a_export.setEnabled(self.job is not None and self.job.n > 0)

    def show_error(self, e):
        self.err_label.setText(str(e))

    # ---- detail -------------------------------------------------------
    def show_detail(self, r):
        if r is None or r < 0 or self.job is None:
            return
        o = self.model.row_dict(r)
        if o is None:
            return
        self.detail_row = r
        self.book_html = ""
        is_mbo = "order_id" in o and self.model.kinds.get("action") == "chr"
        self.book_btn.setVisible(is_mbo)
        self.detail_title.setText(T("<b>第 %s 列</b> <span style='color:gray'>· 檔案內第 %s 筆</span>") % (fmt_n(r), fmt_n(o.get("_rec"))))
        self.render_detail()

    def ladder_html(self, bids, asks, ct_label=None):
        t = self.colors
        mx = max([b[1] or 0 for b in bids] + [a[1] or 0 for a in asks] + [1])

        def bar(v, col):
            n = int(round(14 * (v or 0) / mx))
            return "<span style='color:%s'>%s</span>" % (blend(col, 0.55, t["bg"]), "█" * n)

        def row(lv, col):
            ct = "" if ct_label is None else "<td align=right style='color:%s'>%s</td>" % (
                t["muted"], "" if lv[2] is None else (fmt_n(lv[2]) if isinstance(lv[2], int) else esc(str(lv[2]))))
            return ("<tr><td align=right style='color:%s'>%s</td><td align=right>%s</td><td>%s</td>%s</tr>"
                    % (col, fmt_px(lv[0]), fmt_n(lv[1]), bar(lv[1], col), ct))

        h = T("<table cellspacing=0 cellpadding=2 style='font-family:Menlo;font-size:11px'><tr style='color:%s'><th align=right>價格</th><th align=right>數量</th><th></th>%s</tr>") % (
            t["muted"], "" if ct_label is None else "<th align=right>%s</th>" % ct_label)
        h += "".join(row(a, t["ask"]) for a in reversed(asks))
        if bids and asks:
            sp = asks[0][0] - bids[0][0]
            mid = (asks[0][0] + bids[0][0]) / 2
            h += "<tr><td colspan=4 align=center style='color:%s'>spread %s · mid %s</td></tr>" % (
                t["muted"], fmt_px(round(sp, 9)), fmt_px(round(mid, 9)))
        h += "".join(row(b, t["bid"]) for b in bids)
        return h + "</table>"

    def render_detail(self):
        r = self.detail_row
        o = self.model.row_dict(r) if r is not None else None
        if o is None:
            return
        t = self.colors
        h = ""
        bids, asks, ct = [], [], None
        for i in range(10):
            k = "%02d" % i
            if "bid_px_" + k not in o:
                break
            c = "ct" if "bid_ct_" + k in o else ("pb" if "bid_pb_" + k in o else None)
            if c:
                ct = T("筆數") if c == "ct" else T("交易所")
            pv = (lambda x: (core.PUBLISHERS.get(x, str(x)).split(".")[-1])) if c == "pb" else (lambda x: x)
            if o["bid_px_" + k] is not None:
                bids.append((o["bid_px_" + k], o["bid_sz_" + k], pv(o["bid_%s_%s" % (c, k)]) if c else None))
            if o["ask_px_" + k] is not None:
                asks.append((o["ask_px_" + k], o["ask_sz_" + k], pv(o["ask_%s_%s" % (c, k)]) if c else None))
        if "bid_px_00" in o:
            h += T("<h4>買賣盤（此筆之後）</h4>") + self.ladder_html(bids, asks, ct)
        if self.book_html:
            h += self.book_html
        h += T("<h4>欄位</h4><table cellspacing=0 cellpadding=2 width=100%>")
        for c in self.model.allcols:
            v = o.get(c)
            k = self.model.kinds.get(c)
            extra = ""
            if v is None:
                s = "<span style='color:%s'>—</span>" % t["faint"]
            elif k == "ts":
                s = esc(self.tsfmt.fmt(v, "dt") + " " + self.tsfmt.tz_short)
                extra = "<br><span style='color:%s'>%s</span>" % (t["faint"], v)
            elif k == "flags":
                s = "%d = %s" % (v, docs.flag_names(v))
            elif k == "pub":
                s = "%s = %s" % (v, core.PUBLISHERS.get(v, "?"))
            elif k == "px":
                s = fmt_px(v)
            else:
                s = esc(str(v))
                et = self.enum_text(c, v)
                if et:
                    s += " <span style='color:%s'>= %s</span>" % (t["muted"], esc(et))
            h += ("<tr><td style='color:%s' valign=top title='%s'>%s</td><td style='font-family:Menlo'>%s%s</td></tr>"
                  % (t["muted"], esc(docs.field_doc(c)), "#rec" if c == "_rec" else esc(c), s, extra))
        h += "</table>"
        try:
            raw = self.job.raw(r)
            h += self.raw_html(raw)
        except Exception as e:  # noqa: BLE001
            h += "<p style='color:%s'>%s</p>" % (t["ask"], esc(str(e)))
        sb = self.detail_view.verticalScrollBar().value()
        self.detail_view.setHtml(h)
        self.detail_view.verticalScrollBar().setValue(sb)

    def raw_html(self, raw):
        t = self.colors
        lay, hx = raw["layout"], raw["hex"]
        owner = {}
        for i, f in enumerate(lay):
            for b in range(f[1], f[1] + f[2]):
                owner[b] = i
        n = len(hx) // 2
        h = (T("<h4>原始位元組（%s · rtype 0x%02x · %d bytes · little-endian）</h4>"
             "<p style='color:%s'>同一欄位同一顏色；下表列出每個欄位的 offset、型別與原始整數值。</p>"
             "<pre style='font-family:Menlo;font-size:11px'>")) % (esc(raw["cls"]), raw["rtype"], n, t["muted"])
        for off in range(0, n, 16):
            h += "<span style='color:%s'>%04x</span>  " % (t["faint"], off)
            for b in range(off, min(n, off + 16)):
                i = owner.get(b)
                bg = field_color(lay[i][0], i, t["bg"]) if i is not None else t["bg"]
                h += "<span style='background-color:%s'>%s</span>%s" % (bg, hx[b * 2:b * 2 + 2], " " if b % 16 != 15 else "")
            h += "\n"
        h += "</pre><table cellspacing=0 cellpadding=2 style='font-size:11px'>"
        h += T("<tr style='color:%s'><th align=left>offset</th><th align=left>欄位</th><th align=left>型別</th><th align=left>原始值</th></tr>") % t["muted"]
        for i, f in enumerate(lay):
            h += ("<tr><td style='font-family:Menlo'>%d<span style='color:%s'>+%d</span></td>"
                  "<td style='font-family:Menlo;background-color:%s'>%s</td><td style='font-family:Menlo;color:%s'>%s</td>"
                  "<td style='font-family:Menlo'>%s</td></tr>") % (
                f[1], t["muted"], f[2], field_color(f[0], i, t["bg"]), esc(f[0]), t["muted"], esc(f[3]),
                "" if f[4] is None else esc(str(f[4])))
        return h + "</table>"

    def load_book(self):
        r = self.detail_row
        if r is None or self.job is None:
            return
        self.book_btn.setEnabled(False)
        self.book_btn.setText(T("重建中…"))

        def done(b):
            self.book_btn.setEnabled(True)
            self.book_btn.setText(T("重建此刻的訂單簿（MBO）"))
            if r != self.detail_row:
                return
            t = self.colors
            h = T("<h4>訂單簿（MBO 重建）</h4><p style='color:%s'>%s · 套用 %s 筆 MBO · %s 張掛單</p>") % (
                t["muted"], esc(b["symbol"] or str(b["instrument_id"])), fmt_n(b["applied"]), fmt_n(b["orders"]))
            if not b["safe"]:
                h += T("<p style='color:%s'>目前篩選可能漏掉此商品較早的訊息（時間/action/side/where），簿可能不正確。</p>") % t["warn"]
            if not b["had_clear"]:
                h += T("<p style='color:%s'>檔案開頭沒有清簿 (R)／快照，開始前已存在的掛單不在簿中。</p>") % t["warn"]
            self.book_html = h + self.ladder_html(b["bids"], b["asks"], T("掛單數"))
            self.render_detail()

        def fail(e):
            self.book_btn.setEnabled(True)
            self.book_btn.setText(T("重建此刻的訂單簿（MBO）"))
            self.show_error(e)

        run_bg(self.job.book, r, 15, done=done, fail=fail)

    # ---- table tools ----------------------------------------------------
    def seek(self):
        if self.job is None or not self.seek_edit.text().strip():
            return
        try:
            ns = core.parse_time(self.seek_edit.text(), self.tsfmt.tz, self.job.tmin or self.fi.md["start"])
        except Exception as e:  # noqa: BLE001
            self.show_error(T("時間格式錯誤：%s") % e)
            return
        r = min(self.job.seek(ns), self.model.n - 1)
        if r >= 0:
            idx = self.model.index(r, 0)
            self.view.setCurrentIndex(idx)
            self.view.scrollTo(idx, QtWidgets.QAbstractItemView.PositionAtCenter)

    def fill_col_menu(self, popup=None):
        menu = self.col_menu if popup is None else QtWidgets.QMenu(self)
        menu.clear()
        a = menu.addAction(T("全部顯示"))
        a.triggered.connect(lambda: self.set_hidden(set()))
        a = menu.addAction(T("精簡（隱藏 rtype、publisher、sequence…）"))
        a.triggered.connect(lambda: self.set_hidden(self.hidden | {"_rec", "rtype", "publisher_id", "ts_in_delta",
                                                                   "sequence", "channel_id", "ts_event"}))
        menu.addSeparator()
        for c in self.model.allcols:
            act = menu.addAction("#rec" if c == "_rec" else c)
            act.setCheckable(True)
            act.setChecked(c not in self.hidden)
            act.setToolTip(docs.field_doc(c))
            act.toggled.connect(lambda on, c=c: self.set_hidden(self.hidden - {c} if on else self.hidden | {c}))
        if popup is not None:
            menu.exec(popup)

    def set_hidden(self, hidden):
        self.hidden = set(hidden)
        self.settings.setValue("hidden", sorted(self.hidden))
        cur = self.view.currentIndex().row()
        if self.model.set_columns(self.model.allcols, self.model.kinds, self.hidden):
            self.apply_col_widths()
        if cur >= 0:
            self.view.selectRow(cur)

    def export_csv(self):
        if self.job is None or self.job.n == 0:
            return
        base = self.fi.path.rsplit("/", 1)[-1].replace(".dbn.zst", "").replace(".dbn", "")
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, T("匯出 CSV"), os.path.join(
            self.settings.value("lastdir", os.path.expanduser("~/Downloads")), base + ".csv"), "CSV (*.csv)")
        if not p:
            return
        job, tz, kinds = self.job, core._tz(self.tsfmt.tz), dict(self.model.kinds)

        def work():
            cols = job.columns
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for off in range(0, job.n, 50000):
                    for r in job.rows(off, 50000)["rows"]:
                        w.writerow([core.fmt_ts(v, tz) if kinds.get(c) == "ts" and v is not None else
                                    ("" if v is None else v) for c, v in zip(cols, r)])
            return job.n

        self.statusBar().showMessage(T("匯出中… %s") % p)
        run_bg(work, done=lambda n: self.statusBar().showMessage(T("已匯出 %s 列 → %s") % (fmt_n(n), p)),
               fail=self.show_error)

    # ---- tz / tabs ----------------------------------------------------
    def on_tz(self):
        self.tsfmt.set(self.tz_box.currentData(), self.mode_box.currentData())
        self.settings.setValue("tz", self.tsfmt.tz)
        self.settings.setValue("tsmode", self.tsfmt.mode)
        if self.meta:
            self.render_info()
            self.render_format()
        self.apply_col_widths()
        self.model.layoutChanged.emit()
        if self.detail_row is not None:
            self.render_detail()
        self.render_stats()
        if self.tabs.currentIndex() == 1:
            self.chart.draw()

    def on_tab(self, i):
        if i == 1 and self.chart.main is None:
            self.chart.on_instrument()
        elif i == 2:
            self.render_stats()
        elif i == 3:
            self.render_format()

    # ---- stats --------------------------------------------------------
    def hbars(self, d):
        t = self.colors
        e = sorted((d or {}).items(), key=lambda kv: -kv[1])
        if not e:
            return "<p style='color:gray'>—</p>"
        mx, tot = e[0][1], sum(v for _, v in e)
        return "<table cellspacing=0 cellpadding=2>" + "".join(
            "<tr><td style='font-family:Menlo'>%s</td><td><span style='color:%s'>%s</span></td>"
            "<td align=right style='color:%s'>%s · %.1f%%</td></tr>" % (
                esc(str(k)), t["accent"], "█" * max(1, int(24 * v / mx)), t["muted"], fmt_n(v), 100 * v / tot)
            for k, v in e) + "</table>"

    def render_stats(self):
        st, s = self.status, self.stats
        if not st or not s:
            self.stats_view.setHtml(T("<p style='color:gray'>尚無統計</p>"))
            return
        t = self.colors
        span = "%s<br>%s" % (self.tsfmt.fmt(st["tmin"], "dt"), self.tsfmt.fmt(st["tmax"], "dt")) if st["tmin"] else "—"
        partial = T("（掃描中）") if not st["done"] else (T("（僅涵蓋已掃描部分）") if st["truncated"] else "")
        tile = lambda label, val: ("<td style='padding:8px 18px 8px 0' valign=top><span style='color:%s'>%s</span><br>"
                                   "<span style='font-size:20px;font-weight:600'>%s</span></td>") % (t["muted"], label, val)
        h = "<table><tr>%s%s%s%s</tr></table>" % (
            tile(T("符合篩選 ") + partial, fmt_n(st["matched"])), tile(T("已讀紀錄"), fmt_n(st["seen"])),
            tile(T("商品數"), fmt_n(s["n_instruments"])),
            T("<td valign=top><span style='color:%s'>時間範圍 (%s)</span><br><span style='font-family:Menlo'>%s</span></td>") % (
                t["muted"], self.tsfmt.tz_short, span))
        h += "<table width=100%%><tr><td valign=top><h3>record type</h3>%s</td><td valign=top><h3>action</h3>%s</td>" \
             "<td valign=top><h3>side</h3>%s</td></tr></table>" % (self.hbars(s["rtype"]), self.hbars(s["action"]), self.hbars(s["side"]))
        h += T("<h3>前 %d 個商品（依筆數）</h3><table cellspacing=0 cellpadding=3 width=100%%>") % len(s["top"])
        h += T("<tr style='color:%s'><th align=left>symbol</th><th align=left>instrument_id</th><th align=right>筆數</th><th align=right>占比</th><th></th></tr>") % t["muted"]
        for iid, c, sym in s["top"]:
            h += (T("<tr><td style='font-family:Menlo'>%s</td><td style='font-family:Menlo'>%d</td><td align=right>%s</td>"
                  "<td align=right>%.2f%%</td><td><a href='filter:%d'>篩選</a>  <a href='chart:%d'>圖表</a></td></tr>")) % (
                esc((sym or "—").replace(" ", " ")), iid, fmt_n(c), 100 * c / max(1, st["matched"]), iid, iid)
        self.stats_view.setHtml(h + "</table>")

    def on_stats_link(self, url):
        kind, _, iid = url.toString().partition(":")
        if kind == "filter":
            self.sym_patterns = []
            self.refresh_sym_list()
            self.iid_edit.setText(iid)
            self.tabs.setCurrentIndex(0)
            self.start_scan()
        elif kind == "chart":
            self.tabs.setCurrentIndex(1)
            self.chart.show_iid(int(iid))

    # ---- format guide ---------------------------------------------------
    def render_format(self):
        if not self.meta:
            self.format_view.setHtml(T("<p style='color:gray'>先開啟一個檔案。</p>"))
            return
        t = self.colors
        m, rec, hl = self.meta["metadata"], self.meta["record"], core.metadata_layout(self.fi.md, T)
        sd = docs.schema_doc(m["schema"], T("混合 schema（檔案內有多種 rtype）。") if not m["schema"] else "")
        h = T("<h2>這個檔案是什麼</h2><p><b>%s</b> 的 <b>%s</b> 資料。%s</p>") % (esc(m["dataset"]), esc(m["schema"] or "mixed"), esc(sd))
        h += (T("<p>symbology：<code>%s</code> → <code>%s</code>。%s。檔內每筆紀錄只帶數字 <code>instrument_id</code>，"
              "要靠檔頭裡的 mappings 對回代碼（本檔 %s 組）。</p>")) % (
            esc(m["stype_in"] or "—"), esc(m["stype_out"]), esc(docs.stype_doc(m["stype_in"] or "")), fmt_n(m["n_mappings"]))
        box = "<td style='border:1px solid %s;padding:8px' width=30%%><b>%s</b><br><span style='color:%s'>%s</span></td>"
        h += "<table cellspacing=6><tr>%s<td>→</td>%s<td>→</td>%s</tr></table>" % (
            box % (t["line"], T(".zst 外層"), t["muted"], T("Zstandard 壓縮整條串流，不能隨機存取，只能從頭解")),
            box % (t["line"], "Metadata header", t["muted"], "%s bytes · DBN v%d" % (fmt_n(m["header_bytes"]), m["version"])),
            box % (t["line"], "Records", t["muted"], (T("%s 每筆 %d bytes，一筆接一筆") % (esc(rec["cls"]), rec["size"])) if rec else "—"))
        if rec:
            lay = rec["layout"]
            h += T("<h2>Record layout：%s（rtype 0x%02x，%d bytes）</h2>") % (esc(rec["cls"]), rec["rtype"], rec["size"])
            h += "<table cellspacing=0 cellpadding=3 width=100%><tr>" + "".join(
                "<td width=%.2f%% style='background-color:%s;font-family:Menlo;font-size:10px' align=center>%s</td>" % (
                    100.0 * f[2] / rec["size"], field_color(f[0], i, t["bg"]), esc(f[0]) if f[2] >= 4 else "")
                for i, f in enumerate(lay)) + "</tr></table>"
            h += (T("<p style='color:%s'>所有紀錄都以 16 bytes 的共同 header 開頭（length, rtype, publisher_id, instrument_id, ts_event），"
                  "之後依 rtype 不同。整數都是 little-endian；價格是 int64 定點數（÷1e9）；時間是 UNIX 奈秒。"
                  "在表格點任一列，右側明細會顯示該筆的實際位元組。</p>")) % t["muted"]
            h += T("<table cellspacing=0 cellpadding=3 width=100%%><tr style='color:%s'><th align=left>offset</th><th align=left>bytes</th>" \
                 "<th align=left>型別</th><th align=left>欄位</th><th align=left>說明</th></tr>") % t["muted"]
            for i, f in enumerate(lay):
                h += ("<tr><td style='font-family:Menlo'>%d</td><td style='font-family:Menlo'>%d</td><td style='font-family:Menlo'>%s</td>"
                      "<td style='font-family:Menlo;background-color:%s'>%s</td><td style='color:%s'>%s</td></tr>") % (
                    f[1], f[2], esc(f[3]), field_color(f[0], i, t["bg"]), esc(f[0]), t["muted"], esc(docs.field_doc(f[0])))
            h += "</table>"
        h += (T("<h2>Metadata header（本檔實際值）</h2><p style='color:%s'>解壓後的串流開頭：\"DBN\" + 版本 byte + 4-byte 長度，"
              "接著是下列欄位。v1 的 symbol 字串固定 22 bytes，v2/v3 為 71 bytes（由 symbol_cstr_len 指定）。</p>")) % t["muted"]
        h += T("<table cellspacing=0 cellpadding=3 width=100%%><tr style='color:%s'><th align=left>offset</th><th align=left>bytes</th>" \
             "<th align=left>型別</th><th align=left>欄位</th><th align=left>值</th></tr>") % t["muted"]
        for f in hl:
            v = "" if f[4] is None else str(f[4])
            if f[0] in ("start", "end") and v.isdigit():
                v = "%s  (%s %s)" % (v, self.tsfmt.fmt(int(v), "dt"), self.tsfmt.tz_short)
            h += ("<tr><td style='font-family:Menlo'>%d</td><td style='font-family:Menlo'>%s</td><td style='font-family:Menlo;color:%s'>%s</td>"
                  "<td style='font-family:Menlo'>%s</td><td style='font-family:Menlo'>%s</td></tr>") % (
                f[1], fmt_n(f[2]), t["muted"], esc(f[3]), esc(f[0]), esc(v))
        h += T("</table><h2>列舉值</h2><table cellspacing=12><tr>")
        for i, (title, rows) in enumerate(docs.enums() + [("rtype", [("0x%02x" % a, b) for a, b in docs.RTYPE_DOC])]):
            if i and i % 3 == 0:
                h += "</tr><tr>"
            h += "<td valign=top><h3>%s</h3><table cellspacing=0 cellpadding=2>%s</table></td>" % (esc(title), "".join(
                "<tr><td style='font-family:Menlo' valign=top>%s</td><td style='color:%s'>%s</td></tr>" % (esc(a), t["muted"], esc(b))
                for a, b in rows))
        h += T("</tr></table><h2>常見陷阱</h2><ul>") + "".join("<li>%s</li>" % esc(x) for x in docs.tips()) + "</ul>"
        self.format_view.setHtml(h)

    # ---- recent / dnd / lifecycle ----------------------------------------
    def add_recent(self, path):
        rec = [p for p in (self.settings.value("recent", []) or []) if p != path]
        rec.insert(0, path)
        self.settings.setValue("recent", rec[:15])
        self.rebuild_recent()

    def rebuild_recent(self):
        self.recent_menu.clear()
        rec = self.settings.value("recent", []) or []
        if isinstance(rec, str):
            rec = [rec]
        for p in rec:
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, p=p: self.open_path(p))
        if not rec:
            self.recent_menu.addAction(T("（沒有）")).setEnabled(False)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.open_path(u.toLocalFile())
                break

    def changeEvent(self, e):
        if e.type() in (QtCore.QEvent.PaletteChange, QtCore.QEvent.ApplicationPaletteChange):
            self.colors = theme()
            if hasattr(self, "chart") and self.chart.main is not None:
                self.chart.draw()
        super().changeEvent(e)

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.split.saveState())
        if self.job is not None:
            self.job.cancelled = True
        super().closeEvent(e)


class App(QtWidgets.QApplication):
    """Handles Finder 'Open With' / double-clicked documents on macOS, and language switching."""

    def __init__(self, argv):
        super().__init__(argv)
        self.win = None
        self.pending = []
        self.opened = set()

    def switch_lang(self, code):
        if code == i18n.get_lang():
            return
        QtCore.QSettings("dbnview", "dbnview").setValue("lang", code)
        apply_lang(code)
        old = self.win
        path = old.fi.path if old and old.fi else None
        old.close()
        self.win = MainWindow()
        self.win.show()
        if path:
            self.win.open_path(path)
        old.deleteLater()

    def event(self, e):
        if e.type() == QtCore.QEvent.FileOpen:
            # macOS also turns command-line arguments into FileOpen events: skip duplicates/non-files
            p = e.file()
            if not os.path.isfile(p):
                return True
            if self.win is None:
                self.pending.append(p)
            elif not (self.win.fi and self.win.fi.path == os.path.abspath(p)) and p not in self.opened:
                self.win.open_path(p)
            return True
        return super().event(e)


def apply_lang(code):
    i18n.set_lang(code)
    docs.set_lang(i18n.get_lang())


def main():
    app = App(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("dbnview")
    apply_lang(QtCore.QSettings("dbnview", "dbnview").value("lang") or i18n.system_lang())
    win = MainWindow()
    app.win = win
    win.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-psn")]
    app.opened = {os.path.abspath(os.path.expanduser(a)) for a in args}
    for p in (args[:1] or app.pending[:1]):
        win.open_path(p if core.is_remote(p) else os.path.abspath(os.path.expanduser(p)))
    shot = os.environ.get("DBNVIEW_SELFTEST")  # packaging smoke test: render tabs to PNGs, then quit
    if shot:
        def step():
            if win.job is None or not win.job.done or win.timer.isActive():
                return QtCore.QTimer.singleShot(200, step)
            for i in range(win.tabs.count()):
                win.tabs.setCurrentIndex(i)
                for _ in range(30):
                    app.processEvents()
                    time.sleep(0.03)
                if win.tabs.widget(i) is win.iv and win.iv.root.count():
                    win.iv.compute()
                    t0 = time.time()
                    while win.iv.s is None and time.time() - t0 < 60:
                        app.processEvents()
                        time.sleep(0.05)
                    for _ in range(30):
                        app.processEvents()
                        time.sleep(0.03)
                win.grab().save("%s_%d.png" % (shot, i))
            app.quit()
        QtCore.QTimer.singleShot(500, step)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
