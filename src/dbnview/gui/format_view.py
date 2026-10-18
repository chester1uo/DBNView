"""Format-guide tab: what the open file contains, its record layout, metadata header and enum meanings."""
from PySide6 import QtWidgets

from .. import reference
from ..display import pretty_field
from ..engine import metadata_layout
from ..i18n import T
from .common import MONO_CSS, esc, field_color, fmt_n


class FormatView(QtWidgets.QTextBrowser):
    def __init__(self, win):
        super().__init__()
        self.win = win

    def render(self, fi, meta):
        if not meta:
            self.setHtml(T("<p style='color:gray'>Open a file first.</p>"))
            return
        t, ts = self.win.colors, self.win.tsfmt
        m, rec, hl = meta["metadata"], meta["record"], metadata_layout(fi.md, T)
        mono = lambda s: s.replace("font-family:Menlo", MONO_CSS)
        sd = reference.schema_doc(m["schema"],
                                  T("Mixed schema (the file contains multiple rtypes).") if not m["schema"] else "")
        h = T("<h2>What This File Is</h2><p>Dataset <b>%s</b>, schema <b>%s</b>. %s</p>") % (
            esc(m["dataset"]), esc(m["schema"] or "mixed"), esc(sd))
        h += (T("<p>symbology: <code>%s</code> → <code>%s</code>. %s. Each record in the file carries only "
                "a numeric <code>instrument_id</code>; the mappings in the header map it back to a symbol "
                "(%s in this file).</p>")) % (
            esc(m["stype_in"] or "—"), esc(m["stype_out"]), esc(reference.stype_doc(m["stype_in"] or "")),
            fmt_n(m["n_mappings"]))
        box = "<td style='border:1px solid %s;padding:8px' width=30%%><b>%s</b><br><span style='color:%s'>%s</span></td>"
        h += "<table cellspacing=6><tr>%s<td>→</td>%s<td>→</td>%s</tr></table>" % (
            box % (t["line"], T(".zst Wrapper"), t["muted"], T("Zstandard compresses the whole stream; no random "
                                                               "access, decode from the start only")),
            box % (t["line"], "Metadata header", t["muted"], "%s bytes · DBN v%d" % (fmt_n(m["header_bytes"]), m["version"])),
            box % (t["line"], "Records", t["muted"],
                   (T("%s, %d bytes each, back to back") % (esc(rec["cls"]), rec["size"])) if rec else "—"))
        if rec:
            h += self._record_layout(rec, t)
        h += mono(T("<h2>Metadata Header (Actual Values in This File)</h2><p style='color:%s'>The "
                    "decompressed stream starts with \"DBN\" + version byte + 4-byte length, followed by the "
                    "fields below. symbol strings are fixed at 22 bytes in v1 and 71 bytes in v2/v3 (set "
                    "by symbol_cstr_len).</p>")) % t["muted"]
        h += T("<table cellspacing=0 cellpadding=3 width=100%%><tr style='color:%s'><th "
               "align=left>Offset</th><th align=left>Bytes</th><th align=left>Type</th><th "
               "align=left>Field</th><th align=left>Value</th></tr>") % t["muted"]
        for f in hl:
            v = "" if f[4] is None else str(f[4])
            if f[0] in ("start", "end") and v.isdigit():
                v = "%s  (%s %s)" % (v, ts.fmt(int(v), "dt"), ts.tz_short)
            h += ("<tr><td style='{m}'>%d</td><td style='{m}'>%s</td><td style='{m};color:%s'>%s</td>"
                  "<td style='{m}'>%s</td><td style='{m}'>%s</td></tr>").replace("{m}", MONO_CSS) % (
                f[1], fmt_n(f[2]), t["muted"], esc(f[3]), esc(f[0]), esc(v))
        h += T("</table><h2>Enum Values</h2><table cellspacing=12><tr>")
        tables = reference.enums() + [("rtype", [("0x%02x" % a, b) for a, b in reference.RTYPE_DOC])]
        for i, (title, rows) in enumerate(tables):
            if i and i % 3 == 0:
                h += "</tr><tr>"
            h += "<td valign=top><h3>%s</h3><table cellspacing=0 cellpadding=2>%s</table></td>" % (esc(title), "".join(
                "<tr><td style='%s' valign=top>%s</td><td style='color:%s'>%s</td></tr>" % (MONO_CSS, esc(a), t["muted"], esc(b))
                for a, b in rows))
        h += T("</tr></table><h2>Common Pitfalls</h2><ul>")
        h += "".join("<li>%s</li>" % esc(x) for x in reference.tips()) + "</ul>"
        self.setHtml(h)

    def _record_layout(self, rec, t):
        lay = rec["layout"]
        h = T("<h2>Record Layout: %s (rtype 0x%02x, %d bytes)</h2>") % (esc(rec["cls"]), rec["rtype"], rec["size"])
        h += "<table cellspacing=0 cellpadding=3 width=100%><tr>" + "".join(
            "<td width=%.2f%% style='background-color:%s;%s;font-size:10px' align=center>%s</td>" % (
                100.0 * f[2] / rec["size"], field_color(f[0], i, t["bg"]), MONO_CSS, esc(pretty_field(f[0])) if f[2] >= 4 else "")
            for i, f in enumerate(lay)) + "</tr></table>"
        h += (T("<p style='color:%s'>Every record starts with a common 16-byte header (length, rtype, "
                "publisher_id, instrument_id, ts_event); the rest depends on rtype. Integers are "
                "little-endian; prices are int64 fixed-point (÷1e9); times are UNIX nanoseconds. Click any "
                "row in the table and the detail panel on the right shows that record's actual "
                "bytes.</p>")) % t["muted"]
        h += T("<table cellspacing=0 cellpadding=3 width=100%%><tr style='color:%s'><th "
               "align=left>Offset</th><th align=left>Bytes</th><th align=left>Type</th><th "
               "align=left>Field</th><th align=left>Description</th></tr>") % t["muted"]
        for i, f in enumerate(lay):
            h += ("<tr><td style='{m}'>%d</td><td style='{m}'>%d</td><td style='{m}'>%s</td>"
                  "<td style='{m};background-color:%s'>%s</td><td style='color:%s'>%s</td></tr>").replace("{m}", MONO_CSS) % (
                f[1], f[2], esc(f[3]), field_color(f[0], i, t["bg"]),
                "%s <span style='color:%s'>%s</span>" % (esc(pretty_field(f[0])), t["muted"], esc(f[0])),
                t["muted"], esc(reference.field_doc(f[0])))
        return h + "</table>"
