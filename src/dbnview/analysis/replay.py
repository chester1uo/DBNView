"""MBO order-book replay: the book at any moment of the day, for scrubbing and playback.

Two backends share one interface (`open_replay` picks one):

- `WasrReplay` uses LOB-WASR (github.com/chester1uo/LOB-WASR, Python package `wasr`). The first time a file is replayed
  it is indexed into a `.wasr` file in the cache directory (a few seconds per day); after that the exact L1-L3 book at
  any time is a checkpoint restore plus a short replay (milliseconds), forward steps continue from the current state,
  and BBO / trades come from materialised sections. Remote (ssh://) files are downloaded into the cache first.
- `LoadedReplay` needs nothing extra: it replays the MBO rows DBNView has already loaded (one instrument) with
  in-memory checkpoints. It covers only the loaded rows and its queue order is approximate (a modify moves the order
  to the back of its level).

Snapshots are dicts: {"pos", "ts", "n_orders", "bids", "asks", "ms"} where bids/asks are lists of
(price, size, count, orders) best first, price as float, and orders a list of (order_id, size) in queue order when
queues were requested (else None).
"""
import hashlib
import os
import sys
import time

import numpy as np

from ..engine.constants import PRICE_SCALE, UNDEF_PRICE
from ..engine.sources import _CountingReader, is_remote, source_stat
from .book import OrderBook

F_LAST = 128


def wasr_available():
    try:
        import wasr
    except ImportError:
        return False
    return hasattr(wasr, "File")


def cache_dir():
    """Where `.wasr` indexes (and downloaded remote files) are kept."""
    if sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Caches/DBNView")
    elif os.name == "nt":
        root = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "DBNView", "cache")
    else:
        root = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "dbnview")
    return os.path.join(os.environ.get("DBNVIEW_CACHE_DIR") or root, "wasr")


def cache_key(path):
    """Stable name for a source file version: stem + hash of (path, size, mtime)."""
    size, mtime = source_stat(path)
    digest = hashlib.sha1(("%s|%d|%d" % (path, size, int(mtime * 1e9))).encode()).hexdigest()[:12]
    stem = os.path.basename(path.rstrip("/")).split(".")[0] or "file"
    return "%s.%s" % (stem, digest), size


def _px(v):
    return None if v == UNDEF_PRICE else v / PRICE_SCALE


class WasrReplay:
    name = "LOB-WASR"
    exact_queues = True

    def __init__(self, wasr_path, symbol=""):
        import wasr
        self.file = wasr.File(wasr_path)
        self.path = wasr_path
        info = self.file.info
        self.info = info
        self.dataset = info.get("dataset", "")
        self.symbol = symbol
        self.n_events = int(info["n_events"])
        self.t0, self.t1 = int(info["first_ts"]), int(info["last_ts"])
        self._cursor = self.file.cursor()

    @classmethod
    def prepare(cls, src, symbol="", progress=None, cancel=None):
        """Index `src` (local path or ssh:// URL) into the cache if needed and open it. `progress(stage, done, total)`."""
        import wasr
        key, size = cache_key(src)
        d = cache_dir()
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, key + ".wasr")
        if not os.path.exists(out):
            local = src
            if is_remote(src):
                local = os.path.join(d, key + ".dbn.zst")
                if not os.path.exists(local):
                    _download(src, local, size, progress, cancel)
            if progress:
                progress("index", 0, 0)
            tmp = out + ".part"
            wasr.build(local, tmp, ckpt_events=20_000, block=20_000, align=True, threads=max(1, min(4, os.cpu_count() or 1)))
            os.replace(tmp, out)
            if local != src:
                os.remove(local)  # the .wasr holds the full stream (wasr export_dbn restores it)
        return cls(out, symbol)

    def _snap(self, s, ms):
        def side(levels):
            return [(lv["px"] / PRICE_SCALE, int(lv["size"]), int(lv["count"]),
                     [(int(o[0]), int(o[1])) for o in lv["orders"]] if "orders" in lv else None) for lv in levels]
        return {"pos": int(s["pos"]), "ts": int(s["ts_recv"]), "n_orders": int(s["n_orders"]),
                "bids": side(s["bid"]), "asks": side(s["ask"]), "ms": ms}

    def _seek(self, target, depth, queues):
        t = time.perf_counter()
        s = self._cursor.seek(target, level="L3" if queues else "L2", depth=depth)
        return self._snap(s, (time.perf_counter() - t) * 1e3)

    def seek(self, ts, depth=10, queues=False):
        """State after every event with ts_recv <= ts."""
        return self._seek(max(int(ts), 10 ** 12), depth, queues)

    def seek_pos(self, pos, depth=10, queues=False):
        """State after the first `pos` events."""
        return self._seek(min(max(int(pos), 0), self.n_events), depth, queues)

    def events(self, end, n=40):
        """The `n` events before position `end` (numpy, DBN mbo layout)."""
        return self.file.replay(max(0, end - n), end)

    def bbo(self, t0, t1):
        s = self.file.bbo_series(int(t0), int(t1))
        bid = s["bid_px"].astype(np.float64)
        ask = s["ask_px"].astype(np.float64)
        bid[s["bid_px"] == UNDEF_PRICE] = np.nan
        ask[s["ask_px"] == UNDEF_PRICE] = np.nan
        return {"t": s["ts_recv"].astype(np.float64) / 1e9, "bid": bid / PRICE_SCALE, "ask": ask / PRICE_SCALE}

    def trades(self, t0, t1):
        tr = self.file.trades(int(t0), int(t1))
        return {"t": tr["ts_recv"].astype(np.float64) / 1e9, "px": tr["price"].astype(np.float64) / PRICE_SCALE,
                "size": tr["size"].astype(np.float64), "side": tr["side"]}


def _download(src, dst, size, progress, cancel):
    tmp = dst + ".part"
    r = _CountingReader(src)
    try:
        with open(tmp, "wb") as f:
            while True:
                if cancel is not None and cancel():
                    raise RuntimeError("cancelled")
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                if progress:
                    progress("download", r.tell(), size)
    finally:
        r.close()
    got = os.path.getsize(tmp)
    if got != size:
        os.remove(tmp)
        raise OSError("download incomplete: %d of %d bytes" % (got, size))
    os.replace(tmp, dst)


class LoadedReplay:
    """Replay of the loaded MBO rows of one instrument, with a checkpoint every CKPT events."""

    name = "Python"
    exact_queues = False
    CKPT = 20_000

    def __init__(self, job, iid=None, progress=None):
        if iid is None:
            top = job.iid_counts.top(1)
            if not top:
                raise ValueError("no rows loaded")
            iid = int(top[0][0])
        parts = [p for rt, p, _ in job.iter_instrument(iid) if rt.cls == "MBOMsg"]
        if not parts:
            raise ValueError("no MBO rows loaded for this instrument")
        self.recs = np.concatenate(parts)
        self.iid = iid
        self.symbol = job.fi.symmap.lookup(iid) or str(iid)
        self.dataset = job.fi.md.get("dataset", "")
        self.n_events = len(self.recs)
        self.ts = self.recs["ts_recv"].astype(np.int64)
        self.t0, self.t1 = int(self.ts[0]), int(self.ts[-1])
        self._cols = [self.recs[c].tolist() for c in ("action", "side", "price", "size", "order_id", "flags")]
        # one pass: checkpoints + a sampled BBO line for the chart
        self.ckpts = []
        book = OrderBook()
        n = self.n_events
        sample = max(1, n // 4000)
        bt, bb, ba = [], [], []
        for i in range(n):
            if i % self.CKPT == 0:
                self.ckpts.append(_copy_book(book))
                if progress:
                    progress("index", i, n)
            book.apply(*(c[i] for c in self._cols))
            if i % sample == 0 or i == n - 1:
                b, a = book.depth(1)
                bt.append(self.ts[i] / 1e9)
                bb.append(b[0][0] if b else np.nan)
                ba.append(a[0][0] if a else np.nan)
        self._bbo = {"t": np.array(bt), "bid": np.array(bb), "ask": np.array(ba)}
        tm = self.recs["action"] == b"T"
        self._tr = {"t": self.ts[tm] / 1e9, "px": self.recs["price"][tm] / PRICE_SCALE,
                    "size": self.recs["size"][tm].astype(np.float64), "side": self.recs["side"][tm]}
        self._book, self._pos = OrderBook(), 0

    def _goto(self, pos):
        pos = min(max(int(pos), 0), self.n_events)
        k = min(pos // self.CKPT, len(self.ckpts) - 1)
        if not k * self.CKPT <= self._pos <= pos:  # continue forward only when no checkpoint lies in between
            self._book, self._pos = _copy_book(self.ckpts[k]), k * self.CKPT
        cols = self._cols
        for i in range(self._pos, pos):
            self._book.apply(cols[0][i], cols[1][i], cols[2][i], cols[3][i], cols[4][i], cols[5][i])
        self._pos = pos

    def _snap(self, depth, queues, ms):
        bids, asks = self._book.depth(depth)
        out = {"pos": self._pos, "ts": int(self.ts[self._pos - 1]) if self._pos else self.t0,
               "n_orders": len(self._book.orders), "ms": ms}
        if queues:
            q = {}
            for key, (side, px, sz) in self._book.orders.items():
                q.setdefault((side, px), []).append((key if isinstance(key, int) else 0, sz))
            out["bids"] = [(p, s, c, q.get((b"B", int(round(p * PRICE_SCALE))), [])) for p, s, c in bids]
            out["asks"] = [(p, s, c, q.get((b"A", int(round(p * PRICE_SCALE))), [])) for p, s, c in asks]
        else:
            out["bids"] = [(p, s, c, None) for p, s, c in bids]
            out["asks"] = [(p, s, c, None) for p, s, c in asks]
        return out

    def seek(self, ts, depth=10, queues=False):
        t = time.perf_counter()
        self._goto(int(np.searchsorted(self.ts, int(ts), side="right")))
        return self._snap(depth, queues, (time.perf_counter() - t) * 1e3)

    def seek_pos(self, pos, depth=10, queues=False):
        t = time.perf_counter()
        self._goto(pos)
        return self._snap(depth, queues, (time.perf_counter() - t) * 1e3)

    def events(self, end, n=40):
        return self.recs[max(0, end - n):end]

    def bbo(self, t0, t1):
        m = (self._bbo["t"] >= t0 / 1e9) & (self._bbo["t"] <= t1 / 1e9)
        return {k: v[m] for k, v in self._bbo.items()}

    def trades(self, t0, t1):
        m = (self._tr["t"] >= t0 / 1e9) & (self._tr["t"] <= t1 / 1e9)
        return {k: v[m] for k, v in self._tr.items()}


def _copy_book(book):
    c = OrderBook()
    c.orders = {k: list(v) for k, v in book.orders.items()}
    c.levels = {s: {p: list(v) for p, v in lv.items()} for s, lv in book.levels.items()}
    c.applied, c.had_clear = book.applied, book.had_clear
    return c


def open_replay(path, job=None, iid=None, symbol="", progress=None, cancel=None):
    """The best available replay for an MBO file: LOB-WASR when installed and the file holds one instrument,
    else the loaded rows. Returns (replay, note) where note explains a fallback (or "")."""
    note = ""
    if wasr_available():
        try:
            return WasrReplay.prepare(path, symbol, progress, cancel), ""
        except Exception as e:  # noqa: BLE001 - e.g. several instruments in one file, or a non-MBO file
            if str(e) == "cancelled":
                raise
            note = "LOB-WASR: %s" % e
    else:
        note = "wasr not installed"
    if job is None:
        raise RuntimeError(note)
    return LoadedReplay(job, iid, progress), note
