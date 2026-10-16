"""Time zones, user time parsing and nanosecond timestamp formatting."""
import datetime as dt

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


_TZ_CACHE = {}


def get_tz(name):
    if not name or name == "UTC":
        return dt.timezone.utc
    if name not in _TZ_CACHE:
        if ZoneInfo is None:
            raise ValueError("zoneinfo unavailable; use UTC")
        _TZ_CACHE[name] = ZoneInfo(name)
    return _TZ_CACHE[name]


def parse_time(s, tz, ref_ns):
    """'2026-10-15 15:30[:00.123]', '15:30' (date from ref_ns), ISO-Z, or raw ns -> ns."""
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit() and len(s) > 12:
        return int(s)
    z = get_tz(tz)
    frac_ns = 0
    if "." in s.split(" ")[-1].split("T")[-1]:
        s, frac = s.rsplit(".", 1)
        frac = "".join(ch for ch in frac if ch.isdigit())
        frac_ns = int((frac + "000000000")[:9])
    if s.endswith("Z"):
        s, z = s[:-1], dt.timezone.utc
    if len(s) <= 8 and ":" in s:
        ref = dt.datetime.fromtimestamp((ref_ns or 0) / 1e9, z)
        t = dt.time.fromisoformat(s if s.count(":") == 2 else s + ":00")
        d = dt.datetime.combine(ref.date(), t)
    else:
        d = dt.datetime.fromisoformat(s.replace("T", " "))
    if d.tzinfo is None:
        d = d.replace(tzinfo=z)
    secs = int((d - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)).total_seconds())
    return secs * 1_000_000_000 + frac_ns


def fmt_ts(ns, tz=dt.timezone.utc):
    if ns is None:
        return ""
    ns = int(ns)
    d = dt.datetime.fromtimestamp(ns // 1_000_000_000, tz)
    return d.strftime("%Y-%m-%d %H:%M:%S") + ".%09d" % (ns % 1_000_000_000)

