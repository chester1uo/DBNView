"""Terminal UI: `dbnview-tui [file | dir | ssh://host/path]` (also `python -m dbnview.tui`).

Keys: o open · s scan · x stop · / filter · f sidebar · enter detail · b MBO book · c chart mode
      i technical indicator · t time zone · 1-6 tabs · e export CSV · q quit
"""
import argparse
import csv
import os

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static, TabbedContent, TabPane

from .. import __version__, i18n, reference
from ..analysis import options
from ..analysis.book import book_at
from ..display import TsFmt, display_name, fmt_bytes
from ..engine import FileInfo, Job, fmt_ts, get_tz, is_remote, list_dir, parse_time
from ..i18n import T
from . import views
from .table import RecordTable

TIMEZONES = ["America/New_York", "UTC", "America/Chicago", "Europe/London", "Asia/Hong_Kong", "Asia/Tokyo"]
CHART_MODES = ["candles", "quotes", "flow"]
CHART_TITLES = {"candles": "Candles", "quotes": "Bid / Ask", "flow": "Order Flow"}


class OpenScreen(ModalScreen):
    """Pick a .dbn / .dbn.zst file from a local or ssh:// directory."""

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel"), Binding("backspace", "up", "Up", show=False)]
    DEFAULT_CSS = """
    OpenScreen { align: center middle; }
    #box { width: 90%; height: 80%; border: round $accent; background: $surface; padding: 0 1; }
    #entries { height: 1fr; }
    """

    def __init__(self, start):
        super().__init__()
        self.dir = start

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Label(T("開啟檔案…") + "  (Enter · Backspace ↑ · Esc)")
            yield Input(self.dir, id="dir")
            yield ListView(id="entries")

    def on_mount(self):
        self.load(self.dir)

    @work(thread=True, exclusive=True)
    def load(self, d):
        try:
            ents = list_dir(d)
            self.app.call_from_thread(self.fill, d, ents)
        except Exception as e:  # noqa: BLE001
            self.app.call_from_thread(self.app.notify, str(e), severity="error")

    def fill(self, d, ents):
        self.dir = d
        self.query_one("#dir", Input).value = d
        lv = self.query_one("#entries", ListView)
        lv.clear()
        for e in ents:
            label = ("▸ " + e["name"] + "/") if e["dir"] else ("  %-60s %10s" % (e["name"], fmt_bytes(e["size"])))
            item = ListItem(Label(label))
            item.entry = e
            lv.append(item)
        lv.focus()

    def _join(self, name):
        sep = "/" if is_remote(self.dir) or "/" in self.dir else os.sep
        return self.dir.rstrip("/\\") + sep + name

    def on_input_submitted(self, event):
        self.load(event.value.strip())

    def on_list_view_selected(self, event):
        e = event.item.entry
        p = self._join(e["name"])
        if e["dir"]:
            self.load(p)
        else:
            self.dismiss(p)

    def action_up(self):
        if self.focused is self.query_one("#dir", Input):
            return
        d = self.dir.rstrip("/\\")
        cut = max(d.rfind("/"), d.rfind("\\"))
        self.load(d[:cut] or "/")


class DBNViewTUI(App):
    TITLE = "DBNView"
    CSS = """
    #sidebar { width: 44; border-right: solid $panel; padding: 0 1; }
    #sidebar Input { margin: 0 0 0 0; }
    #meta { height: auto; margin-bottom: 1; }
    #progress { height: auto; margin-top: 1; }
    RecordTable { height: 1fr; }
    #chart_body { height: 1fr; }
    .pane { padding: 0 1; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"), Binding("o", "open", "Open"), Binding("s", "scan", "Scan"),
        Binding("x", "stop", "Stop"), Binding("slash", "focus_filter", "Filter"),
        Binding("f", "toggle_sidebar", "Sidebar"), Binding("b", "book", "Book"), Binding("c", "chart_mode", "Chart"),
        Binding("i", "next_indicator", "Indicator"), Binding("t", "next_tz", "TZ"), Binding("e", "export", "CSV"), Binding("enter", "show_detail", "Detail", show=False),
        *[Binding(str(i + 1), "tab(%d)" % i, show=False) for i in range(6)],
    ]
    TABS = ["table", "detail", "chart", "stats", "format", "iv"]

    def __init__(self, path=None, tz="America/New_York"):
        super().__init__()
        self.path = path
        self.tsfmt = TsFmt()
        self.tsfmt.set(tz, "dt")
        self.fi = self.meta = self.job = self.status = self.stats = None
        self.row = 0
        self.book = None
        self.chart_mode = 0
        self.indicator = 0
        self.iv_surface = None

    # ---- layout ------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with VerticalScroll(id="sidebar"):
                yield Static(T("尚未開啟檔案"), id="meta")
                yield Input(placeholder="Symbol (substring, or exact$)", id="f_symbol")
                yield Input(placeholder="instrument_id, …", id="f_iids")
                yield Input(placeholder=T("09:30 或 2026-01-02 09:30:00"), id="f_t0")
                yield Input(placeholder=T("10:00（不含）"), id="f_t1")
                yield Input(placeholder="Where: size >= 10 and side == 'B'", id="f_where")
                yield Input("1000000", placeholder="Max rows", id="f_cap")
                yield Button(T("掃描"), id="scan", variant="primary")
                yield Static("—", id="progress")
            with TabbedContent(id="tabs"):
                with TabPane(T("表格"), id="table"):
                    yield RecordTable(self.fmt, id="records")
                with TabPane(T("明細"), id="detail"):
                    yield VerticalScroll(Static(id="detail_body"), classes="pane")
                with TabPane(T("圖表"), id="chart"):
                    yield Static(id="chart_body", classes="pane")
                with TabPane(T("統計"), id="stats"):
                    yield VerticalScroll(Static(id="stats_body"), classes="pane")
                with TabPane(T("格式說明"), id="format"):
                    yield VerticalScroll(Static(id="format_body"), classes="pane")
                with TabPane(T("IV 曲面"), id="iv"):
                    with Vertical(classes="pane"):
                        yield Input(placeholder=T("時間") + " (15:45) · Enter", id="iv_time")
                        yield VerticalScroll(Static(id="iv_body"))
        yield Footer()

    def on_mount(self):
        self.sub_title = "v" + __version__
        self.set_interval(0.25, self.poll)
        if self.path:
            if is_remote(self.path) or os.path.isdir(self.path):
                self.push_screen(OpenScreen(self.path), self.open_path)
            else:
                self.open_path(self.path)

    def fmt(self, ns):
        return self.tsfmt.fmt(ns)

    def fmt_short(self, x):
        import datetime as dt
        return dt.datetime.fromtimestamp(float(x), get_tz(self.tsfmt.tz)).strftime("%H:%M:%S")

    # ---- open / scan ---------------------------------------------------------------------
    def action_open(self):
        start = os.path.dirname(self.fi.path) if self.fi and not is_remote(self.fi.path) else os.getcwd()
        self.push_screen(OpenScreen(start), self.open_path)

    def open_path(self, path):
        if not path:
            return
        self.notify(T("讀取檔頭… %s") % path)
        self._load_file(path)

    @work(thread=True, exclusive=True, group="open")
    def _load_file(self, path):
        try:
            fi = FileInfo.get(path if is_remote(path) else os.path.abspath(os.path.expanduser(path)))
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(self.notify, "%s: %s" % (type(e).__name__, e), severity="error", timeout=10)
            return
        self.call_from_thread(self.on_file, fi)

    def on_file(self, fi):
        self.fi, self.meta = fi, fi.to_json()
        self.title = "DBNView — " + display_name(fi.path)
        self.query_one("#meta", Static).update(views.metadata_view(self.meta, self.fmt))
        self.query_one("#format_body", Static).update(views.format_view(fi, self.meta))
        self.action_scan()

    def query_dict(self):
        v = lambda i: self.query_one("#" + i, Input).value.strip()
        syms = [s for s in v("f_symbol").split(",") if s.strip()]
        cap = v("f_cap")
        return {"symbols": syms, "iids": v("f_iids"), "t0": v("f_t0"), "t1": v("f_t1"), "tz": self.tsfmt.tz,
                "where": v("f_where"), "cap": int(cap) if cap.isdigit() else 1_000_000}

    def action_scan(self):
        if self.fi is None:
            return
        if self.job is not None:
            self.job.cancelled = True
        try:
            self.job = Job(self.fi.path, self.query_dict())
        except Exception as e:  # noqa: BLE001
            self.notify("%s: %s" % (type(e).__name__, e), severity="error", timeout=10)
            return
        self.status = self.stats = self.book = self.iv_surface = None
        self._final_done = False
        table = self.query_one("#records", RecordTable)
        table.set_job(self.job)
        table.focus()

    def action_stop(self):
        if self.job is not None:
            self.job.cancelled = True

    def on_button_pressed(self, event):
        if event.button.id == "scan":
            self.action_scan()

    def on_input_submitted(self, event):
        if event.input.id == "iv_time":
            self.compute_iv()
        elif event.input.id and event.input.id.startswith("f_"):
            self.action_scan()

    def poll(self):
        job = self.job
        if job is None or (self.status is not None and self.status["done"] and job.done and self._final_done):
            return
        st = job.status(with_stats=job.done)
        self.status = st
        if st.get("stats"):
            self.stats = st["stats"]
        self.query_one("#records", RecordTable).update_from_status(st)
        self.query_one("#progress", Static).update(views.progress_text(st))
        self._final_done = job.done
        if job.done:
            self.query_one("#stats_body", Static).update(views.stats_view(st, self.stats, self.fmt))
            self.refresh_active()

    _final_done = False

    # ---- detail / charts ---------------------------------------------------------------------
    def on_record_table_row_changed(self, message):
        self.row = message.row
        self.book = None
        if self.query_one("#tabs", TabbedContent).active in ("detail", "chart"):
            self.refresh_active()

    def on_tabbed_content_tab_activated(self, event):
        self.refresh_active()

    def current_row(self):
        table = self.query_one("#records", RecordTable)
        return table.row(self.row)

    def refresh_active(self):
        active = self.query_one("#tabs", TabbedContent).active
        if self.job is None:
            return
        if active == "detail":
            o = self.current_row()
            if o is not None:
                self.query_one("#detail_body", Static).update(
                    views.detail_view(self.job, self.row, o, self.status["kinds"] if self.status else {}, self.fmt,
                                      self.book))
        elif active == "chart":
            o = self.current_row()
            iid = o.get("instrument_id") if o else (self.stats["top"][0][0] if self.stats and self.stats["top"] else None)
            if iid is not None:
                self._draw_chart(int(iid), CHART_MODES[self.chart_mode])
        elif active == "stats":
            self.query_one("#stats_body", Static).update(views.stats_view(self.status, self.stats, self.fmt))
        elif active == "iv" and self.iv_surface is None and self.job.done:
            self.compute_iv()

    @work(thread=True, exclusive=True, group="chart")
    def _draw_chart(self, iid, mode):
        body = self.query_one("#chart_body", Static)
        w, h = max(40, body.size.width - 2), max(12, body.size.height - 2)
        try:
            r = views.chart_view(self.job, iid, mode, w, h, self.fmt_short, get_tz(self.tsfmt.tz),
                                 views.TUI_INDICATORS[self.indicator])
        except Exception as e:  # noqa: BLE001
            r = "%s: %s" % (type(e).__name__, e)
        self.call_from_thread(body.update, r)

    def action_chart_mode(self):
        self.chart_mode = (self.chart_mode + 1) % len(CHART_MODES)
        self.notify("Chart: " + CHART_TITLES[CHART_MODES[self.chart_mode]])
        self.query_one("#tabs", TabbedContent).active = "chart"
        self.refresh_active()

    def action_next_indicator(self):
        self.indicator = (self.indicator + 1) % len(views.TUI_INDICATORS)
        key = views.TUI_INDICATORS[self.indicator]
        self.notify("Indicator: " + ("None" if key == "none" else views.ind.label(key)))
        self.chart_mode = 0
        self.query_one("#tabs", TabbedContent).active = "chart"
        self.refresh_active()

    def action_show_detail(self):
        if self.focused is self.query_one("#records", RecordTable):
            self.query_one("#tabs", TabbedContent).active = "detail"

    def action_book(self):
        if self.job is None:
            return
        o = self.current_row()
        if o is None or "order_id" not in o:
            self.notify("The order-book rebuild needs MBO data", severity="warning")
            return
        self._load_book(self.row)

    @work(thread=True, exclusive=True, group="book")
    def _load_book(self, row):
        b = book_at(self.job, row, 15)
        self.book = b
        self.call_from_thread(setattr, self.query_one("#tabs", TabbedContent), "active", "detail")
        self.call_from_thread(self.refresh_active)

    # ---- IV ------------------------------------------------------------------------------------
    def compute_iv(self):
        if self.job is None or not options.is_option_data(self.job):
            self.query_one("#iv_body", Static).update(
                T("這個檔案看起來不是期權資料（找不到 OSI 期權代碼，例如 SPY   260116C00690000）。"))
            return
        text = self.query_one("#iv_time", Input).value.strip()
        try:
            t_ns = parse_time(text, self.tsfmt.tz, int(self.status["tmin"])) if text else int(self.status["tmax"])
        except Exception as e:  # noqa: BLE001
            self.notify(T("時間格式錯誤：%s") % e, severity="error")
            return
        self.query_one("#iv_body", Static).update(T("計算中…"))
        self._iv(t_ns)

    @work(thread=True, exclusive=True, group="iv")
    def _iv(self, t_ns):
        ch = options.chain(self.job)
        s = options.surface(self.job, t_ns, options.roots(ch)[0], ch=ch, max_age_s=1800)
        self.iv_surface = s
        body = self.query_one("#iv_body", Static)
        r = views.iv_view(s, max(60, body.size.width - 2), max(24, self.size.height - 8))
        self.call_from_thread(body.update, r)

    # ---- misc ------------------------------------------------------------------------------------
    def action_focus_filter(self):
        self.query_one("#f_symbol", Input).focus()

    def action_toggle_sidebar(self):
        sb = self.query_one("#sidebar")
        sb.display = not sb.display

    def action_tab(self, i):
        self.query_one("#tabs", TabbedContent).active = self.TABS[i]

    def action_next_tz(self):
        i = (TIMEZONES.index(self.tsfmt.tz) + 1) % len(TIMEZONES) if self.tsfmt.tz in TIMEZONES else 0
        self.tsfmt.set(TIMEZONES[i], "dt")
        self.notify(TIMEZONES[i])
        self.query_one("#records", RecordTable).refresh()
        if self.meta:
            self.query_one("#meta", Static).update(views.metadata_view(self.meta, self.fmt))
        self.refresh_active()

    def action_export(self):
        if self.job is None or not self.job.n:
            return
        name = display_name(self.fi.path).replace(".dbn.zst", "").replace(".dbn", "") + ".csv"
        self._export(os.path.abspath(name))

    @work(thread=True, group="export")
    def _export(self, path):
        job, tz = self.job, get_tz(self.tsfmt.tz)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(job.columns)
            for off in range(0, job.n, 50000):
                for r in job.rows(off, 50000)["rows"]:
                    w.writerow([fmt_ts(v, tz) if job.kinds.get(c) == "ts" and v is not None else ("" if v is None else v)
                                for c, v in zip(job.columns, r)])
        self.call_from_thread(self.notify, T("已匯出 %s 列 → %s") % ("{:,}".format(job.n), path))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dbnview-tui", description="Terminal viewer for Databento DBN files")
    ap.add_argument("path", nargs="?", help="file, directory or ssh://host/path")
    ap.add_argument("--tz", default="America/New_York", help="display time zone (t cycles in the app)")
    ap.add_argument("--lang", default=None, help="zh_Hant | zh_Hans | en | ja | de | ko | es (default: system)")
    a = ap.parse_args(argv)
    i18n.set_lang(a.lang or i18n.system_lang())
    reference.set_lang(i18n.get_lang())
    DBNViewTUI(a.path or os.getcwd(), a.tz).run()


if __name__ == "__main__":
    main()
