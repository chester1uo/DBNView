"""Option walls: open interest, volume and dealer gamma exposure (GEX) by strike.

Inputs come from three places:
- open interest: OPRA `statistics` records with stat_type 9 (usually a separate file for the trading day)
- volume: trades / tcbbo / cmbp-1 trade rows or ohlcv bars in the open file
- implied volatility: options.surface() on the quotes in the open file (needed for gamma)

GEX convention (the common "naive dealer" model): dealers are long the calls and short the puts that
customers hold, so call gamma counts positive and put gamma negative. Exposure is quoted in dollars of
delta change per 1% move in the underlying: gamma * OI * multiplier * S^2 * 0.01.
"""
import collections
import math

import numpy as np

from ..engine import iter_records, open_stream, parse_metadata
from ..engine.symbology import SymbolMap
from . import options

STAT_OPEN_INTEREST = 9


def load_open_interest(path, progress=None):
    """{(root, expiry, 'C'|'P', strike): open interest} from a statistics DBN file (latest value wins)."""
    fh, st = open_stream(path)
    out, stamp = {}, {}
    try:
        md = parse_metadata(st)
        symmap = SymbolMap(md)
        for rt, recs in iter_records(st, md["version"], md["ts_out"], schema=md["schema"]):
            if rt.cls != "StatMsg":
                continue
            m = recs["stat_type"] == STAT_OPEN_INTEREST
            if "update_action" in recs.dtype.names:
                m &= recs["update_action"] != 2  # 2 = delete
            if not m.any():
                continue
            r = recs[m]
            q = r["quantity"].astype(np.int64)
            ok = q < np.iinfo(r.dtype["quantity"]).max  # max of the type = undefined
            for iid, qty, ts in zip(r["instrument_id"][ok].tolist(), q[ok].tolist(), r["ts_recv"][ok].tolist()):
                key = options.parse_osi(symmap.lookup(iid, ts))
                if key and ts >= stamp.get(key, 0):
                    out[key], stamp[key] = qty, ts
            if progress:
                progress(fh.tell())
    finally:
        fh.close()
    return out


def find_statistics_file(path):
    """A sibling file that looks like the statistics for the same data (same directory), or None."""
    import os
    import re
    if path.startswith("ssh://"):
        return None
    d, name = os.path.split(path)
    date = re.search(r"(20\d\d-?\d\d-?\d\d)", name)
    cands = []
    for f in os.listdir(d or "."):
        if "statistic" in f.lower() and f.endswith((".dbn", ".zst")) and f != name:
            score = 2 if date and date.group(1) in f else 0
            score += 1 if name.split("_")[0] in f else 0
            cands.append((score, f))
    return os.path.join(d, max(cands)[1]) if cands else None


def volume_by_contract(job):
    """{(root, expiry, cp, strike): traded contracts} from the rows loaded by the scan."""
    ch = options.chain(job)
    vol = collections.Counter()
    with job._lock:
        segs = list(job.segments)
    for rt, recs, _ in segs:
        names = recs.dtype.names
        if rt.cls == "OHLCVMsg":
            sizes = recs["volume"].astype(np.int64)
            m = np.ones(len(recs), bool)
        elif "size" in names and (rt.cls in ("TradeMsg", "TCBBOMsg") or "action" in names):
            m = np.ones(len(recs), bool) if rt.cls in ("TradeMsg", "TCBBOMsg") else recs["action"] == b"T"
            sizes = recs["size"].astype(np.int64)
        else:
            continue
        if not m.any():
            continue
        iids, s = recs["instrument_id"][m], sizes[m]
        u, inv = np.unique(iids, return_inverse=True)
        tot = np.bincount(inv, weights=s)
        for iid, v in zip(u.tolist(), tot.tolist()):
            key = ch.get(iid)
            if key:
                vol[key] += int(v)
    return dict(vol)


def _gamma(F, K, T, sigma):
    """Black-76 gamma with respect to the forward (discounting ignored; it is ~1 for listed options)."""
    sq = sigma * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(F / K) + 0.5 * sq * sq) / sq
        g = np.exp(-0.5 * d1 * d1) / (math.sqrt(2 * math.pi) * F * sq)
    return np.where(np.isfinite(g), g, 0.0)


def walls(root, surface=None, oi=None, vol=None, spot=None, max_days=None, expiries=None, multiplier=100,
          asof=None, profile_range=0.12, profile_points=121):
    """Per-strike walls and gamma exposure.

    surface: options.surface(...) result (optional; needed for gamma and for an automatic spot)
    oi / vol: dicts keyed by (root, expiry, cp, strike)
    max_days / expiries: restrict to expiries within max_days (counted from `asof`, a date) or to a set of dates
    """
    import datetime as dt
    oi, vol = oi or {}, vol or {}
    keys = {k for k in list(oi) + list(vol) if k[0] == root}
    if surface is not None:
        for e, cp, K in zip(surface["exp"], surface["cp"], surface["K"]):
            keys.add((root, dt.date.fromordinal(int(e)), str(cp), float(K)))
        if asof is None:
            asof = dt.datetime.fromtimestamp(surface["t_ns"] / 1e9, dt.timezone.utc).date()
    if not keys:
        return None
    # implied vol per (expiry, strike): taken from the OTM side and shared by the call and the put
    iv_at, F_at, T_at = {}, {}, {}
    if surface is not None:
        for e, K, iv, F, T in zip(surface["exp"], surface["K"], surface["iv"], surface["F"], surface["T"]):
            d = dt.date.fromordinal(int(e))
            iv_at[(d, float(K))] = float(iv)
            F_at[d], T_at[d] = float(F), float(T)
        if spot is None and F_at:
            near = min(T_at, key=T_at.get)
            spot = F_at[near] * math.exp(-surface["r"] * T_at[near])
    if asof is None:
        asof = min(k[1] for k in keys)
    rows = collections.defaultdict(lambda: np.zeros(6))  # strike -> call_oi, put_oi, call_vol, put_vol, call_g, put_g
    contracts = []  # (F, K, T, iv, signed_oi) for the gamma profile
    for (r_, d, cp, K) in keys:
        if expiries is not None and d not in expiries:
            continue
        if max_days is not None and (d - asof).days > max_days:
            continue
        o, v = oi.get((r_, d, cp, K), 0), vol.get((r_, d, cp, K), 0)
        row = rows[K]
        row[0 if cp == "C" else 1] += o
        row[2 if cp == "C" else 3] += v
        iv = iv_at.get((d, K))
        if iv is not None and spot and o:
            g = float(_gamma(np.array(F_at[d]), np.array(K), np.array(T_at[d]), np.array(iv)))
            gex = g * o * multiplier * spot * spot * 0.01
            row[4 if cp == "C" else 5] += gex if cp == "C" else -gex
            contracts.append((F_at[d], K, T_at[d], iv, o if cp == "C" else -o))
    if not rows:
        return None
    strikes = np.array(sorted(rows))
    a = np.array([rows[k] for k in strikes])
    out = {"root": root, "strike": strikes, "call_oi": a[:, 0], "put_oi": a[:, 1], "call_vol": a[:, 2],
           "put_vol": a[:, 3], "call_gex": a[:, 4], "put_gex": a[:, 5], "net_gex": a[:, 4] + a[:, 5], "spot": spot,
           "has_oi": bool(a[:, :2].any()), "has_vol": bool(a[:, 2:4].any()), "has_gex": bool(contracts)}
    above = strikes >= (spot or -np.inf)
    below = strikes <= (spot or np.inf)
    out["call_wall"] = float(strikes[above][np.argmax(a[above, 0])]) if out["has_oi"] and above.any() else None
    out["put_wall"] = float(strikes[below][np.argmax(a[below, 1])]) if out["has_oi"] and below.any() else None
    out["vol_call_wall"] = float(strikes[above][np.argmax(a[above, 2])]) if out["has_vol"] and above.any() else None
    out["vol_put_wall"] = float(strikes[below][np.argmax(a[below, 3])]) if out["has_vol"] and below.any() else None
    out["total_gex"] = float(out["net_gex"].sum()) if contracts else None
    out["profile_spot"], out["profile_gex"], out["zero_gamma"] = None, None, None
    if contracts and spot:
        F, K, T, iv, so = (np.array(c, dtype=np.float64) for c in zip(*contracts))
        xs = np.linspace(spot * (1 - profile_range), spot * (1 + profile_range), profile_points)
        prof = np.array([np.sum(_gamma(F * x / spot, K, T, iv) * so) * multiplier * x * x * 0.01 for x in xs])
        out["profile_spot"], out["profile_gex"] = xs, prof
        flips = np.flatnonzero(np.sign(prof[:-1]) * np.sign(prof[1:]) < 0)
        if len(flips):  # the crossing closest to the current spot, linearly interpolated
            i = flips[np.argmin(np.abs(xs[flips] - spot))]
            x0, x1, y0, y1 = xs[i], xs[i + 1], prof[i], prof[i + 1]
            out["zero_gamma"] = float(x0 - y0 * (x1 - x0) / (y1 - y0))
    return out
