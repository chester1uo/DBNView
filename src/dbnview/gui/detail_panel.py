"""Right panel: every field of the selected row, its bid/ask ladder, the MBO book rebuild and raw bytes."""
from PySide6 import QtWidgets

from .. import reference
from ..analysis.book import book_at
from ..engine import PUBLISHERS
from ..i18n import T
from .common import MONO_CSS, blend, esc, field_color, fmt_n, fmt_px, run_bg


class DetailPanel(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.row = None
        self.book_html = ""
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 10, 8)
        self.title = QtWidgets.QLabel(T("<b>明細</b>"))
        self.book_btn = QtWidgets.QPushButton(T("重建此刻的訂單簿（MBO）"))
        self.book_btn.clicked.connect(self.load_book)
        self.book_btn.hide()
        self.view = QtWidgets.QTextBrowser()
        self.view.setPlaceholderText(T("點表格任一列，查看全部欄位、買賣盤與原始位元組。"))
        lay.addWidget(self.title)
        lay.addWidget(self.book_btn)
        lay.addWidget(self.view, 1)
        self.setMinimumWidth(300)

    @property
    def model(self):
        return self.win.table.model

    def clear(self):
        self.row = None
        self.book_html = ""
        self.view.clear()
        self.book_btn.hide()

    def show_row(self, r):
        if r is None or r < 0 or self.win.job is None:
            return
        o = self.model.row_dict(r)
        if o is None:
            return
        self.row = r
        self.book_html = ""
        self.book_btn.setVisible("order_id" in o and self.model.kinds.get("action") == "chr")
        self.title.setText(T("<b>第 %s 列</b> <span style='color:gray'>· 檔案內第 %s 筆</span>")
                           % (fmt_n(r), fmt_n(o.get("_rec"))))
        self.render()

    # ---- html pieces ---------------------------------------------------------------
    def ladder_html(self, bids, asks, ct_label=None):
        t = self.win.colors
        mx = max([b[1] or 0 for b in bids] + [a[1] or 0 for a in asks] + [1])

        def bar(v, col):
            return "<span style='color:%s'>%s</span>" % (blend(col, 0.55, t["bg"]), "█" * int(round(14 * (v or 0) / mx)))

        def row(lv, col):
            ct = "" if ct_label is None else "<td align=right style='color:%s'>%s</td>" % (
                t["muted"], "" if lv[2] is None else (fmt_n(lv[2]) if isinstance(lv[2], int) else esc(str(lv[2]))))
            return ("<tr><td align=right style='color:%s'>%s</td><td align=right>%s</td><td>%s</td>%s</tr>"
                    % (col, fmt_px(lv[0]), fmt_n(lv[1]), bar(lv[1], col), ct))

        h = (T("<table cellspacing=0 cellpadding=2 style='font-family:Menlo;font-size:11px'><tr style='color:%s'>"
               "<th align=right>價格</th><th align=right>數量</th><th></th>%s</tr>")
             % (t["muted"], "" if ct_label is None else "<th align=right>%s</th>" % ct_label)).replace(
            "font-family:Menlo", MONO_CSS)
        h += "".join(row(a, t["ask"]) for a in reversed(asks))
        if bids and asks:
            h += "<tr><td colspan=4 align=center style='color:%s'>Spread %s · Mid %s</td></tr>" % (
                t["muted"], fmt_px(round(asks[0][0] - bids[0][0], 9)), fmt_px(round((asks[0][0] + bids[0][0]) / 2, 9)))
        h += "".join(row(b, t["bid"]) for b in bids)
        return h + "</table>"

    def levels_from_row(self, o):
        """Bid/ask levels embedded in MBP / CBBO / CMBP / BBO rows."""
        bids, asks, ct = [], [], None
        for i in range(10):
            k = "%02d" % i
            if "bid_px_" + k not in o:
                break
            c = "ct" if "bid_ct_" + k in o else ("pb" if "bid_pb_" + k in o else None)
            if c:
                ct = T("筆數") if c == "ct" else T("交易所")
            pv = (lambda x: PUBLISHERS.get(x, str(x)).split(".")[-1]) if c == "pb" else (lambda x: x)
            if o["bid_px_" + k] is not None:
                bids.append((o["bid_px_" + k], o["bid_sz_" + k], pv(o["bid_%s_%s" % (c, k)]) if c else None))
            if o["ask_px_" + k] is not None:
                asks.append((o["ask_px_" + k], o["ask_sz_" + k], pv(o["ask_%s_%s" % (c, k)]) if c else None))
        return bids, asks, ct

    def fields_html(self, o):
        t, ts = self.win.colors, self.win.tsfmt
        h = T("<h4>欄位</h4><table cellspacing=0 cellpadding=2 width=100%>")
        for c in self.model.allcols:
            v = o.get(c)
            k = self.model.kinds.get(c)
            extra = ""
            if v is None:
                s = "<span style='color:%s'>—</span>" % t["faint"]
            elif k == "ts":
                s = esc(ts.fmt(v, "dt") + " " + ts.tz_short)
                extra = "<br><span style='color:%s'>%s</span>" % (t["faint"], v)
            elif k == "flags":
                s = "%d = %s" % (v, reference.flag_names(v))
            elif k == "pub":
                s = "%s = %s" % (v, PUBLISHERS.get(v, "?"))
            elif k == "px":
                s = fmt_px(v)
            else:
                s = esc(str(v))
                et = reference.enum_text(self.win.job, c, v)
                if et:
                    s += " <span style='color:%s'>= %s</span>" % (t["muted"], esc(et))
            h += ("<tr><td style='color:%s' valign=top title='%s'>%s</td><td style='%s'>%s%s</td></tr>"
                  % (t["muted"], esc(reference.field_doc(c)), "#rec" if c == "_rec" else esc(c), MONO_CSS, s, extra))
        return h + "</table>"

    def raw_html(self, raw):
        t = self.win.colors
        lay, hx = raw["layout"], raw["hex"]
        owner = {b: i for i, f in enumerate(lay) for b in range(f[1], f[1] + f[2])}
        n = len(hx) // 2
        h = (T("<h4>原始位元組（%s · rtype 0x%02x · %d bytes · little-endian）</h4>"
               "<p style='color:%s'>同一欄位同一顏色；下表列出每個欄位的 offset、型別與原始整數值。</p>"
               "<pre style='font-family:Menlo;font-size:11px'>")
             % (esc(raw["cls"]), raw["rtype"], n, t["muted"])).replace("font-family:Menlo", MONO_CSS)
        for off in range(0, n, 16):
            h += "<span style='color:%s'>%04x</span>  " % (t["faint"], off)
            for b in range(off, min(n, off + 16)):
                i = owner.get(b)
                bg = field_color(lay[i][0], i, t["bg"]) if i is not None else t["bg"]
                h += "<span style='background-color:%s'>%s</span>%s" % (bg, hx[b * 2:b * 2 + 2], " " if b % 16 != 15 else "")
            h += "\n"
        h += "</pre><table cellspacing=0 cellpadding=2 style='font-size:11px'>"
        h += T("<tr style='color:%s'><th align=left>offset</th><th align=left>欄位</th><th align=left>型別</th>"
               "<th align=left>原始值</th></tr>") % t["muted"]
        for i, f in enumerate(lay):
            h += ("<tr><td style='{m}'>%d<span style='color:%s'>+%d</span></td>"
                  "<td style='{m};background-color:%s'>%s</td><td style='{m};color:%s'>%s</td>"
                  "<td style='{m}'>%s</td></tr>").replace("{m}", MONO_CSS) % (
                f[1], t["muted"], f[2], field_color(f[0], i, t["bg"]), esc(f[0]), t["muted"], esc(f[3]),
                "" if f[4] is None else esc(str(f[4])))
        return h + "</table>"

    def render(self):
        o = self.model.row_dict(self.row) if self.row is not None else None
        if o is None:
            return
        h = ""
        bids, asks, ct = self.levels_from_row(o)
        if "bid_px_00" in o:
            h += T("<h4>買賣盤（此筆之後）</h4>") + self.ladder_html(bids, asks, ct)
        h += self.book_html + self.fields_html(o)
        try:
            h += self.raw_html(self.win.job.raw(self.row))
        except Exception as e:  # noqa: BLE001
            h += "<p style='color:%s'>%s</p>" % (self.win.colors["ask"], esc(str(e)))
        sb = self.view.verticalScrollBar().value()
        self.view.setHtml(h)
        self.view.verticalScrollBar().setValue(sb)

    # ---- MBO book --------------------------------------------------------------------
    def load_book(self):
        r, job = self.row, self.win.job
        if r is None or job is None:
            return
        self.book_btn.setEnabled(False)
        self.book_btn.setText(T("重建中…"))

        def reset_button():
            self.book_btn.setEnabled(True)
            self.book_btn.setText(T("重建此刻的訂單簿（MBO）"))

        def done(b):
            reset_button()
            if r != self.row:
                return
            t = self.win.colors
            h = T("<h4>訂單簿（MBO 重建）</h4><p style='color:%s'>%s · 套用 %s 筆 MBO · %s 張掛單</p>") % (
                t["muted"], esc(b["symbol"] or str(b["instrument_id"])), fmt_n(b["applied"]), fmt_n(b["orders"]))
            if not b["safe"]:
                h += T("<p style='color:%s'>目前篩選可能漏掉此商品較早的訊息（時間/action/side/where），簿可能不正確。</p>") % t["warn"]
            if not b["had_clear"]:
                h += T("<p style='color:%s'>檔案開頭沒有清簿 (R)／快照，開始前已存在的掛單不在簿中。</p>") % t["warn"]
            self.book_html = h + self.ladder_html(b["bids"], b["asks"], T("掛單數"))
            self.render()

        def fail(e):
            reset_button()
            self.win.show_error(e)

        run_bg(book_at, job, r, 15, done=done, fail=fail)
