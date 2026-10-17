"""Left panel: file metadata, scan filters and scan progress."""
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import reference
from ..i18n import T
from ..display import pretty_stype
from .common import esc, fmt_bytes, fmt_dur, fmt_n


class FilterPanel(QtWidgets.QScrollArea):
    """Shows the open file's metadata, collects the scan query and displays scan progress.

    Emits scanRequested / stopRequested; the main window owns the actual scan job.
    """

    scanRequested = QtCore.Signal()
    stopRequested = QtCore.Signal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.sym_patterns = []
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 6, 8)
        lay.addWidget(self._build_info())
        lay.addWidget(self._build_filters())
        lay.addWidget(self._build_progress())
        lay.addStretch()
        self.setWidget(w)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setMinimumWidth(270)

    # ---- construction -------------------------------------------------------
    def _build_info(self):
        self.info = QtWidgets.QLabel(T("尚未開啟檔案"))
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        box = QtWidgets.QGroupBox(T("檔案"))
        QtWidgets.QVBoxLayout(box).addWidget(self.info)
        return box

    def _build_filters(self):
        mono = self.win.mono
        fb = QtWidgets.QGroupBox(T("篩選"))
        form = QtWidgets.QFormLayout(fb)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.sym_edit = QtWidgets.QLineEdit()
        self.sym_edit.setPlaceholderText(T("輸入後 Enter：子字串；選建議：精確"))
        self.sym_edit.setFont(mono)
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
        self.sym_list.setFont(mono)
        self.sym_list.setToolTip(T("雙擊或按 Delete 移除"))
        self.sym_list.itemDoubleClicked.connect(self.remove_symbol)
        for key in (QtGui.QKeySequence.Delete, QtGui.QKeySequence(Qt.Key_Backspace)):
            QtGui.QShortcut(key, self.sym_list, activated=lambda: self.remove_symbol(self.sym_list.currentItem()))
        sw = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.sym_edit)
        sl.addWidget(self.sym_list)
        form.addRow(T("代碼"), sw)

        self.iid_edit = QtWidgets.QLineEdit()
        self.iid_edit.setPlaceholderText(T("逗號分隔"))
        form.addRow(T("商品 ID"), self.iid_edit)
        self.t0_edit = QtWidgets.QLineEdit()
        self.t0_edit.setPlaceholderText(T("09:30 或 2026-01-02 09:30:00"))
        self.t1_edit = QtWidgets.QLineEdit()
        self.t1_edit.setPlaceholderText(T("10:00（不含）"))
        form.addRow(T("起"), self.t0_edit)
        form.addRow(T("迄"), self.t1_edit)
        self.tf_box = QtWidgets.QComboBox()
        self.tf_box.addItem(T("自動（優先接收時間）"), "auto")
        self.tf_box.addItem(T("接收時間"), "ts_recv")
        self.tf_box.addItem(T("事件時間"), "ts_event")
        form.addRow(T("時間欄位"), self.tf_box)

        self.act_boxes, self.side_boxes = {}, {}
        self.act_row = QtWidgets.QWidget()
        al = QtWidgets.QGridLayout(self.act_row)
        al.setContentsMargins(0, 0, 0, 0)
        al.setHorizontalSpacing(6)
        action_docs = dict(reference.enums()[0][1])
        for i, a in enumerate("ACMRTFN"):
            cb = QtWidgets.QCheckBox(a)
            cb.setToolTip(action_docs.get(a, ""))
            self.act_boxes[a] = cb
            al.addWidget(cb, i // 4, i % 4)
        form.addRow(T("動作"), self.act_row)
        self.side_row = QtWidgets.QWidget()
        sl2 = QtWidgets.QHBoxLayout(self.side_row)
        sl2.setContentsMargins(0, 0, 0, 0)
        for s in "BAN":
            cb = QtWidgets.QCheckBox(s)
            self.side_boxes[s] = cb
            sl2.addWidget(cb)
        sl2.addStretch()
        form.addRow(T("方向"), self.side_row)

        self.where_edit = QtWidgets.QLineEdit()
        self.where_edit.setFont(mono)
        self.where_edit.setPlaceholderText("size >= 10 and side == 'B'")
        self.where_edit.setToolTip(T("欄位名直接用；價格為實際數值（未定義為 NaN）。\n支援 and / or / not、+ - * /、== != < <= > >=、in (…)、abs()、isnan()。\n"
                                     "例：ask_px_00 - bid_px_00 <= 0.05、action in ('T','F')"))
        form.addRow(T("條件式"), self.where_edit)
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
        bl = QtWidgets.QHBoxLayout(bw)
        bl.setContentsMargins(0, 4, 0, 0)
        self.b_scan = QtWidgets.QPushButton(T("掃描"))
        self.b_scan.setDefault(True)
        self.b_scan.clicked.connect(self.scanRequested)
        self.b_stop = QtWidgets.QPushButton(T("停止"))
        self.b_stop.clicked.connect(self.stopRequested)
        b_clear = QtWidgets.QPushButton(T("清除"))
        b_clear.clicked.connect(self.clear_filters)
        for b in (self.b_scan, self.b_stop, b_clear):
            bl.addWidget(b)
        form.addRow(bw)
        for e in (self.iid_edit, self.t0_edit, self.t1_edit, self.where_edit, self.cap_edit):
            e.returnPressed.connect(self.scanRequested)
        return fb

    def _build_progress(self):
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
        self.err_label.setStyleSheet("color:%s" % self.win.colors["ask"])
        self.err_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for wdg in (self.progress, self.prog_label, self.err_label):
            pl.addWidget(wdg)
        return pb

    # ---- file -------------------------------------------------------------------
    def set_file(self, fi, meta):
        """Show metadata of a newly opened file and adapt the filter widgets to its record type."""
        self.render_info(meta)
        rec = meta["record"] or {}
        fields, kinds = rec.get("fields", []), rec.get("kinds", {})
        self.act_row.setEnabled("action" in fields and kinds.get("action") == "chr")
        self.side_row.setEnabled("side" in fields)
        self.sym_model.setStringList(sorted({n for ivs in fi.symmap.iv.values() for _, _, n in ivs}))
        self.sym_patterns = []
        self.refresh_sym_list()

    def render_info(self, meta):
        m, rec = meta["metadata"], meta["record"]
        t, ts = self.win.colors, self.win.tsfmt
        rng = "%s<br>%s" % (ts.fmt(m["start"], "dt"), ts.fmt(m["end"], "dt") if m["end"] else "—")
        syms = ", ".join(esc(s) for s in m["symbols_preview"][:6]) + (
            " … (+%d)" % (m["n_symbols"] - 6) if m["n_symbols"] > 6 else "")
        rows = [(T("檔案"), esc(meta["path"])),
                (T("大小"), fmt_bytes(meta["size"]) + (" (zst)" if meta["compressed"] else "")),
                (T("資料集"), esc(m["dataset"])),
                ("Schema", "%s%s" % (esc(m["schema"] or "mixed"), T(" · %dB/筆") % rec["size"] if rec else "")),
                (T("DBN 版本"), "v%d%s" % (m["version"], T(" · 含送出時間") if m["ts_out"] else "")),
                (T("時間 (%s)") % ts.tz_short, rng),
                (T("代碼體系"), "%s → %s" % (esc(pretty_stype(m["stype_in"])), esc(pretty_stype(m["stype_out"])))),
                (T("代碼"), syms or "—"),
                (T("代碼對應"), "%s · %s IDs" % (fmt_n(m["n_mappings"]), fmt_n(m["n_instruments"])))]
        self.info.setText("<table cellspacing=0 cellpadding=1>" + "".join(
            "<tr><td style='color:%s;padding-right:8px' valign=top>%s</td><td style='font-family:Menlo'>%s</td></tr>"
            % (t["muted"], k, v) for k, v in rows) + "</table>")

    # ---- symbols ----------------------------------------------------------------
    def add_symbol(self, text, from_completer):
        text = text.strip()
        if not text:
            self.scanRequested.emit()
            return
        exact = from_completer or text in self.sym_model.stringList()
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

    def filter_instrument(self, iid):
        """Replace the symbol/instrument filters by a single instrument_id."""
        self.sym_patterns = []
        self.refresh_sym_list()
        self.iid_edit.setText(str(iid))

    # ---- query / progress -------------------------------------------------------
    def query(self):
        """The scan query dict understood by engine.Job."""
        return {"symbols": self.sym_patterns, "iids": self.iid_edit.text(), "t0": self.t0_edit.text(),
                "t1": self.t1_edit.text(), "tz": self.win.tsfmt.tz, "tfield": self.tf_box.currentData(),
                "actions": [a for a, cb in self.act_boxes.items() if cb.isChecked()] if self.act_row.isEnabled() else [],
                "sides": [s for s, cb in self.side_boxes.items() if cb.isChecked()] if self.side_row.isEnabled() else [],
                "where": self.where_edit.text(), "cap": int(self.cap_edit.text() or 1_000_000),
                "full": self.full_cb.isChecked()}

    @staticmethod
    def state_text(st):
        return (T("錯誤") if st["error"] else T("已停止") if st["cancelled"] else T("掃描中") if not st["done"]
                else T("達上限，已停止（未掃完）") if st["truncated"] else T("完成"))

    def render_progress(self, st):
        pct = st["bytes_done"] / st["bytes_total"] if st["bytes_total"] else 0
        complete = st["done"] and not st["truncated"] and not st["cancelled"] and not st["error"]
        self.progress.setValue(1000 if complete else int(pct * 1000))
        rate = st["bytes_done"] / st["elapsed"] if st["elapsed"] > 0 else 0
        self.prog_label.setText(
            T("<b>%s</b> · %s<br>已載入 <b>%s</b> 列%s<br>符合 %s / 已讀 %s 筆<br>%s / %s (%.1f%%) · %s/s%s") % (
                self.state_text(st), fmt_dur(st["elapsed"]), fmt_n(st["rows"]),
                T("（上限）") if st["rows"] >= st["cap"] else "",
                fmt_n(st["matched"]), fmt_n(st["seen"]), fmt_bytes(st["bytes_done"]), fmt_bytes(st["bytes_total"]),
                pct * 100, fmt_bytes(rate),
                "<br><span style='color:gray'>%s</span>" % esc(" · ".join(st["filter"])) if st["filter"] else ""))

    def set_running(self, have_file, running):
        self.b_scan.setEnabled(have_file)
        self.b_stop.setEnabled(running)

    def show_error(self, e):
        self.err_label.setText(str(e) if e else "")
