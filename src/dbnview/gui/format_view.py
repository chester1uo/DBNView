"""Format-guide tab: what the open file contains, its record layout, metadata header and enum meanings."""
from PySide6 import QtWidgets

from .. import reference
from ..engine import metadata_layout
from ..i18n import T
from .common import MONO_CSS, esc, field_color, fmt_n


class FormatView(QtWidgets.QTextBrowser):
    def __init__(self, win):
        super().__init__()
        self.win = win

    def render(self, fi, meta):
        if not meta:
            self.setHtml(T("<p style='color:gray'>先開啟一個檔案。</p>"))
            return
        t, ts = self.win.colors, self.win.tsfmt
        m, rec, hl = meta["metadata"], meta["record"], metadata_layout(fi.md, T)
        mono = lambda s: s.replace("font-family:Menlo", MONO_CSS)
        sd = reference.schema_doc(m["schema"], T("混合 schema（檔案內有多種 rtype）。") if not m["schema"] else "")
        h = T("<h2>這個檔案是什麼</h2><p><b>%s</b> 的 <b>%s</b> 資料。%s</p>") % (
            esc(m["dataset"]), esc(m["schema"] or "mixed"), esc(sd))
        h += (T("<p>symbology：<code>%s</code> → <code>%s</code>。%s。檔內每筆紀錄只帶數字 <code>instrument_id</code>，"
                "要靠檔頭裡的 mappings 對回代碼（本檔 %s 組）。</p>")) % (
            esc(m["stype_in"] or "—"), esc(m["stype_out"]), esc(reference.stype_doc(m["stype_in"] or "")),
            fmt_n(m["n_mappings"]))
        box = "<td style='border:1px solid %s;padding:8px' width=30%%><b>%s</b><br><span style='color:%s'>%s</span></td>"
        h += "<table cellspacing=6><tr>%s<td>→</td>%s<td>→</td>%s</tr></table>" % (
            box % (t["line"], T(".zst 外層"), t["muted"], T("Zstandard 壓縮整條串流，不能隨機存取，只能從頭解")),
            box % (t["line"], "Metadata header", t["muted"], "%s bytes · DBN v%d" % (fmt_n(m["header_bytes"]), m["version"])),
            box % (t["line"], "Records", t["muted"],
                   (T("%s 每筆 %d bytes，一筆接一筆") % (esc(rec["cls"]), rec["size"])) if rec else "—"))
        if rec:
            h += self._record_layout(rec, t)
        h += mono(T("<h2>Metadata header（本檔實際值）</h2><p style='color:%s'>解壓後的串流開頭：\"DBN\" + 版本 byte + 4-byte 長度，"
                    "接著是下列欄位。v1 的 symbol 字串固定 22 bytes，v2/v3 為 71 bytes（由 symbol_cstr_len 指定）。</p>")) % t["muted"]
        h += T("<table cellspacing=0 cellpadding=3 width=100%%><tr style='color:%s'><th align=left>offset</th><th align=left>bytes</th>"
               "<th align=left>型別</th><th align=left>欄位</th><th align=left>值</th></tr>") % t["muted"]
        for f in hl:
            v = "" if f[4] is None else str(f[4])
            if f[0] in ("start", "end") and v.isdigit():
                v = "%s  (%s %s)" % (v, ts.fmt(int(v), "dt"), ts.tz_short)
            h += ("<tr><td style='{m}'>%d</td><td style='{m}'>%s</td><td style='{m};color:%s'>%s</td>"
                  "<td style='{m}'>%s</td><td style='{m}'>%s</td></tr>").replace("{m}", MONO_CSS) % (
                f[1], fmt_n(f[2]), t["muted"], esc(f[3]), esc(f[0]), esc(v))
        h += T("</table><h2>列舉值</h2><table cellspacing=12><tr>")
        tables = reference.enums() + [("rtype", [("0x%02x" % a, b) for a, b in reference.RTYPE_DOC])]
        for i, (title, rows) in enumerate(tables):
            if i and i % 3 == 0:
                h += "</tr><tr>"
            h += "<td valign=top><h3>%s</h3><table cellspacing=0 cellpadding=2>%s</table></td>" % (esc(title), "".join(
                "<tr><td style='%s' valign=top>%s</td><td style='color:%s'>%s</td></tr>" % (MONO_CSS, esc(a), t["muted"], esc(b))
                for a, b in rows))
        h += T("</tr></table><h2>常見陷阱</h2><ul>") + "".join("<li>%s</li>" % esc(x) for x in reference.tips()) + "</ul>"
        self.setHtml(h)

    def _record_layout(self, rec, t):
        lay = rec["layout"]
        h = T("<h2>Record layout：%s（rtype 0x%02x，%d bytes）</h2>") % (esc(rec["cls"]), rec["rtype"], rec["size"])
        h += "<table cellspacing=0 cellpadding=3 width=100%><tr>" + "".join(
            "<td width=%.2f%% style='background-color:%s;%s;font-size:10px' align=center>%s</td>" % (
                100.0 * f[2] / rec["size"], field_color(f[0], i, t["bg"]), MONO_CSS, esc(f[0]) if f[2] >= 4 else "")
            for i, f in enumerate(lay)) + "</tr></table>"
        h += (T("<p style='color:%s'>所有紀錄都以 16 bytes 的共同 header 開頭（length, rtype, publisher_id, instrument_id, ts_event），"
                "之後依 rtype 不同。整數都是 little-endian；價格是 int64 定點數（÷1e9）；時間是 UNIX 奈秒。"
                "在表格點任一列，右側明細會顯示該筆的實際位元組。</p>")) % t["muted"]
        h += T("<table cellspacing=0 cellpadding=3 width=100%%><tr style='color:%s'><th align=left>offset</th><th align=left>bytes</th>"
               "<th align=left>型別</th><th align=left>欄位</th><th align=left>說明</th></tr>") % t["muted"]
        for i, f in enumerate(lay):
            h += ("<tr><td style='{m}'>%d</td><td style='{m}'>%d</td><td style='{m}'>%s</td>"
                  "<td style='{m};background-color:%s'>%s</td><td style='color:%s'>%s</td></tr>").replace("{m}", MONO_CSS) % (
                f[1], f[2], esc(f[3]), field_color(f[0], i, t["bg"]), esc(f[0]), t["muted"], esc(reference.field_doc(f[0])))
        return h + "</table>"
