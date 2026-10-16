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

