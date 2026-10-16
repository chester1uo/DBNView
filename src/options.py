"""Option chains from loaded rows: OSI symbol parsing, snapshots, parity forwards, Black-76 implied vol."""
import collections
import datetime as dt
import math
import re

import numpy as np

import core

_OSI = re.compile(r"^(.+?)(\d{6})([CP])(\d{8})$")
YEAR_NS = 365.0 * 86400e9


def parse_osi(sym):
    """'QQQ   261113C00805000' -> (root, date, 'C'|'P', strike) or None."""
    if not sym:
        return None
    s = sym.strip()
    if len(sym) == 21 and sym[6:12].isdigit() and sym[12] in "CP" and sym[13:].isdigit():
        root, ymd, cp, k = sym[:6].strip(), sym[6:12], sym[12], sym[13:]
    else:
        m = _OSI.match(s.replace(" ", ""))
        if not m:
            return None
        root, ymd, cp, k = m.groups()
    try:
        d = dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError:
        return None
    return root, d, cp, int(k) / 1000.0


def chain(job):
    """instrument_id -> (root, expiry date, cp, strike) for every option symbol in the file's mappings."""
    out = {}
    for iid, ivs in job.fi.symmap.iv.items():
        for _, _, name in ivs:
            p = parse_osi(name)
            if p:
                out[iid] = p
                break
    return out


def is_option_data(job, sample=200):
    iv = job.fi.symmap.iv
    if not iv:
        return False
    names = [n for ivs in list(iv.values())[:sample] for _, _, n in ivs[:1]]
    return sum(parse_osi(n) is not None for n in names) >= 0.5 * max(len(names), 1)


def roots(ch):
    c = collections.Counter(v[0] for v in ch.values())
    return [r for r, _ in c.most_common()]


def _expiry_ns(d, tz="America/New_York"):
    t = dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=core._tz(tz))
    return int(t.timestamp()) * 1_000_000_000


# ---- Black-76 ------------------------------------------------------------------
def ncdf(x):
    """Standard normal CDF (Abramowitz-Stegun 26.2.17, |err| < 7.5e-8), vectorized."""
    x = np.asarray(x, dtype=np.float64)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.2316419 * a)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    pdf = np.exp(-0.5 * a * a) / math.sqrt(2 * math.pi)
    upper = 1.0 - pdf * poly
    return np.where(x >= 0, upper, 1.0 - upper)


def black76(F, K, T, sigma, D, is_call):
    sq = sigma * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(F / K) + 0.5 * sq * sq) / sq
    d2 = d1 - sq
    call = D * (F * ncdf(d1) - K * ncdf(d2))
    put = D * (K * ncdf(-d2) - F * ncdf(-d1))
    return np.where(is_call, call, put), d1


def implied_vol(price, F, K, T, D, is_call, lo=1e-4, hi=6.0, iters=80):
    """Vectorized bisection; NaN where the price is outside the no-arbitrage range."""
    price = np.asarray(price, dtype=np.float64)
    intrinsic = D * np.where(is_call, np.maximum(F - K, 0), np.maximum(K - F, 0))
    upper = D * np.where(is_call, F, K)
    ok = np.isfinite(price) & (price > intrinsic + 1e-12) & (price < upper) & (T > 0)
    a = np.full(price.shape, lo)
    b = np.full(price.shape, hi)
    for _ in range(iters):
        m = 0.5 * (a + b)
        pm, _ = black76(F, K, T, m, D, is_call)
        high = pm > price
        b = np.where(high, m, b)
        a = np.where(high, a, m)
    iv = 0.5 * (a + b)
    iv[~ok | (iv >= hi * 0.999)] = np.nan
    return iv


# ---- snapshot ---------------------------------------------------------------
def snapshot(job, t_ns, ch):
    """Last quote/trade of each option instrument at or before t_ns."""
    iids, ts, bid, ask, last = [], [], [], [], []
    want = np.fromiter(ch.keys(), dtype=np.uint32, count=len(ch))
    with job._lock:
        segs = list(job.segments)
    for rt, recs, _ in segs:
        tf = "ts_event" if rt.cls == "OHLCVMsg" else job.filter.tf(rt)
        t = recs[tf]
        m = (t <= np.uint64(t_ns)) & np.isin(recs["instrument_id"], want)
        if not m.any():
            continue
        r = recs[m]
        n = len(r)
        iids.append(r["instrument_id"])
        ts.append(r[tf])
        names = r.dtype.names
        px = lambda f: np.where(r[f] == core.UNDEF_PRICE, np.nan, r[f] / core.PRICE_SCALE) if f in names \
            else np.full(n, np.nan)
        bid.append(px("bid_px_00"))
        ask.append(px("ask_px_00"))
        last.append(px("close") if rt.cls == "OHLCVMsg" else px("price"))
    if not iids:
        return None
    iid = np.concatenate(iids)
    t = np.concatenate(ts)
    order = np.argsort(t, kind="stable")
    iid, t = iid[order], t[order]
    cols = [np.concatenate(c)[order] for c in (bid, ask, last)]
    rev = iid[::-1]
    u, first = np.unique(rev, return_index=True)
    idx = len(iid) - 1 - first
    return {"iid": u, "ts": t[idx], "bid": cols[0][idx], "ask": cols[1][idx], "last": cols[2][idx]}


def stream_snapshot(job, t_ns, ch, progress=None, cancel=None):
    """Read the file from the start up to t_ns, keeping only the last quote of each option."""
    want = np.fromiter(ch.keys(), dtype=np.uint32, count=len(ch))
    last = {}  # iid -> (ts, bid, ask, last)
    fh, st = core.open_stream(job.fi.path)
    try:
        md = core.parse_metadata(st)
        for rt, recs in core.iter_records(st, md["version"], md["ts_out"], schema=md["schema"]):
            if cancel is not None and cancel():
                break
            tf = "ts_event" if rt.cls == "OHLCVMsg" else ("ts_recv" if "ts_recv" in recs.dtype.names else "ts_event")
            t = recs[tf]
            if len(t) and int(t[0]) > t_ns:
                break
            m = (t <= np.uint64(t_ns)) & np.isin(recs["instrument_id"], want)
            if m.any():
                r = recs[m]
                rev = r[::-1]
                u, first = np.unique(rev["instrument_id"], return_index=True)
                pick = rev[first]
                names = r.dtype.names
                px = lambda f: np.where(pick[f] == core.UNDEF_PRICE, np.nan, pick[f] / core.PRICE_SCALE) \
                    if f in names else np.full(len(pick), np.nan)
                b, a = px("bid_px_00"), px("ask_px_00")
                lp = px("close") if rt.cls == "OHLCVMsg" else px("price")
                for i, iid in enumerate(u.tolist()):
                    last[iid] = (int(pick[tf][i]), b[i], a[i], lp[i])
            if progress is not None:
                progress(fh.tell(), job.fi.size)
    finally:
        fh.close()
    if not last:
        return None
    iid = np.array(sorted(last), dtype=np.uint32)
    vals = [last[i] for i in iid.tolist()]
    return {"iid": iid, "ts": np.array([v[0] for v in vals], dtype=np.uint64),
            "bid": np.array([v[1] for v in vals]), "ask": np.array([v[2] for v in vals]),
            "last": np.array([v[3] for v in vals])}


def loaded_covers(job, t_ns):
    """True if the rows already loaded by the scan contain everything up to t_ns."""
    st = job.status()
    if st["done"] and not st["truncated"] and not st["cancelled"] and job.filter.trivial:
        return True
    return st["tmax"] is not None and int(st["tmax"]) >= t_ns and job.filter.trivial


def surface(job, t_ns, root, r=0.04, spot=None, side="otm", max_spread=0.5, min_days=0.5, ch=None,
            max_age_s=None, progress=None, cancel=None):
    """Implied vols of one root's chain at time t_ns. Returns a dict of column arrays + per-expiry forwards."""
    ch = ch or chain(job)
    sub = {i: v for i, v in ch.items() if v[0] == root}
    streamed = not loaded_covers(job, t_ns)
    snap = stream_snapshot(job, t_ns, sub, progress, cancel) if streamed else snapshot(job, t_ns, sub)
    if snap is None:
        return None
    if max_age_s:
        fresh = (t_ns - snap["ts"].astype(np.float64)) / 1e9 <= max_age_s
        snap = {k: v[fresh] for k, v in snap.items()}
        if len(snap["iid"]) == 0:
            return None
    meta = [sub[int(i)] for i in snap["iid"]]
    exp = np.array([m[1].toordinal() for m in meta])
    cp = np.array([m[2] for m in meta])
    K = np.array([m[3] for m in meta])
    bid, ask, last = snap["bid"], snap["ask"], snap["last"]
    two_sided = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask >= bid)
    mid = np.where(two_sided, (bid + ask) / 2, np.where(np.isfinite(last) & (last > 0), last, np.nan))
    rel_spread = np.where(two_sided, (ask - bid) / np.where(mid > 0, mid, np.nan), np.nan)
    exp_ns = {e: _expiry_ns(dt.date.fromordinal(int(e))) for e in np.unique(exp)}
    T = np.array([(exp_ns[e] - t_ns) / YEAR_NS for e in exp])
    D = np.exp(-r * np.maximum(T, 0))
    F = np.full(len(K), np.nan)
    fwd = {}
    for e in np.unique(exp):
        m = exp == e
        Te = T[m][0]
        if Te * 365 < min_days:
            continue
        De = math.exp(-r * Te)
        calls = {k: p for k, p, c in zip(K[m], mid[m], cp[m]) if c == "C" and np.isfinite(p)}
        puts = {k: p for k, p, c in zip(K[m], mid[m], cp[m]) if c == "P" and np.isfinite(p)}
        both = sorted(set(calls) & set(puts), key=lambda k: abs(calls[k] - puts[k]))
        if both:
            Fs = [k + (calls[k] - puts[k]) / De for k in both[:5]]
            fe = float(np.median(Fs))
        elif spot:
            fe = spot * math.exp(r * Te)
        else:
            continue
        fwd[int(e)] = fe
        F[m] = fe
    is_call = cp == "C"
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.log(K / F)
    if side == "otm":
        use = np.where(K >= F, is_call, ~is_call)
    elif side == "call":
        use = is_call
    elif side == "put":
        use = ~is_call
    else:
        use = np.ones(len(K), bool)
    ok = use & np.isfinite(F) & np.isfinite(mid) & (T * 365 >= min_days)
    ok &= ~(two_sided & (rel_spread > max_spread))
    iv = np.full(len(K), np.nan)
    ivb = np.full(len(K), np.nan)
    iva = np.full(len(K), np.nan)
    if ok.any():
        sl = np.flatnonzero(ok)
        iv[sl] = implied_vol(mid[sl], F[sl], K[sl], T[sl], D[sl], is_call[sl])
        tb = sl[two_sided[sl]]
        if len(tb):
            ivb[tb] = implied_vol(bid[tb], F[tb], K[tb], T[tb], D[tb], is_call[tb])
            iva[tb] = implied_vol(ask[tb], F[tb], K[tb], T[tb], D[tb], is_call[tb])
    good = np.isfinite(iv)
    _, d1 = black76(F, K, np.maximum(T, 1e-9), np.where(good, iv, 0.2), D, is_call)
    call_delta = ncdf(d1)
    sel = np.flatnonzero(good)
    syms = [job.fi.symmap.lookup(int(i)) for i in snap["iid"][sel]]
    return {"iid": snap["iid"][sel], "sym": syms, "exp": exp[sel], "T": T[sel], "days": T[sel] * 365, "K": K[sel],
            "cp": cp[sel], "bid": bid[sel], "ask": ask[sel], "mid": mid[sel], "F": F[sel], "k": k[sel], "iv": iv[sel],
            "iv_bid": ivb[sel], "iv_ask": iva[sel], "delta": call_delta[sel], "age_s": (t_ns - snap["ts"][sel].astype(np.float64)) / 1e9,
            "forwards": fwd, "n_quotes": len(snap["iid"]), "t_ns": t_ns, "root": root, "r": r, "streamed": streamed}


def grid(s, x="k", nx=60, max_exp=40):
    """Regular grid for the 3D surface / heatmap: one row per expiry, linear interpolation along x."""
    xs = s[x] if x != "delta" else s["delta"]
    exps = sorted(set(s["exp"].tolist()))[:max_exp]
    los, his = [], []
    for e in exps:
        m = s["exp"] == e
        if m.sum() >= 3:
            los.append(np.nanmin(xs[m]))
            his.append(np.nanmax(xs[m]))
    if not los:
        return None
    lo, hi = float(np.median(los)), float(np.median(his))
    if x == "k":
        lo, hi = max(lo, -1.0), min(hi, 1.0)
    if hi <= lo:
        lo, hi = float(np.min(los)), float(np.max(his))
    gx = np.linspace(lo, hi, nx)
    Z = np.full((nx, len(exps)), np.nan)
    days = []
    for j, e in enumerate(exps):
        m = s["exp"] == e
        days.append(float(s["days"][m][0]))
        if m.sum() < 2:
            continue
        o = np.argsort(xs[m])
        xe, ye = xs[m][o], s["iv"][m][o]
        inside = (gx >= xe[0]) & (gx <= xe[-1])
        Z[inside, j] = np.interp(gx[inside], xe, ye)
    return {"x": gx, "exps": exps, "days": np.array(days), "Z": Z, "xname": x}


def term_at(s, x="k", value=0.0):
    """IV at a fixed x (moneyness / strike / delta) for each expiry, by linear interpolation."""
    xs = s[x]
    out_d, out_iv, out_e = [], [], []
    for e in sorted(set(s["exp"].tolist())):
        m = s["exp"] == e
        if m.sum() < 2:
            continue
        o = np.argsort(xs[m])
        xe, ye = xs[m][o], s["iv"][m][o]
        if xe[0] <= value <= xe[-1]:
            out_d.append(float(s["days"][m][0]))
            out_iv.append(float(np.interp(value, xe, ye)))
            out_e.append(e)
    return np.array(out_d), np.array(out_iv), out_e
