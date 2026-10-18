"""Rich renderables for the terminal UI: metadata, record detail, stats, format guide, charts and IV tables."""
import datetime as dt

import numpy as np
from rich.console import Group
from rich.table import Table
from rich.text import Text

from .. import reference
from ..analysis import indicators as ind
from ..analysis import market, options
from ..display import fmt_bytes, fmt_n, pretty_field, pretty_stype
from ..engine import PUBLISHERS, metadata_layout
from ..i18n import T
from .table import fmt_px

FIELD_STYLES = ["on #1f3a5f", "on #1f4a3a", "on #4a3f1a", "on #4a1f24", "on #3a2a55", "on #1f4448"]


def _px(v):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt_px(v)


def kv_table(rows, title=None):
    t = Table.grid(padding=(0, 1))
    t.add_column(style="dim", no_wrap=True)
    t.add_column(overflow="fold")
    for k, v in rows:
        t.add_row(k, v)
    return t if title is None else Group(Text(title, style="bold"), t)


def metadata_view(meta, fmt):
    m, rec = meta["metadata"], meta["record"]
    syms = ", ".join(m["symbols_preview"][:6]) + (" … (+%d)" % (m["n_symbols"] - 6) if m["n_symbols"] > 6 else "")
    return kv_table([
        (T("File"), meta["path"]), (T("Size"), fmt_bytes(meta["size"])), (T("Dataset"), m["dataset"]),
        ("Schema", "%s%s" % (m["schema"] or "mixed", " · %dB" % rec["size"] if rec else "")),
        (T("DBN Version"), "v%d" % m["version"]),
        (T("Time"), "%s → %s" % (fmt(m["start"]), fmt(m["end"]) if m["end"] else "—")),
        (T("Symbology"), "%s → %s" % (pretty_stype(m["stype_in"]), pretty_stype(m["stype_out"]))),
        (T("Symbol"), syms or "—"),
        (T("Mappings"), "%s · %s IDs" % (fmt_n(m["n_mappings"]), fmt_n(m["n_instruments"]))),
    ])


def progress_text(st):
    if not st:
        return Text("—")
    state = (T("Error") if st["error"] else T("Stopped") if st["cancelled"] else T("Scanning") if not st["done"]
             else T("Limit reached, stopped (incomplete)") if st["truncated"] else T("Done"))
    pct = 100.0 * st["bytes_done"] / st["bytes_total"] if st["bytes_total"] else 0
    t = Text()
    t.append(state, style="bold red" if st["error"] else "bold")
    t.append("  %s rows · %s matched / %s read · %.1f%% · %.1f s" % (fmt_n(st["rows"]), fmt_n(st["matched"]), fmt_n(st["seen"]),
                                                        pct, st["elapsed"]))
    if st["filter"]:
        t.append("\n" + " · ".join(st["filter"]), style="dim")
    if st["error"]:
        t.append("\n" + st["error"], style="red")
    return t


def ladder(bids, asks, extra_label=None):
    mx = max([b[1] or 0 for b in bids] + [a[1] or 0 for a in asks] + [1])
    t = Table(show_header=True, header_style="dim", box=None, padding=(0, 1))
    t.add_column(T("Price"), justify="right", min_width=10, no_wrap=True)
    t.add_column(T("order|Size"), justify="right", min_width=8, no_wrap=True)
    t.add_column("", width=16, no_wrap=True)
    if extra_label:
        t.add_column(extra_label, justify="left", style="dim", min_width=6, no_wrap=True)
    for lv, style in [(a, "red") for a in reversed(asks)] + [(None, None)] + [(b, "green") for b in bids]:
        if lv is None:
            if bids and asks:
                t.add_row("", Text("Spread %s" % _px(round(asks[0][0] - bids[0][0], 9)), style="dim"), "", *([""] if extra_label else []))
            continue
        bar = Text("█" * int(round(16 * (lv[1] or 0) / mx)), style=style)
        row = [Text(_px(lv[0]), style=style), fmt_n(lv[1]), bar]
        if extra_label:
            row.append("" if lv[2] is None else str(lv[2]))
        t.add_row(*row)
    return t


def detail_view(job, row, o, kinds, fmt, book=None):
    """Every field of a row, its bid/ask ladder, an optional rebuilt MBO book and the raw bytes."""
    parts = []
    bids, asks, label = [], [], None
    for i in range(10):
        k = "%02d" % i
        if "bid_px_" + k not in o:
            break
        c = "ct" if "bid_ct_" + k in o else ("pb" if "bid_pb_" + k in o else None)
        if c:
            label = T("Orders") if c == "ct" else T("Venue")
        pv = (lambda x: PUBLISHERS.get(x, str(x)).split(".")[-1]) if c == "pb" else (lambda x: x)
        if o["bid_px_" + k] is not None:
            bids.append((o["bid_px_" + k], o["bid_sz_" + k], pv(o["bid_%s_%s" % (c, k)]) if c else None))
        if o["ask_px_" + k] is not None:
            asks.append((o["ask_px_" + k], o["ask_sz_" + k], pv(o["ask_%s_%s" % (c, k)]) if c else None))
    if bids or asks:
        parts += [Text(T("Bid/Ask (After This Record)"), style="bold"), ladder(bids, asks, label), Text("")]
    if book:
        parts += [Text("%s · %s · %s" % (T("Order Book (Rebuilt from MBO)"), book["symbol"] or book["instrument_id"],
                                         fmt_n(book["orders"])), style="bold"),
                  ladder(book["bids"], book["asks"], T("book|Orders")), Text("")]
    rows = []
    for c in job.columns:
        v = o.get(c)
        k = kinds.get(c)
        if v is None:
            s = Text("—", style="dim")
        elif k == "ts":
            s = Text("%s  " % fmt(v)) + Text(str(v), style="dim")
        elif k == "flags":
            s = Text("%d = %s" % (v, reference.flag_names(v)))
        elif k == "pub":
            s = Text("%s = %s" % (v, PUBLISHERS.get(v, "?")))
        elif k == "px":
            s = Text(_px(v))
        else:
            s = Text(str(v))
            et = reference.enum_text(job, c, v)
            if et:
                s.append("  = " + et, style="dim")
        rows.append((pretty_field(c), s))
    parts.append(kv_table(rows, T("Columns")))
    try:
        parts += [Text(""), raw_view(job.raw(row))]
    except Exception:  # noqa: BLE001
        pass
    return Group(*parts)


def raw_view(raw):
    lay, hx = raw["layout"], raw["hex"]
    owner = {b: i for i, f in enumerate(lay) for b in range(f[1], f[1] + f[2])}
    n = len(hx) // 2
    text = Text("%s · rtype 0x%02x · %d bytes · little-endian\n" % (raw["cls"], raw["rtype"], n), style="bold")
    for off in range(0, n, 16):
        text.append("%04x  " % off, style="dim")
        for b in range(off, min(n, off + 16)):
            i = owner.get(b)
            text.append(hx[b * 2:b * 2 + 2], style=FIELD_STYLES[i % len(FIELD_STYLES)] if i is not None else "")
            text.append(" ")
        text.append("\n")
    t = Table(box=None, header_style="dim", padding=(0, 1))
    for c in ("Offset", "Field", "Type", "Raw Value"):
        t.add_column(c)
    for i, f in enumerate(lay):
        t.add_row("%d+%d" % (f[1], f[2]), Text(pretty_field(f[0]), style=FIELD_STYLES[i % len(FIELD_STYLES)]), f[3],
                  "" if f[4] is None else str(f[4]))
    return Group(text, t)


def stats_view(st, s, fmt):
    if not st or not s:
        return Text(T("No statistics yet"), style="dim")
    head = kv_table([(T("Records Read"), fmt_n(st["seen"])), ("Matched", fmt_n(st["matched"])),
                     (T("Instruments"), fmt_n(s["n_instruments"])),
                     (T("Time"), "%s → %s" % (fmt(st["tmin"]), fmt(st["tmax"])) if st["tmin"] else "—")])

    def bars(title, d):
        t = Table(title=title, box=None, show_header=False, padding=(0, 1), title_justify="left", title_style="bold")
        e = sorted((d or {}).items(), key=lambda kv: -kv[1])
        tot = sum(v for _, v in e) or 1
        mx = e[0][1] if e else 1
        for k, v in e:
            t.add_row(str(k), Text("█" * max(1, int(20 * v / mx)), style="cyan"), "%s · %.1f%%" % (fmt_n(v), 100 * v / tot))
        return t

    top = Table(title=T("Instruments"), box=None, header_style="dim", title_justify="left", title_style="bold")
    for c in (T("Symbol"), T("Instrument ID"), "Rows", "Share %"):
        top.add_column(c, justify="right" if c in ("Rows", "Share %") else "left")
    for iid, c, sym in s["top"][:50]:
        top.add_row(sym or "—", str(iid), fmt_n(c), "%.2f" % (100 * c / max(1, st["matched"])))
    return Group(head, Text(""), bars(T("Record Type"), s["rtype"]), bars(T("Action"), s["action"]),
                 bars(T("Side"), s["side"]),
                 Text(""), top)


def format_view(fi, meta):
    m, rec = meta["metadata"], meta["record"]
    parts = [Text("%s · %s" % (m["dataset"], m["schema"] or "mixed"), style="bold"),
             Text(reference.schema_doc(m["schema"], "")), Text("")]
    if rec:
        t = Table(title="Record layout: %s (rtype 0x%02x, %d bytes)" % (rec["cls"], rec["rtype"], rec["size"]),
                  header_style="dim", box=None, title_justify="left", title_style="bold")
        for c in ("Offset", "Bytes", "Type", "Field", "Description"):
            t.add_column(c, overflow="fold")
        for i, f in enumerate(rec["layout"]):
            t.add_row(str(f[1]), str(f[2]), f[3],
                      Text(pretty_field(f[0]), style=FIELD_STYLES[i % len(FIELD_STYLES)]) + Text("  " + f[0], style="dim"),
                      Text(reference.field_doc(f[0]), style="dim"))
        parts += [t, Text("")]
    h = Table(title="Metadata header", header_style="dim", box=None, title_justify="left", title_style="bold")
    for c in ("Offset", "Bytes", "Type", "Field", "Value"):
        h.add_column(c, overflow="fold")
    for f in metadata_layout(fi.md, T):
        h.add_row(str(f[1]), fmt_n(f[2]), f[3], f[0], "" if f[4] is None else str(f[4]))
    parts += [h, Text("")]
    for title, rows in reference.enums():
        e = Table(title=title, box=None, show_header=False, title_justify="left", title_style="bold")
        for a, b in rows:
            e.add_row(a, Text(b, style="dim"))
        parts.append(e)
    parts.append(Text(""))
    parts += [Text("• " + tip) for tip in reference.tips()]
    return Group(*parts)


# ---- charts (plotext) --------------------------------------------------------------------
def _plt(width, height):
    import plotext as plt
    plt.clf()
    plt.plotsize(max(40, width), max(10, height))
    plt.theme("pro")
    return plt


def _labels(ts, fmt_short, n=6):
    idx = np.linspace(0, len(ts) - 1, min(n, len(ts))).astype(int) if len(ts) else []
    return [float(ts[i]) for i in idx], [fmt_short(ts[i]) for i in idx]


def fmt_interval(s):
    for unit, n in (("W", 604800), ("D", 86400), ("h", 3600), ("m", 60)):
        if s >= n and s % n == 0:
            return "%d%s" % (s // n, unit)
    return "%gs" % s


TUI_INDICATORS = ["none", "sma", "ema", "boll", "vwap", "rsi", "macd", "stoch", "atr"]


def _finite_from(y):
    ok = np.isfinite(y)
    return int(np.argmax(ok)) if ok.any() else len(y)


def chart_view(job, iid, mode, width, height, fmt_short, tz, indicator="none"):
    """mode: 'candles' | 'quotes' | 'flow'. Returns rich Text with the plot (ANSI colors)."""
    plt = _plt(width, height)
    sym = job.fi.symmap.lookup(int(iid)) or str(iid)
    if mode == "candles":
        b = market.bars(job, iid)
        if b is not None and len(b["t"]) > max(10, width // 3):  # one candle needs ~3 columns
            span = b["t"][-1] - b["t"][0]
            b = market.bars(job, iid, market.pick_interval(span, max_bars=max(10, width // 3), min_iv=b["interval"]))
        if b is None or not len(b["t"]):
            return Text(T("No data to draw candles for this instrument"), style="dim")
        plt.date_form("d/m/Y H:M:S", "H:M:S")
        # plotext parses date strings as UTC but prints tick labels in the machine's local zone;
        # pre-shift by the local UTC offset so the labels show wall-clock time in the chosen zone.
        local_off = dt.datetime.fromtimestamp(float(b["t"][0])).astimezone().utcoffset()
        dates = [(dt.datetime.fromtimestamp(float(x), tz).replace(tzinfo=None) - local_off).strftime("%d/%m/%Y %H:%M:%S")
                 for x in b["t"]]
        spec = ind.INDICATORS.get(indicator)
        pane = spec is not None and spec["kind"] == "pane"
        if pane:  # candles on top, the oscillator below (two separate plots stacked)
            plt.plotsize(max(40, width), max(8, int(height * 0.62)))
        plt.candlestick(dates, {"Open": list(b["o"]), "High": list(b["h"]), "Low": list(b["l"]), "Close": list(b["c"])})
        title = "%s · Candles %s · %d bars · %s" % (sym, fmt_interval(b["interval"]), len(dates),
                                                     {"bars": "OHLCV", "trades": "from trades", "mid": "from quote mid"}[b["source"]])
        if spec is None:
            plt.title(title)
            return Text.from_ansi(plt.build())
        out = ind.compute(indicator, b)
        colors = {"accent": "cyan", "warn": "orange", "muted": "gray", "teal": "blue", "violet": "magenta", "hist": "white"}
        if pane:
            plt.title(title)
            top = plt.build()
            plt = _plt(width, max(6, height - int(height * 0.62)))
            plt.date_form("d/m/Y H:M:S", "H:M:S")
        for (line_name, role), y in zip(spec["lines"], out):
            i0 = _finite_from(y)
            if i0 < len(y):
                if role == "hist":
                    plt.bar(dates[i0:], list(y[i0:]), color="white", width=0.4)
                else:
                    plt.plot(dates[i0:], list(y[i0:]), color=colors[role], label=line_name)
        for lvl in spec.get("levels", []):
            plt.hline(lvl, "gray")
        plt.xlim(dates[0], dates[-1])  # keep the oscillator aligned with the candles above
        if pane:
            plt.title(ind.label(indicator))
            return Text.from_ansi(top + "\n" + plt.build())
        plt.title(title + " · " + ind.label(indicator))
    elif mode == "quotes":
        q = market.quotes(job, iid, maxpts=max(200, width * 2))
        if q is None:
            return Text(T("This instrument has no quote (bid/ask) fields"), style="dim")
        ok = np.isfinite(q["bid"]) & np.isfinite(q["ask"])
        plt.plot(list(q["t"][ok]), list(q["bid"][ok]), color="green", label="Bid")
        plt.plot(list(q["t"][ok]), list(q["ask"][ok]), color="red", label="Ask")
        xt, xl = _labels(q["t"], fmt_short)
        plt.xticks(xt, xl)
        plt.title("%s · Bid / Ask · %s quotes" % (sym, fmt_n(q["n"])))
    else:
        f = market.flow(job, iid)
        if f is None:
            return Text(T("No trades for this instrument (needs data with trades, e.g. trades / tbbo / mbp / cmbp / "
                          "mbo)"), style="dim")
        tr = f["trades"]
        for side, color in ((b"B", "green"), (b"A", "red"), (b"N", "gray")):
            m = tr["side"] == side
            if m.any():
                plt.scatter(list(tr["t"][m]), list(tr["price"][m]), color=color, marker="dot")
        xt, xl = _labels(f["cvd_t"], fmt_short)
        plt.xticks(xt, xl)
        plt.title("%s · Trades (green = buyer-initiated, red = seller-initiated) · VWAP %s · %s trades" % (sym, _px(f["vwap"]), fmt_n(f["n"])))
    return Text.from_ansi(plt.build())


def iv_view(s, width, height):
    """IV table (expiry × moneyness buckets) plus the ATM term structure."""
    if s is None or not len(s["iv"]):
        return Text(T("No usable option quotes at this time (try a later time, or relax the spread / expiry "
                      "limits)."), style="dim")
    buckets = [-0.3, -0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2, 0.3]
    t = Table(title="%s IV · ln(K/F)" % s["root"], header_style="dim", box=None, title_justify="left", title_style="bold")
    t.add_column("Expiry")
    t.add_column("F", justify="right")
    for b in buckets:
        t.add_column("%+.2f" % b, justify="right")
    lo, hi = np.nanpercentile(s["iv"], 5), np.nanpercentile(s["iv"], 95)
    for e in sorted(set(s["exp"].tolist()))[:30]:
        m = s["exp"] == e
        o = np.argsort(s["k"][m])
        k, iv = s["k"][m][o], s["iv"][m][o]
        cells = []
        for b in buckets:
            if len(k) >= 2 and k[0] <= b <= k[-1]:
                v = float(np.interp(b, k, iv))
                z = (v - lo) / max(hi - lo, 1e-9)
                style = "blue" if z < 0.33 else "yellow" if z < 0.66 else "red"
                cells.append(Text("%.1f%%" % (100 * v), style=style))
            else:
                cells.append(Text("·", style="dim"))
        t.add_row("%s (%.0fd)" % (dt.date.fromordinal(int(e)).isoformat(), s["days"][m][0]),
                  "%.2f" % s["forwards"].get(int(e), np.nan), *cells)
    d, iv, _ = options.term_at(s, "k", 0.0)
    parts = [t]
    if len(d) >= 2:
        plt = _plt(width, max(10, height // 3))
        plt.plot(list(d), list(100 * iv), marker="dot", color="cyan")
        plt.title("ATM IV Term Structure (%) vs. Days to Expiry")
        parts += [Text(""), Text.from_ansi(plt.build())]
    return Group(*parts)


def walls_view(w, width, pct=0.08):
    """Option walls as a strike table with call/put bars, plus the key levels."""
    if w is None:
        return Text(T("Not enough data here"), style="dim")
    spot = w["spot"]
    k = w["strike"]
    keep = np.abs(k - spot) <= spot * pct if spot else np.ones(len(k), bool)
    metric = "gex" if w["has_gex"] else ("oi" if w["has_oi"] else "vol")
    call = {"gex": w["call_gex"], "oi": w["call_oi"], "vol": w["call_vol"]}[metric][keep]
    put = {"gex": -w["put_gex"], "oi": w["put_oi"], "vol": w["put_vol"]}[metric][keep]
    k = k[keep]
    big = lambda v: next(("%.2f%s" % (v / n, u) for u, n in (("B", 1e9), ("M", 1e6), ("K", 1e3)) if abs(v) >= n),
                         "%.0f" % v)
    levels = Text()
    for label, v, style in ((T("Underlying Price"), spot, "cyan"), (T("Call Wall"), w["call_wall"], "green"),
                            (T("Put Wall"), w["put_wall"], "red"), (T("Gamma Flip"), w["zero_gamma"], "yellow")):
        if v:
            walls = (T("Call Wall"), T("Put Wall"))
            levels.append("%s %s   " % (label, ("%.2f" % v) if label not in walls else "%g" % v),
                          style=style)
    if w["total_gex"] is not None:
        levels.append("%s %s" % (T("Total Gamma Exposure"), big(w["total_gex"])))
    title = {"gex": T("Gamma Exposure (per 1% Move)"), "oi": T("Open Interest"), "vol": T("Volume")}[metric]
    bw = max(10, (width - 40) // 2)
    mx = max(float(np.max(np.abs(np.r_[call, put]))) if len(k) else 1, 1e-9)
    t = Table(title=title, header_style="dim", box=None, title_justify="left", title_style="bold")
    t.add_column("Put", justify="right", no_wrap=True)
    t.add_column("", justify="right", no_wrap=True, width=bw)
    t.add_column(T("Strike"), justify="center", no_wrap=True)
    t.add_column("", no_wrap=True, width=bw)
    t.add_column("Call", no_wrap=True)
    for K, c, p in sorted(zip(k, call, put), reverse=True):
        mark = "◀" if spot and abs(K - spot) == min(abs(k - spot)) else " "
        kstyle = "bold cyan" if mark != " " else ("green" if K == w["call_wall"] else "red" if K == w["put_wall"] else "")
        t.add_row(big(p), Text("█" * int(round(bw * p / mx)), style="red"), Text("%g %s" % (K, mark), style=kstyle),
                  Text("█" * int(round(bw * c / mx)), style="green"), big(c))
    return Group(levels, Text(""), t)
