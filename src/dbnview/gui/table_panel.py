"""Table tab: the loaded rows in a virtual table, time seek, column visibility and CSV export."""
import csv
import os

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import reference
from ..engine import PUBLISHERS, fmt_ts, get_tz, parse_time
from ..i18n import T
from ..display import pretty_field
from .common import QTY, display_name, fmt_n, fmt_px, run_bg
from .table_model import RecordModel

COMPACT_HIDE = {"_rec", "rtype", "publisher_id", "ts_in_delta", "sequence", "channel_id", "ts_event"}


class TablePanel(QtWidgets.QWidget):
    """Owns the RecordModel; emits rowSelected(row) when the current row changes."""

    rowSelected = QtCore.Signal(int)

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.hidden = set(win.settings.value("hidden", []) or [])
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(6, 0, 6, 0)
        self.seek_edit = QtWidgets.QLineEdit()
        self.seek_edit.setPlaceholderText(T("Jump to time, e.g. 15:45"))
        self.seek_edit.setMaximumWidth(240)
        self.seek_edit.returnPressed.connect(self.seek)
        self.rows_label = QtWidgets.QLabel("")
        self.rows_label.setStyleSheet("color:gray")
        bar.addWidget(self.seek_edit)
        bar.addStretch()
        bar.addWidget(self.rows_label)
        lay.addLayout(bar)

        self.model = RecordModel(self)
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.model)
        self.view.setFont(win.mono)
        vh = self.view.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        vh.setDefaultSectionSize(QtGui.QFontMetrics(win.mono).height() + 6)
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
        self.view.selectionModel().currentRowChanged.connect(lambda cur, prev: self.rowSelected.emit(cur.row()))
        lay.addWidget(self.view, 1)

    # ---- model owner interface (used by RecordModel) ------------------------
    @property
    def colors(self):
        return self.win.colors

    def enum_text(self, c, v):
        return reference.enum_text(self.win.job, c, v)

    def fmt_cell(self, c, v):
        if v is None:
            return "—"
        k = self.model.kinds.get(c)
        if k == "ts":
            return self.win.tsfmt.fmt(v)
        if k == "px":
            return fmt_px(v)
        if k == "flags":
            return reference.flag_short(v) or "·"
        if k == "pub":
            n = PUBLISHERS.get(v)
            return n.split(".")[-1] if n else str(v)
        if isinstance(v, int) and QTY.search(c):
            return "{:,}".format(v)
        return str(v)

    # ---- job updates ------------------------------------------------------------
    def reset(self, job):
        self.model.reset(job)

    def update_from_status(self, st):
        if self.model.set_columns(st["columns"], st["kinds"], self.hidden):
            self.apply_col_widths()
        self.model.set_rows(st["rows"])
        self.rows_label.setText(T("%s rows%s") % (fmt_n(st["rows"]), "" if st["done"] else T(" · scanning…")))

    def refresh(self):
        """Re-render after a time-zone / format change."""
        self.apply_col_widths()
        self.model.layoutChanged.emit()

    def select_first_if_none(self):
        if self.view.currentIndex().row() < 0 and self.model.n:
            self.view.selectRow(0)

    # ---- columns ------------------------------------------------------------------
    def col_width(self, c):
        k = self.model.kinds.get(c)
        ch = QtGui.QFontMetrics(self.win.mono).horizontalAdvance("0")
        if k == "ts":
            return ch * (20 if self.win.tsfmt.mode == "t" else 31) + 16
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
            self.view.setColumnWidth(i, max(self.col_width(c), hfm.horizontalAdvance(pretty_field(c)) + 28))

    def fill_col_menu(self, menu=None, popup=None):
        menu = menu if menu is not None else QtWidgets.QMenu(self)
        menu.clear()
        menu.addAction(T("Show All")).triggered.connect(lambda: self.set_hidden(set()))
        menu.addAction(T("Compact (hide rtype, publisher, sequence…)")).triggered.connect(
            lambda: self.set_hidden(self.hidden | COMPACT_HIDE))
        menu.addSeparator()
        for c in self.model.allcols:
            act = menu.addAction(pretty_field(c))
            act.setCheckable(True)
            act.setChecked(c not in self.hidden)
            act.setToolTip("%s\n%s" % (c, reference.field_doc(c)))
            act.toggled.connect(lambda on, c=c: self.set_hidden(self.hidden - {c} if on else self.hidden | {c}))
        if popup is not None:
            menu.exec(popup)

    def set_hidden(self, hidden):
        self.hidden = set(hidden)
        self.win.settings.setValue("hidden", sorted(self.hidden))
        cur = self.view.currentIndex().row()
        if self.model.set_columns(self.model.allcols, self.model.kinds, self.hidden):
            self.apply_col_widths()
        if cur >= 0:
            self.view.selectRow(cur)

    # ---- tools -----------------------------------------------------------------------
    def seek(self):
        job = self.win.job
        if job is None or not self.seek_edit.text().strip():
            return
        try:
            ns = parse_time(self.seek_edit.text(), self.win.tsfmt.tz, job.tmin or self.win.fi.md["start"])
        except Exception as e:  # noqa: BLE001
            self.win.show_error(T("Invalid time format: %s") % e)
            return
        r = min(job.seek(ns), self.model.n - 1)
        if r >= 0:
            idx = self.model.index(r, 0)
            self.view.setCurrentIndex(idx)
            self.view.scrollTo(idx, QtWidgets.QAbstractItemView.PositionAtCenter)

    def export_csv(self):
        job = self.win.job
        if job is None or job.n == 0:
            return
        base = display_name(self.win.fi.path).replace(".dbn.zst", "").replace(".dbn", "")
        start = self.win.settings.value("lastdir", os.path.expanduser("~"))
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, T("Export CSV"), os.path.join(start, base + ".csv"),
                                                     "CSV (*.csv)")
        if not p:
            return
        tz, kinds = get_tz(self.win.tsfmt.tz), dict(self.model.kinds)

        def work():
            cols = job.columns
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for off in range(0, job.n, 50000):
                    for r in job.rows(off, 50000)["rows"]:
                        w.writerow([fmt_ts(v, tz) if kinds.get(c) == "ts" and v is not None else
                                    ("" if v is None else v) for c, v in zip(cols, r)])
            return job.n

        sb = self.win.statusBar()
        sb.showMessage(T("Exporting… %s") % p)
        run_bg(work, done=lambda n: sb.showMessage(T("Exported %s rows → %s") % (fmt_n(n), p)),
               fail=self.win.show_error)
