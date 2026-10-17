"""Joint stock + option analysis on a common time grid.

From the underlying file: price bars and realized volatility.
From the option file (one streaming pass, quotes kept per contract): at every grid time the parity-implied
spot, ATM implied volatility for the front and ~30-day expiries, a 25-delta-style skew proxy, the
front-expiry straddle (implied move), and per-interval call/put volume and premium.
"""
import datetime as dt
import math
import time

import numpy as np

from ..engine import Job, get_tz, iter_records, open_stream, parse_metadata
from ..engine.constants import PRICE_SCALE, UNDEF_PRICE
from . import market, options

TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600


def underlying_series(path, interval, cancel=None, cap=50_000_000):
    """Bars of the busiest instrument in a stock/ETF/futures file and its rolling realized volatility."""
    job = Job(path, {"cap": cap})
    while not job.done:
        if cancel is not None and cancel():
            job.cancelled = True
        time.sleep(0.05)
    if job.error:
        raise RuntimeError(job.error)
    top = job.iid_counts.top(1)
    if not top:
        return None
    iid = top[0][0]
    b = market.bars(job, iid, interval)
    if b is None:
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.diff(np.log(b["c"]))
    window = max(5, int(1800 // interval))  # ~30 minutes of bars
    rv = np.full(len(b["c"]), np.nan)
    for i in range(window, len(r) + 1):
        seg = r[i - window:i]
        seg = seg[np.isfinite(seg)]
        if len(seg) > 2:
            rv[i] = np.std(seg, ddof=1) * math.sqrt(TRADING_SECONDS_PER_YEAR / interval)
    return {"symbol": job.fi.symmap.lookup(iid) or str(iid), "bars": b, "rv": rv, "job": job}


class _Chain:
    """Static index of the option chain of one root: expiry/strike/cp per contract slot."""

    def __init__(self, ch, root):
        items = sorted((v[1], v[3], v[2], iid) for iid, v in ch.items() if v[0] == root)
        self.iids = np.array([x[3] for x in items], dtype=np.int64)
        self.exp = np.array([x[0].toordinal() for x in items])
        self.K = np.array([x[1] for x in items])
        self.call = np.array([x[2] == "C" for x in items])
        self.slot = {int(i): n for n, i in enumerate(self.iids)}
        self.expiries = sorted(set(self.exp.tolist()))
        self.exp_ns = {e: int(dt.datetime.combine(dt.date.fromordinal(e), dt.time(16), get_tz("America/New_York"))
                              .timestamp()) * 1_000_000_000 for e in self.expiries}


def _expiry_metrics(ch, e, bid, ask, t_ns, r):
    """Forward, ATM IV, straddle and skew proxy for one expiry from the current quotes (or None)."""
    T = (ch.exp_ns[e] - t_ns) / options.YEAR_NS
    if T <= 1e-6:
        return None
    m = ch.exp == e
    K, call = ch.K[m], ch.call[m]
    b, a = bid[m], ask[m]
    ok = np.isfinite(b) & np.isfinite(a) & (b > 0) & (a >= b)
    mid = np.where(ok, (b + a) / 2, np.nan)
    calls = {k: p for k, p, c in zip(K, mid, call) if c and np.isfinite(p)}
    puts = {k: p for k, p, c in zip(K, mid, call) if not c and np.isfinite(p)}
    both = sorted(set(calls) & set(puts), key=lambda k: abs(calls[k] - puts[k]))
    if not both:
        return None
    D = math.exp(-r * T)
    F = float(np.median([k + (calls[k] - puts[k]) / D for k in both[:3]]))
    atm = min(both, key=lambda k: abs(k - F))
    ivc = options.implied_vol(np.array([calls[atm]]), np.array([F]), np.array([atm]), np.array([T]), D, np.array([True]))[0]
    ivp = options.implied_vol(np.array([puts[atm]]), np.array([F]), np.array([atm]), np.array([T]), D, np.array([False]))[0]
    atm_iv = np.nanmean([ivc, ivp]) if np.isfinite([ivc, ivp]).any() else np.nan
    straddle = calls[atm] + puts[atm]
    skew = np.nan
    if np.isfinite(atm_iv):  # IV of the put ~1 sd * 0.5 below minus the call ~0.5 sd above (a 25-delta proxy)
        width = 0.5 * atm_iv * math.sqrt(T)
        kp, kc = F * math.exp(-width), F * math.exp(width)
        pk = min(puts, key=lambda k: abs(k - kp))
        ck = min(calls, key=lambda k: abs(k - kc))
        ivs = [options.implied_vol(np.array([puts[pk]]), np.array([F]), np.array([pk]), np.array([T]), D, np.array([False]))[0],
               options.implied_vol(np.array([calls[ck]]), np.array([F]), np.array([ck]), np.array([T]), D, np.array([True]))[0]]
        if np.isfinite(ivs).all():
            skew = ivs[0] - ivs[1]
    return {"F": F, "T": T, "spot": F * D, "atm_iv": atm_iv, "straddle": straddle, "move": straddle / F, "skew": skew}


def option_series(path, root, interval, r=0.04, target_days=30, t0=None, t1=None, progress=None, cancel=None):
    """One pass over an option file: per-grid-time chain metrics plus per-interval call/put flow."""
    fh, st = open_stream(path)
    try:
        md = parse_metadata(st)
        from ..engine.symbology import SymbolMap
        symmap = SymbolMap(md)
        ch_map = {}
        for iid, ivs in symmap.iv.items():
            for _, _, name in ivs:
                p = options.parse_osi(name)
                if p:
                    ch_map[iid] = p
                    break
        if root is None:
            roots = options.roots(ch_map)
            if not roots:
                raise ValueError("no OSI option symbols in %s" % path)
            root = roots[0]
        ch = _Chain(ch_map, root)
        n = len(ch.iids)
        bid, ask = np.full(n, np.nan), np.full(n, np.nan)
        out = {k: [] for k in ("t", "spot", "front_iv", "iv30", "skew", "move", "front_days", "call_vol", "put_vol",
                               "call_prem", "put_prem")}
        flow = np.zeros(4)
        next_edge = None
        lookup = {}
        finished = False

        def emit(edge):
            row = {"t": edge / 1e9}
            exps = [e for e in ch.expiries if ch.exp_ns[e] > edge]
            front = None
            for e in exps[:3]:  # first expiry with usable quotes
                front = _expiry_metrics(ch, e, bid, ask, edge, r)
                if front:
                    break
            target = min(exps, key=lambda e: abs((ch.exp_ns[e] - edge) / 86400e9 - target_days)) if exps else None
            m30 = _expiry_metrics(ch, target, bid, ask, edge, r) if target is not None else None
            row.update(spot=front["spot"] if front else np.nan, front_iv=front["atm_iv"] if front else np.nan,
                       move=front["move"] if front else np.nan, front_days=front["T"] * 365 if front else np.nan,
                       iv30=m30["atm_iv"] if m30 else np.nan, skew=m30["skew"] if m30 else np.nan,
                       call_vol=flow[0], put_vol=flow[1], call_prem=flow[2], put_prem=flow[3])
            for k in out:
                out[k].append(row[k])
            flow[:] = 0

        for rt, recs in iter_records(st, md["version"], md["ts_out"], schema=md["schema"]):
            if finished or (cancel is not None and cancel()):
                break
            names = recs.dtype.names
            tf = "ts_recv" if "ts_recv" in names else "ts_event"
            ts = recs[tf]
            iid = recs["instrument_id"]
            # map instrument ids to chain slots (cached per unique id)
            u, inv = np.unique(iid, return_inverse=True)
            su = np.array([lookup.setdefault(int(x), ch.slot.get(int(x), -1)) for x in u.tolist()], dtype=np.int64)
            slots = su[inv]
            keep = slots >= 0
            if t0 is not None:
                keep &= ts >= np.uint64(t0)
            if not keep.any():
                continue
            recs, ts, slots = recs[keep], ts[keep], slots[keep]
            if t1 is not None and int(ts[0]) >= t1:
                finished = True
                break
            # process in time order, emitting grid points as their edges are passed
            start = 0
            while start < len(recs):
                if next_edge is None:
                    next_edge = (int(ts[start]) // (interval * 1_000_000_000) + 1) * interval * 1_000_000_000
                cut = int(np.searchsorted(ts[start:], np.uint64(next_edge))) + start
                part, ps = recs[start:cut], slots[start:cut]
                if len(part):
                    if "bid_px_00" in names:
                        b = part["bid_px_00"].astype(np.float64)
                        a = part["ask_px_00"].astype(np.float64)
                        b[part["bid_px_00"] == UNDEF_PRICE] = np.nan
                        a[part["ask_px_00"] == UNDEF_PRICE] = np.nan
                        bid[ps], ask[ps] = b / PRICE_SCALE, a / PRICE_SCALE  # later rows overwrite earlier ones
                    if rt.cls == "OHLCVMsg":
                        v = part["volume"].astype(np.float64)
                        prem = part["close"] / PRICE_SCALE * v * 100
                        isc = ch.call[ps]
                        flow += [v[isc].sum(), v[~isc].sum(), prem[isc].sum(), prem[~isc].sum()]
                    elif rt.cls in ("TradeMsg", "TCBBOMsg") or ("action" in names and rt.cls == "CMBP1Msg"):
                        tm = np.ones(len(part), bool) if rt.cls in ("TradeMsg", "TCBBOMsg") else part["action"] == b"T"
                        tm &= part["price"] != UNDEF_PRICE
                        if tm.any():
                            sz = part["size"][tm].astype(np.float64)
                            prem = part["price"][tm] / PRICE_SCALE * sz * 100
                            isc = ch.call[ps[tm]]
                            flow += [sz[isc].sum(), sz[~isc].sum(), prem[isc].sum(), prem[~isc].sum()]
                if cut < len(recs):
                    emit(next_edge)
                    next_edge += interval * 1_000_000_000
                    if t1 is not None and next_edge > t1:
                        finished = True
                        break
                start = cut
            if progress is not None:
                progress(fh.tell())
        if next_edge is not None and not finished:
            emit(next_edge)
    finally:
        fh.close()
    res = {k: np.array(v, dtype=np.float64) for k, v in out.items()}
    with np.errstate(divide="ignore", invalid="ignore"):
        res["pc_ratio"] = np.where(res["call_vol"] > 0, res["put_vol"] / res["call_vol"], np.nan)
    res["root"] = root
    res["interval"] = interval
    return res


def find_volume_file(options_path):
    """A sibling option file with trades (trades / tcbbo / ohlcv) for the same day, or None."""
    import os
    import re
    if options_path.startswith("ssh://"):
        return None
    d, name = os.path.split(options_path)
    date = re.search(r"(20\d\d-?\d\d-?\d\d)", name)
    prefix = name.split("_")[0]
    best = None
    for f in sorted(os.listdir(d or ".")):
        if f == name or not f.endswith((".dbn", ".zst")) or not any(k in f for k in ("trades", "tcbbo", "ohlcv")):
            continue
        if date and date.group(1) not in f:
            continue
        score = (prefix in f) * 2 + ("tcbbo" in f) + ("trades" in f)
        if best is None or score > best[0]:
            best = (score, f)
    return os.path.join(d, best[1]) if best and best[0] >= 2 else None


def merge_flow(base, extra):
    """Copy per-interval call/put volume and premium from `extra` into `base` where the grid times match."""
    idx = {round(t): i for i, t in enumerate(extra["t"])}
    for k in ("call_vol", "put_vol", "call_prem", "put_prem"):
        base[k] = np.array([extra[k][idx[round(t)]] if round(t) in idx else 0.0 for t in base["t"]])
    with np.errstate(divide="ignore", invalid="ignore"):
        base["pc_ratio"] = np.where(base["call_vol"] > 0, base["put_vol"] / base["call_vol"], np.nan)
    return base


def symbol_root(symbol):
    """'QQQ' from a stock symbol like 'QQQ' or 'BRK.B' -> 'BRKB' (OSI roots drop punctuation)."""
    return "".join(ch for ch in (symbol or "") if ch.isalnum()).upper() or None
