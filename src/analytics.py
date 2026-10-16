"""Chart data derived from the rows a scan loaded: K-lines, quotes, order flow, book heatmaps.

Every function takes a core.Job and an instrument_id and returns plain numpy arrays
(times in float seconds since the epoch, prices in real units).
"""
import collections

import numpy as np

import core

TRADE_CLASSES = {"TradeMsg", "MBP1Msg", "TBBOMsg", "MBP10Msg", "CMBP1Msg", "TCBBOMsg", "MBOMsg"}
QUOTE_CLASSES = {"MBP1Msg", "TBBOMsg", "MBP10Msg", "CMBP1Msg", "TCBBOMsg", "CBBO1SMsg", "CBBO1MMsg",
                 "BBO1SMsg", "BBO1MMsg"}
BAR_CLASSES = {"OHLCVMsg"}
INTERVALS = [1, 5, 15, 30, 60, 300, 900, 1800, 3600, 4 * 3600, 86400, 7 * 86400]


def _px(v):
    return np.where(v == core.UNDEF_PRICE, np.nan, v / core.PRICE_SCALE)


def inst_records(job, iid):
    """(RecordType, records) of the dominant record class for one instrument, time-sorted."""
    parts = collections.defaultdict(list)
    rts = {}
    for rt, recs, _ in job.iter_instrument(int(iid)):
        parts[rt.cls].append(recs)
        rts[rt.cls] = rt
    if not parts:
        return None, None, None
    cls = max(parts, key=lambda c: sum(len(p) for p in parts[c]))
    rt = rts[cls]
    recs = np.concatenate(parts[cls]) if len(parts[cls]) > 1 else parts[cls][0]
    tf = job.filter.tf(rt)
    if rt.cls in BAR_CLASSES:
        tf = "ts_event"
    t = recs[tf]
    ok = t != core.UNDEF_TS
    recs = recs[ok]
    order = np.argsort(recs[tf], kind="stable")
    return rt, recs[order], tf


def capabilities(job, iid):
    rt, recs, _ = inst_records(job, iid)
    if rt is None:
        return set(), None
    caps = set()
    names = recs.dtype.names
    if rt.cls in BAR_CLASSES:
        caps.add("bars")
    if rt.cls in TRADE_CLASSES and "price" in names:
        caps |= {"bars", "flow"}
    if "bid_px_00" in names:
        caps |= {"bars", "quotes", "heatmap"}
    if rt.cls == "MBOMsg":
        caps.add("heatmap")
    return caps, rt.cls


def _trades(rt, recs):
    """Mask of rows that are trades (price/size/side are a real print)."""
    names = recs.dtype.names
    if rt.cls == "TradeMsg":
        m = np.ones(len(recs), bool)
    elif "action" in names and recs.dtype["action"].kind == "S":
        m = recs["action"] == b"T"
    else:
        return np.zeros(len(recs), bool)
    return m & (recs["price"] != core.UNDEF_PRICE)


def pick_interval(span_s, max_bars=400, min_iv=0.0):
    for iv in INTERVALS:
        if iv >= min_iv * 0.99 and span_s / iv <= max_bars:
            return iv
    return INTERVALS[-1]


def _aggregate(t, price, vol, interval, o=None, h=None, low=None):
    """OHLCV per bucket of `interval` seconds; t sorted. If o/h/low given, re-aggregate existing bars."""
    b = np.floor(t / interval).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    ends = np.r_[starts[1:], len(b)] - 1
    op = (o if o is not None else price)[starts]
    hi = np.fmax.reduceat(h if h is not None else price, starts)
    lo = np.fmin.reduceat(low if low is not None else price, starts)
    cl = price[ends]
    v = np.add.reduceat(vol, starts) if len(vol) else np.zeros(len(starts))
    return b[starts] * float(interval), op, hi, lo, cl, v, starts


def bars(job, iid, interval=None, source="auto"):
    """Candles for one instrument. source: auto | trades | mid | bars."""
    rt, recs, tf = inst_records(job, iid)
    if rt is None:
        return None
    t = recs[tf].astype(np.float64) / 1e9
    names = recs.dtype.names
    out = {"cls": rt.cls}
    if rt.cls in BAR_CLASSES and source in ("auto", "bars"):
        native = {0x20: 1, 0x21: 60, 0x22: 3600, 0x23: 86400, 0x24: 86400}.get(rt.rtype)
        if native is None:
            d = np.diff(t)
            native = float(np.median(d[d > 0])) if (d > 0).any() else 60.0
        interval = interval or max(1, int(round(native)))
        if len(t) and interval > native * 1.01:
            tt, o, h, lo, c, v, _ = _aggregate(t, _px(recs["close"]), recs["volume"].astype(np.float64), interval,
                                              o=_px(recs["open"]), h=_px(recs["high"]), low=_px(recs["low"]))
        else:
            tt, o, h, lo, c, v = t, _px(recs["open"]), _px(recs["high"]), _px(recs["low"]), _px(recs["close"]), \
                recs["volume"].astype(np.float64)
        out.update(t=tt, o=o, h=h, l=lo, c=c, v=v, buy=None, sell=None, source="bars", interval=interval)
        return out
    tm = _trades(rt, recs)
    use_trades = source == "trades" or (source == "auto" and tm.sum() >= 2)
    if use_trades and tm.any():
        tr = recs[tm]
        tt = t[tm]
        price = _px(tr["price"])
        size = tr["size"].astype(np.float64)
        side = tr["side"] if "side" in names else np.full(len(tr), b"N")
        interval = interval or pick_interval(tt[-1] - tt[0] if len(tt) > 1 else 60)
        bt, o, h, lo, c, v, starts = _aggregate(tt, price, size, interval)
        buy = np.add.reduceat(np.where(side == b"B", size, 0.0), starts)
        sell = np.add.reduceat(np.where(side == b"A", size, 0.0), starts)
        out.update(t=bt, o=o, h=h, l=lo, c=c, v=v, buy=buy, sell=sell, source="trades", interval=interval)
        return out
    if "bid_px_00" in names:
        bid, ask = _px(recs["bid_px_00"]), _px(recs["ask_px_00"])
        mid = (bid + ask) / 2
        ok = np.isfinite(mid)
        if not ok.any():
            return None
        tt, mid = t[ok], mid[ok]
        native = float(np.median(np.diff(tt))) if len(tt) > 1 else 0.0
        interval = interval or pick_interval(tt[-1] - tt[0] if len(tt) > 1 else 60, min_iv=native)
        bt, o, h, lo, c, v, _ = _aggregate(tt, mid, np.ones(len(mid)), interval)
        out.update(t=bt, o=o, h=h, l=lo, c=c, v=v, buy=None, sell=None, source="mid", interval=interval,
                   v_is_count=True)
        return out
    return None


def _thin(n, maxpts):
    if n <= maxpts:
        return np.arange(n)
    return np.unique(np.linspace(0, n - 1, maxpts).astype(np.int64))


def quotes(job, iid, maxpts=20000):
    rt, recs, tf = inst_records(job, iid)
    if rt is None or "bid_px_00" not in recs.dtype.names:
        return None
    t = recs[tf].astype(np.float64) / 1e9
    bid, ask = _px(recs["bid_px_00"]), _px(recs["ask_px_00"])
    bsz = recs["bid_sz_00"].astype(np.float64)
    asz = recs["ask_sz_00"].astype(np.float64)
    if len(t) > maxpts:
        # last quote of each time bucket keeps the step shape of the book
        edges = np.linspace(t[0], t[-1], maxpts + 1)
        idx = np.searchsorted(t, edges[1:], side="right") - 1
        idx = np.unique(idx[idx >= 0])
    else:
        idx = np.arange(len(t))
    with np.errstate(invalid="ignore", divide="ignore"):
        imb = (bsz - asz) / (bsz + asz)
    out = {"t": t[idx], "bid": bid[idx], "ask": ask[idx], "bid_sz": bsz[idx], "ask_sz": asz[idx],
           "mid": ((bid + ask) / 2)[idx], "spread": (ask - bid)[idx], "imb": imb[idx], "n": len(t), "cls": rt.cls}
    tm = _trades(rt, recs)
    out["trades"] = _trade_points(t[tm], recs[tm]) if tm.any() else None
    return out


def _trade_points(t, tr, maxpts=15000):
    price = _px(tr["price"])
    size = tr["size"].astype(np.float64)
    side = tr["side"] if "side" in tr.dtype.names else np.full(len(tr), b"N")
    if len(t) > maxpts:  # keep the biggest prints, then a uniform sample of the rest
        big = np.argsort(-size, kind="stable")[: maxpts // 2]
        rest = _thin(len(t), maxpts // 2)
        keep = np.unique(np.r_[big, rest])
        t, price, size, side = t[keep], price[keep], size[keep], side[keep]
    return {"t": t, "price": price, "size": size, "side": side}


def flow(job, iid, interval=None):
    """Order flow: trade bubbles, cumulative volume delta, buy/sell volume per bar, volume profile."""
    rt, recs, tf = inst_records(job, iid)
    if rt is None:
        return None
    tm = _trades(rt, recs)
    if not tm.any():
        return None
    tr = recs[tm]
    t = tr[tf].astype(np.float64) / 1e9
    price = _px(tr["price"])
    size = tr["size"].astype(np.float64)
    side = tr["side"] if "side" in tr.dtype.names else np.full(len(tr), b"N")
    sign = np.where(side == b"B", 1.0, np.where(side == b"A", -1.0, 0.0))
    cvd = np.cumsum(sign * size)
    ci = _thin(len(t), 20000)
    # volume profile on the price grid actually traded
    u, inv = np.unique(np.round(price, 9), return_inverse=True)
    vp_buy = np.bincount(inv, weights=np.where(sign > 0, size, 0.0), minlength=len(u))
    vp_sell = np.bincount(inv, weights=np.where(sign < 0, size, 0.0), minlength=len(u))
    vp_other = np.bincount(inv, weights=np.where(sign == 0, size, 0.0), minlength=len(u))
    if len(u) > 400:  # re-bin to at most 400 price rows
        edges = np.linspace(u[0], u[-1], 401)
        k = np.clip(np.searchsorted(edges, u, side="right") - 1, 0, 399)
        rb = lambda w: np.bincount(k, weights=w, minlength=400)
        u, vp_buy, vp_sell, vp_other = (edges[:-1] + edges[1:]) / 2, rb(vp_buy), rb(vp_sell), rb(vp_other)
    step = float(np.min(np.diff(u))) if len(u) > 1 else 0.01
    interval = interval or pick_interval(t[-1] - t[0] if len(t) > 1 else 60)
    bt, *_rest, starts = _aggregate(t, price, size, interval)
    buy = np.add.reduceat(np.where(sign > 0, size, 0.0), starts)
    sell = np.add.reduceat(np.where(sign < 0, size, 0.0), starts)
    return {"trades": _trade_points(t, tr), "cvd_t": t[ci], "cvd": cvd[ci], "bar_t": bt, "buy": buy, "sell": sell,
            "interval": interval, "vp_price": u, "vp_buy": vp_buy, "vp_sell": vp_sell, "vp_other": vp_other,
            "vp_step": step, "n": len(t), "cls": rt.cls,
            "vwap": float(np.sum(price * size) / max(np.sum(size), 1e-12))}


def heatmap(job, iid, tbins=500, max_pbins=300):
    """Resting liquidity over time. MBP-N rows are read directly; MBO is replayed into a book."""
    rt, recs, tf = inst_records(job, iid)
    if rt is None:
        return None
    t = recs[tf].astype(np.float64) / 1e9
    if len(t) == 0:
        return None
    t0, t1 = t[0], max(t[-1], t[0] + 1e-6)
    edges = np.linspace(t0, t1, tbins + 1)
    snaps = []  # per time bin: (bid prices, bid sizes, ask prices, ask sizes)
    if rt.cls == "MBOMsg":
        snaps = _mbo_snapshots(recs, t, edges)
    elif "bid_px_00" in recs.dtype.names:
        levels = sorted({int(n[-2:]) for n in recs.dtype.names if n.startswith("bid_px_")})
        idx = np.searchsorted(t, edges[1:], side="right") - 1
        for i in idx:
            if i < 0:
                snaps.append(None)
                continue
            r = recs[i]
            bp = np.array([r["bid_px_%02d" % k] for k in levels])
            ap = np.array([r["ask_px_%02d" % k] for k in levels])
            bs = np.array([r["bid_sz_%02d" % k] for k in levels], dtype=np.float64)
            as_ = np.array([r["ask_sz_%02d" % k] for k in levels], dtype=np.float64)
            okb, oka = bp != core.UNDEF_PRICE, ap != core.UNDEF_PRICE
            snaps.append((bp[okb] / core.PRICE_SCALE, bs[okb], ap[oka] / core.PRICE_SCALE, as_[oka]))
    else:
        return None
    allp = np.concatenate([np.r_[s[0], s[2]] for s in snaps if s is not None] or [np.zeros(0)])
    if len(allp) == 0:
        return None
    best = np.array([[s[0].max() if s is not None and len(s[0]) else np.nan,
                      s[2].min() if s is not None and len(s[2]) else np.nan] for s in snaps])
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mids = np.nanmean(best, axis=1)
    lo, hi = np.nanpercentile(allp, 0.5), np.nanpercentile(allp, 99.5)
    ua = np.unique(np.round(allp, 9))
    tick0 = float(np.min(np.diff(ua))) if len(ua) > 1 else 1e-6
    if np.isfinite(mids).any():  # keep the window around where the market actually is
        mlo, mhi = np.nanpercentile(mids[np.isfinite(mids)], [1, 99])
        pad = max((mhi - mlo) * 0.5, 40 * tick0)
        lo, hi = max(lo, mlo - pad), min(hi, mhi + pad)
    u = np.unique(np.round(allp[(allp >= lo) & (allp <= hi)], 9))
    tick = float(np.min(np.diff(u))) if len(u) > 1 else max((hi - lo) / 50, 1e-6)
    npb = int(round((hi - lo) / tick)) + 1
    if npb > max_pbins:
        npb = max_pbins
        tick = (hi - lo) / (npb - 1)
    z_bid = np.zeros((tbins, npb))
    z_ask = np.zeros((tbins, npb))
    for i, s in enumerate(snaps):
        if s is None:
            continue
        for p, q, z in ((s[0], s[1], z_bid), (s[2], s[3], z_ask)):
            k = np.round((p - lo) / tick).astype(np.int64)
            ok = (k >= 0) & (k < npb)
            np.add.at(z[i], k[ok], q[ok])
    tm = _trades(rt, recs)
    return {"t0": t0, "t1": t1, "p0": lo - tick / 2, "tick": tick, "bid": z_bid, "ask": z_ask,
            "edges": edges, "best_bid": best[:, 0], "best_ask": best[:, 1], "cls": rt.cls, "n": len(t),
            "trades": _trade_points(t[tm], recs[tm], 8000) if tm.any() else None}


def _mbo_snapshots(recs, t, edges, depth=40):
    """Replay MBO into an L2 book, snapshotting the top `depth` levels at each bin edge."""
    orders = {}
    bids, asks = collections.defaultdict(float), collections.defaultdict(float)
    A, S, P, Z, O, F = (recs["action"].tolist(), recs["side"].tolist(), recs["price"].tolist(),
                        recs["size"].tolist(), recs["order_id"].tolist(), recs["flags"].tolist())
    cut = np.searchsorted(t, edges[1:], side="right")
    snaps, j = [], 0

    def level(sd):
        return bids if sd == b"B" else asks

    def take():
        bp = sorted((p for p, q in bids.items() if q > 0), reverse=True)[:depth]
        ap = sorted(p for p, q in asks.items() if q > 0)[:depth]
        return (np.array(bp) / core.PRICE_SCALE, np.array([bids[p] for p in bp]),
                np.array(ap) / core.PRICE_SCALE, np.array([asks[p] for p in ap]))

    for c in cut:
        while j < c:
            a, sd, px, sz, oid = A[j], S[j], P[j], Z[j], O[j]
            j += 1
            if a == b"R":
                orders.clear()
                bids.clear()
                asks.clear()
            elif a == b"A":
                if px != core.UNDEF_PRICE:
                    orders[oid] = [sd, px, sz]
                    level(sd)[px] += sz
            elif a == b"C":
                o = orders.get(oid)
                if o is not None:
                    d = min(sz, o[2])
                    o[2] -= d
                    level(o[0])[o[1]] -= d
                    if o[2] <= 0:
                        del orders[oid]
            elif a == b"M":
                o = orders.get(oid)
                if o is not None:
                    level(o[0])[o[1]] -= o[2]
                if px != core.UNDEF_PRICE:
                    orders[oid] = [sd, px, sz]
                    level(sd)[px] += sz
        snaps.append(take())
    return snaps
