"""Statistics tab: record/action/side distributions and the busiest instruments."""
from PySide6 import QtCore, QtWidgets

from ..i18n import T
from .common import MONO_CSS, esc, fmt_n


class StatsView(QtWidgets.QTextBrowser):
    """Emits filterRequested(iid) / chartRequested(iid) when a link in the top-instrument table is clicked."""

    filterRequested = QtCore.Signal(int)
    chartRequested = QtCore.Signal(int)

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_link)

    def _on_link(self, url):
        kind, _, iid = url.toString().partition(":")
        if kind == "filter":
            self.filterRequested.emit(int(iid))
        elif kind == "chart":
            self.chartRequested.emit(int(iid))

    def hbars(self, d):
        t = self.win.colors
        e = sorted((d or {}).items(), key=lambda kv: -kv[1])
        if not e:
            return "<p style='color:gray'>—</p>"
        mx, tot = e[0][1], sum(v for _, v in e)
        return "<table cellspacing=0 cellpadding=2>" + "".join(
            "<tr><td style='%s'>%s</td><td><span style='color:%s'>%s</span></td>"
            "<td align=right style='color:%s'>%s · %.1f%%</td></tr>" % (
                MONO_CSS, esc(str(k)), t["accent"], "█" * max(1, int(24 * v / mx)), t["muted"], fmt_n(v), 100 * v / tot)
            for k, v in e) + "</table>"

    def render(self, st, s):
        if not st or not s:
            self.setHtml(T("<p style='color:gray'>No statistics yet</p>"))
            return
        t, ts = self.win.colors, self.win.tsfmt
        span = "%s<br>%s" % (ts.fmt(st["tmin"], "dt"), ts.fmt(st["tmax"], "dt")) if st["tmin"] else "—"
        partial = T("(scanning)") if not st["done"] else (T("(scanned part only)") if st["truncated"] else "")
        tile = lambda label, val: ("<td style='padding:8px 18px 8px 0' valign=top><span style='color:%s'>%s</span><br>"
                                   "<span style='font-size:20px;font-weight:600'>%s</span></td>") % (t["muted"], label, val)
        h = "<table><tr>%s%s%s%s</tr></table>" % (
            tile(T("Matching Filter ") + partial, fmt_n(st["matched"])), tile(T("Records Read"), fmt_n(st["seen"])),
            tile(T("Instruments"), fmt_n(s["n_instruments"])),
            T("<td valign=top><span style='color:%s'>Time range (%s)</span><br><span "
              "style='font-family:Menlo'>%s</span></td>")
            .replace("font-family:Menlo", MONO_CSS) % (t["muted"], ts.tz_short, span))
        h += ("<table width=100%%><tr><td valign=top><h3>%s</h3>%s</td><td valign=top><h3>%s</h3>%s</td>"
              "<td valign=top><h3>%s</h3>%s</td></tr></table>") % (
            T("Record Type"), self.hbars(s["rtype"]), T("Action"), self.hbars(s["action"]),
            T("Side"), self.hbars(s["side"]))
        h += T("<h3>Top %d Instruments (by Record Count)</h3>") % len(s["top"])
        h += "<table cellspacing=0 cellpadding=3 width=100%>"
        h += T("<tr style='color:%s'><th align=left>Symbol</th><th align=left>Instrument ID</th><th "
               "align=right>Records</th><th align=right>Share</th><th></th></tr>") % t["muted"]
        row = T("<tr><td style='font-family:Menlo'>%s</td><td style='font-family:Menlo'>%d</td><td "
                "align=right>%s</td><td align=right>%.2f%%</td><td><a href='filter:%d'>Filter</a>  <a "
                "href='chart:%d'>Chart</a></td></tr>"
                ).replace("font-family:Menlo", MONO_CSS)
        for iid, c, sym in s["top"]:
            h += row % (esc((sym or "—").replace(" ", " ")), iid, fmt_n(c), 100 * c / max(1, st["matched"]), iid, iid)
        self.setHtml(h + "</table>")
