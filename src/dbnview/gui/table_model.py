"""Qt table model over a scan job's loaded rows (paged, formatted lazily)."""
import collections

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt

from .. import reference
from ..engine import PUBLISHERS, fmt_ts


class RecordModel(QtCore.QAbstractTableModel):
    PAGE = 500

    def __init__(self, owner):
        """owner provides fmt_cell(col, value), enum_text(col, value) and a `colors` dict."""
        super().__init__()
        self.owner = owner
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
            return self.owner.fmt_cell(c, r[self.ci[c]])
        if role == Qt.TextAlignmentRole:
            right = k in ("px", "int", "rec")
            return int((Qt.AlignRight if right else Qt.AlignLeft) | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            r = self.row(idx.row())
            v = None if r is None else r[self.ci[c]]
            t = self.owner.colors
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
                return "%d = %s" % (v, reference.flag_names(v))
            if k == "pub" and v is not None:
                return PUBLISHERS.get(v, str(v))
            et = self.owner.enum_text(c, v)
            if et:
                return "%s = %s" % (v, et)
            if k == "ts" and v is not None:
                return "%s ns\n%s UTC" % (v, fmt_ts(v))
            return None
        return None

    def headerData(self, sec, orient, role=Qt.DisplayRole):
        if orient != Qt.Horizontal or sec >= len(self.cols):
            return None
        c = self.cols[sec]
        if role == Qt.DisplayRole:
            return "#rec" if c == "_rec" else c
        if role == Qt.ToolTipRole:
            return "%s\n%s" % (c, reference.field_doc(c))
        return None

