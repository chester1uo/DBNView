"""Qt-free display helpers shared by the desktop GUI, the terminal UI and the web server."""
import datetime as dt
import os
import re

from .engine import get_tz


def fmt_bytes(b):
    if b is None:
        return "—"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return ("%.0f %s" if u == "B" else "%.1f %s") % (b, u)
        b /= 1024


def fmt_n(n):
    return "—" if n is None else "{:,}".format(n)


def fmt_px(v):
    if v is None:
        return None
    s = "%.9f" % v
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt_dur(s):
    return "%.1fs" % s if s < 60 else "%dm%02ds" % (s // 60, s % 60)


class TsFmt:
    def __init__(self):
        self.tz = "America/New_York"
        self.mode = "dt"
        self._cache = {}

    def set(self, tz=None, mode=None):
        self.tz = tz or self.tz
        self.mode = mode or self.mode
        self._cache.clear()

    def _sec(self, s):
        v = self._cache.get(s)
        if v is None:
            d = dt.datetime.fromtimestamp(s, get_tz(self.tz))
            v = (d.strftime("%Y-%m-%d"), d.strftime("%H:%M:%S"))
            if len(self._cache) > 100000:
                self._cache.clear()
            self._cache[s] = v
        return v

    def fmt(self, ns, mode=None):
        if ns is None:
            return None
        mode = mode or self.mode
        if mode == "ns":
            return str(ns)
        s, frac = divmod(int(ns), 1_000_000_000)
        d, t = self._sec(s)
        return "%s.%09d" % (t, frac) if mode == "t" else "%s %s.%09d" % (d, t, frac)

    @property
    def tz_short(self):
        return self.tz.split("/")[-1]


def display_name(path):
    """Last path component of a local (any OS) or ssh:// path."""
    return re.split(r"[\\/]", path.rstrip("/\\"))[-1] or path


def ssh_hosts():
    hosts = []
    try:
        with open(os.path.expanduser("~/.ssh/config")) as f:
            for line in f:
                m = re.match(r"\s*Host\s+(.+)", line, re.I)
                if m:
                    hosts += [h for h in m.group(1).split() if not any(ch in h for ch in "*?!")]
    except OSError:
        pass
    return hosts



# ---- human-readable names for raw DBN field / symbology identifiers --------------------------------
_FIELD_NAMES = {
    "_rec": "#", "ts_recv": "Receive Time", "ts_event": "Event Time", "ts_out": "Send Time",
    "ts_ref": "Reference Time", "ts_in_delta": "Receive Delta (ns)", "instrument_id": "Instrument ID",
    "publisher_id": "Publisher", "rtype": "Record Type", "order_id": "Order ID", "channel_id": "Channel ID",
    "raw_symbol": "Raw Symbol", "stype_in_symbol": "Input Symbol", "stype_out_symbol": "Output Symbol",
    "stype_in": "Input Symbology", "stype_out": "Output Symbology", "stat_type": "Statistic Type",
    "stat_flags": "Statistic Flags", "update_action": "Update Action", "raw_instrument_id": "Raw Instrument ID",
    "underlying_id": "Underlying ID", "leg_instrument_id": "Leg Instrument ID", "appl_id": "Application ID",
    "market_segment_id": "Market Segment ID", "security_update_action": "Security Update Action",
    "inst_attrib_value": "Instrument Attributes", "start_ts": "Start Time", "end_ts": "End Time",
    "err": "Error", "msg": "Message", "is_last": "Is Last", "symbol": "Symbol",
}
_LEVEL_PART = {"px": "Price", "sz": "Size", "ct": "Orders", "pb": "Venue"}
_ACRONYMS = {"id": "ID", "ts": "TS", "dbn": "DBN", "utc": "UTC", "ohlcv": "OHLCV", "bbo": "BBO", "mbo": "MBO",
             "mbp": "MBP", "isin": "ISIN", "figi": "FIGI", "cfi": "CFI", "vwap": "VWAP", "nbbo": "NBBO",
             "ssr": "SSR", "mwcb": "MWCB", "qty": "Quantity", "vol": "Volume", "px": "Price", "sz": "Size", "ct": "Count"}
_SMALL = {"of", "and", "or", "in", "to", "at", "per", "vs"}
_STYPE_NAMES = {
    "instrument_id": "Instrument ID", "raw_symbol": "Raw Symbol", "parent": "Parent", "continuous": "Continuous",
    "smart": "Smart", "nasdaq_symbol": "Nasdaq Symbol", "cms_symbol": "CMS Symbol", "isin": "ISIN",
    "us_code": "US Code (CUSIP)", "bbg_comp_id": "Bloomberg Composite ID",
    "bbg_comp_ticker": "Bloomberg Composite Ticker", "figi": "FIGI", "figi_ticker": "FIGI Ticker",
}


def pretty_field(name):
    """Display name of a raw field: 'instrument_id' -> 'Instrument ID', 'bid_px_00' -> 'Bid Price 1'."""
    if name in _FIELD_NAMES:
        return _FIELD_NAMES[name]
    m = re.match(r"^(bid|ask)_(px|sz|ct|pb)_(\d\d)$", name)
    if m:
        return "%s %s %d" % (m.group(1).title(), _LEVEL_PART[m.group(2)], int(m.group(3)) + 1)
    words = []
    for w in name.strip("_").split("_"):
        words += [p for p in re.split(r"(\d+)", w) if p]  # 'reserved1' -> 'reserved', '1'
    out = [_ACRONYMS.get(w, w if w.isdigit() else w.lower() if i and w in _SMALL else w.capitalize())
           for i, w in enumerate(words)]
    return " ".join(out) or name


def pretty_stype(s):
    return "—" if not s else _STYPE_NAMES.get(s, pretty_field(s))
