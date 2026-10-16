"""Virtual record table for the terminal: renders only visible lines, so millions of rows scroll smoothly."""
import collections

from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.strip import Strip

from .. import reference
from ..engine import PUBLISHERS

PAGE = 400
WIDTH = {"ts": 29, "px": 12, "sym": 22, "chr": 6, "flags": 5, "pub": 6, "rec": 9, "str": 20}

STYLE_HEAD = Style(bold=True, reverse=True)
STYLE_CURSOR = Style(reverse=True)
STYLE_NIL = Style(dim=True)
STYLE_BID = Style(color="green")
STYLE_ASK = Style(color="red")
STYLE_MUTED = Style(dim=True)
ACTION_STYLE = {"A": Style(color="cyan"), "C": Style(color="red"), "M": Style(color="yellow"),
                "T": Style(color="bright_yellow", bold=True), "F": Style(color="yellow"), "R": Style(color="magenta")}


def fmt_px(v):
    s = "%.9f" % v
    return s.rstrip("0").rstrip(".")


class RecordTable(ScrollView, can_focus=True):
    """Scrollable table over a scan job's loaded rows. Posts RowChanged when the cursor moves."""

    BINDINGS = [
        Binding("up", "move(-1)", show=False), Binding("down", "move(1)", show=False),
        Binding("k", "move(-1)", show=False), Binding("j", "move(1)", show=False),
        Binding("pageup", "page(-1)", show=False), Binding("pagedown", "page(1)", show=False),
        Binding("home", "jump(0)", show=False), Binding("end", "jump(-1)", show=False),
        Binding("g", "jump(0)", show=False), Binding("G", "jump(-1)", show=False),
        Binding("left", "hscroll(-8)", show=False), Binding("right", "hscroll(8)", show=False),
    ]

    class RowChanged(Message):
        def __init__(self, row):
            self.row = row
            super().__init__()

    cursor = reactive(0)

    def __init__(self, fmt_ts, **kw):
        super().__init__(**kw)
        self.fmt_ts = fmt_ts  # callable(ns) -> str in the chosen time zone
        self.job = None
        self.n = 0
        self.cols, self.kinds, self.widths = [], {}, []
        self.hidden = {"length"}
        self.pages = collections.OrderedDict()

    # ---- data -------------------------------------------------------------------------
    def set_job(self, job):
        self.job, self.n = job, 0
        self.pages.clear()
        self.cols = []
        self.cursor = 0
        self.scroll_to(0, 0, animate=False)
        self._resize()

    def update_from_status(self, st):
        cols = [c for c in st["columns"] if c not in self.hidden]
        if cols != self.cols:
            self.cols, self.kinds = cols, st["kinds"]
            self.widths = [max(len(c if c != "_rec" else "#rec"), WIDTH.get(self.kinds.get(c), 11)) for c in cols]
            self.pages.clear()
        if st["rows"] != self.n:
            self.pages.pop(self.n // PAGE, None)  # the last page may have been partial
            self.n = st["rows"]
        self._resize()
        self.refresh()

    def _resize(self):
        self.virtual_size = Size(sum(w + 1 for w in self.widths) or 1, self.n + 1)

    def row(self, r):
        if self.job is None or not (0 <= r < self.n):
            return None
        p = r // PAGE
        pg = self.pages.get(p)
        if pg is None:
            res = self.job.rows(p * PAGE, PAGE, self.job.columns)
            pg = (res["columns"], res["rows"])
            self.pages[p] = pg
            if len(self.pages) > 200:
                self.pages.popitem(last=False)
        cols, rows = pg
        i = r - p * PAGE
        return dict(zip(cols, rows[i])) if i < len(rows) else None

    # ---- rendering ---------------------------------------------------------------------
    def cell(self, c, v):
        k = self.kinds.get(c)
        if v is None:
            return "—", STYLE_NIL
        if k == "ts":
            return self.fmt_ts(v), None
        if k == "px":
            st = STYLE_BID if c.startswith("bid_px") else STYLE_ASK if c.startswith("ask_px") else None
            return fmt_px(v), st
        if k == "flags":
            return reference.flag_short(v) or "·", STYLE_MUTED
        if k == "pub":
            name = PUBLISHERS.get(v)
            return (name.split(".")[-1] if name else str(v)), STYLE_MUTED
        if c == "side":
            return str(v), STYLE_BID if v == "B" else STYLE_ASK if v == "A" else STYLE_MUTED
        if c == "action":
            return str(v), ACTION_STYLE.get(v)
        if c in ("_rec", "rtype"):
            return str(v), STYLE_MUTED
        return str(v), None

    def render_line(self, y):
        sx, sy = self.scroll_offset
        width = self.size.width
        if y == 0:
            segs = []
            for c, w in zip(self.cols, self.widths):
                label = "#rec" if c == "_rec" else c
                segs.append(Segment(label[:w].ljust(w) + " ", STYLE_HEAD))
            return Strip(segs).crop_extend(sx, sx + width, STYLE_HEAD)
        r = sy + y - 1
        o = self.row(r)
        if o is None:
            return Strip.blank(width)
        segs = []
        for c, w in zip(self.cols, self.widths):
            text, st = self.cell(c, o.get(c))
            right = self.kinds.get(c) in ("px", "int", "rec")
            text = (text[:w].rjust(w) if right else text[:w].ljust(w)) + " "
            segs.append(Segment(text, st))
        strip = Strip(segs).crop_extend(sx, sx + width, None)
        if r == self.cursor:
            strip = strip.apply_style(STYLE_CURSOR)
        return strip

    # ---- cursor ---------------------------------------------------------------------------
    def watch_cursor(self, old, new):
        self.refresh()
        self.post_message(self.RowChanged(new))

    def _ensure_visible(self):
        top = self.scroll_offset.y
        h = max(1, self.size.height - 1)
        if self.cursor < top:
            self.scroll_to(y=self.cursor, animate=False)
        elif self.cursor >= top + h:
            self.scroll_to(y=self.cursor - h + 1, animate=False)

    def set_cursor(self, r):
        if self.n:
            self.cursor = max(0, min(self.n - 1, r))
            self._ensure_visible()

    def action_move(self, d):
        self.set_cursor(self.cursor + d)

    def action_page(self, d):
        self.set_cursor(self.cursor + d * max(1, self.size.height - 2))

    def action_jump(self, where):
        self.set_cursor(0 if where == 0 else self.n - 1)

    def action_hscroll(self, d):
        self.scroll_to(x=max(0, self.scroll_offset.x + d), animate=False)

    def on_click(self, event):
        if event.y >= 1:
            self.set_cursor(self.scroll_offset.y + event.y - 1)
