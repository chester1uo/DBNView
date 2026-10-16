"""File info cache and background scan jobs that load, filter and summarize records."""
import bisect
import collections
import os
import threading
import time
import uuid

import numpy as np

from .constants import UNDEF_TS
from .filters import Filter
from .formatting import format_column
from .metadata import _cstr, metadata_layout, parse_metadata
from .records import record_layout
from .sources import is_remote, open_stream, source_stat
from .stream import iter_records
from .symbology import SymbolMap


class Counts:
    """Mergeable integer histogram backed by numpy (fast for millions of keys)."""

    def __init__(self, dtype=np.int64):
        self.keys = np.zeros(0, dtype)
        self.cnts = np.zeros(0, np.int64)
        self.pk, self.pc, self.pending = [], [], 0

    def add(self, values):
        if len(values) == 0:
            return
        k, c = np.unique(values, return_counts=True)
        self.pk.append(k)
        self.pc.append(c)
        self.pending += len(k)
        if self.pending > 2_000_000:
            self.flush()

    def flush(self):
        if not self.pk:
            return
        k = np.concatenate([self.keys] + self.pk)
        c = np.concatenate([self.cnts] + self.pc)
        order = np.argsort(k, kind="stable")
        k, c = k[order], c[order]
        uk, start = np.unique(k, return_index=True)
        self.keys, self.cnts = uk, np.add.reduceat(c, start) if len(c) else c
        self.pk, self.pc, self.pending = [], [], 0

    def top(self, n):
        self.flush()
        if len(self.keys) == 0:
            return []
        idx = np.argsort(-self.cnts, kind="stable")[:n]
        return [(int(self.keys[i]), int(self.cnts[i])) for i in idx]

    def items(self):
        self.flush()
        return list(zip(self.keys.tolist(), self.cnts.tolist()))

    def __len__(self):
        self.flush()
        return len(self.keys)


class FileInfo:
    _cache = {}
    _lock = threading.Lock()

    def __init__(self, path):
        self.path = path
        self.size, self.mtime = source_stat(path)
        fh, st = open_stream(path)
        try:
            self.md = parse_metadata(st)
            # peek first records so the UI knows the record layout before any scan
            first = []
            for rt, arr in iter_records(st, self.md["version"], self.md["ts_out"], chunk=1 << 16,
                                        schema=self.md["schema"]):
                first.append(rt)
                break
            self.first_rt = first[0] if first else None
        finally:
            fh.close()
        self.symmap = SymbolMap(self.md)

    @classmethod
    def get(cls, path):
        if not is_remote(path):
            path = os.path.abspath(os.path.expanduser(path))
        with cls._lock:
            fi = cls._cache.get(path)
            if fi is None or (not is_remote(path) and fi.mtime != os.path.getmtime(path)):
                fi = cls._cache[path] = FileInfo(path)
            return fi

    def to_json(self):
        md = {k: v for k, v in self.md.items() if not k.startswith("_")}
        md["start"] = str(md["start"])
        md["end"] = None if md["end"] is None else str(md["end"])
        md["n_mappings"] = len(self.md["_mappings"])
        md["n_instruments"] = len(self.symmap.iv)
        md["symbols_preview"] = md["symbols"][:50]
        md["n_symbols"] = len(md["symbols"])
        del md["symbols"]
        rt = self.first_rt
        return {"path": self.path, "size": self.size, "compressed": self.path.endswith(".zst"),
                "remote": is_remote(self.path),
                "metadata": md,
                "record": None if rt is None else {
                    "rtype": rt.rtype, "name": rt.name, "cls": rt.cls, "size": rt.dtype.itemsize,
                    "fields": rt.order, "kinds": rt.kinds, "time_field": rt.time_field,
                    "layout": record_layout(rt)},
                "header_layout": metadata_layout(self.md)}


class Job:
    MAX_JOBS = 6
    jobs = collections.OrderedDict()
    lock = threading.Lock()

    def __init__(self, path, query):
        self.id = uuid.uuid4().hex[:12]
        self.fi = FileInfo.get(path)
        self.query = query
        self.filter = Filter(query, self.fi.md, self.fi.symmap)
        self.cap = int(query.get("cap") or 1_000_000)
        self.full = bool(query.get("full"))
        self.segments = []  # (RecordType, records ndarray, record index ndarray)
        self.seg_start = []  # cumulative start row of each segment
        self.n = 0
        self.seen = 0
        self.bytes_done = 0
        self.bytes_total = self.fi.size
        self.t_start = time.time()
        self.t_end = None
        self.done = False
        self.error = None
        self.cancelled = False
        self.truncated = False
        self.rt_counts = collections.Counter()
        self.action_counts = collections.Counter()
        self.side_counts = collections.Counter()
        self.iid_counts = Counts(np.int64)
        self.minute_counts = Counts(np.int64)
        self.tmin = self.tmax = None
        self.columns, self.kinds = ["_rec"], {"_rec": "rec"}
        self.rts = {}
        self._lock = threading.Lock()
        with Job.lock:
            Job.jobs[self.id] = self
            while len(Job.jobs) > Job.MAX_JOBS:
                _, old = Job.jobs.popitem(last=False)
                old.cancelled = True
        threading.Thread(target=self._run, daemon=True).start()

    # -- scanning --------------------------------------------------------
    def _add_columns(self, rt):
        if rt.cls in self.rts:
            return
        self.rts[rt.cls] = rt
        for f in rt.order:
            if f not in self.kinds:
                self.columns.append(f)
                self.kinds[f] = rt.kinds[f]
                if f == "instrument_id":
                    self.columns.append("symbol")
                    self.kinds["symbol"] = "sym"

    def _run(self):
        fh = None
        try:
            fh, st = open_stream(self.fi.path)
            md = parse_metadata(st)
            filt, symmap = self.filter, self.fi.symmap

            def on_bytes():
                self.bytes_done = fh.tell()

            for rt, arr in iter_records(st, md["version"], md["ts_out"], on_bytes=on_bytes, schema=md["schema"]):
                if self.cancelled:
                    break
                base = self.seen
                self.seen += len(arr)
                if rt.cls == "SymbolMappingMsg":
                    for r in arr:
                        symmap.add(int(r["instrument_id"]),
                                   _cstr(r["stype_out_symbol"]) or _cstr(r["stype_in_symbol"]))
                elif rt.cls == "InstrumentDefMsg" and "raw_symbol" in arr.dtype.names:
                    for iid, sym in zip(arr["instrument_id"].tolist(), arr["raw_symbol"].tolist()):
                        symmap.add(iid, _cstr(sym))
                m = filt.mask(arr, rt)
                if m is None:
                    sel, idx = arr, None
                else:
                    if not m.any():
                        continue
                    sel = arr[m]
                    idx = np.flatnonzero(m)
                k = len(sel)
                self.rt_counts[rt.name] += k
                self.iid_counts.add(sel["instrument_id"])
                t = sel[filt.tf(rt)]
                tv = t[t != UNDEF_TS]
                if len(tv):
                    lo, hi = int(tv.min()), int(tv.max())
                    self.tmin = lo if self.tmin is None else min(self.tmin, lo)
                    self.tmax = hi if self.tmax is None else max(self.tmax, hi)
                    self.minute_counts.add((tv // np.uint64(60_000_000_000)).astype(np.int64))
                for fld, ctr in (("action", self.action_counts), ("side", self.side_counts)):
                    if fld in sel.dtype.names and sel.dtype[fld].kind == "S":
                        u, c = np.unique(sel[fld], return_counts=True)
                        for a, b in zip(u.tolist(), c.tolist()):
                            ctr[a.decode("ascii", "replace") or "∅"] += b
                if self.n < self.cap:
                    take = min(self.cap - self.n, k)
                    recs = sel[:take].copy()
                    ridx = (np.arange(base, base + take, dtype=np.int64) if idx is None
                            else idx[:take].astype(np.int64) + base)
                    with self._lock:
                        self._add_columns(rt)
                        self.seg_start.append(self.n)
                        self.segments.append((rt, recs, ridx))
                        self.n += take
                    if take < k:
                        self.truncated = True
                if self.n >= self.cap and not self.full:
                    self.truncated = True
                    break
            self.bytes_done = fh.tell() if not self.truncated else self.bytes_done
        except Exception as e:  # surface to UI
            import traceback
            traceback.print_exc()
            self.error = "%s: %s" % (type(e).__name__, e)
        finally:
            if fh:
                fh.close()
            self.done = True
            self.t_end = time.time()

    # -- queries ---------------------------------------------------------
    def status(self, with_stats=False):
        el = (self.t_end or time.time()) - self.t_start
        out = {"id": self.id, "done": self.done, "error": self.error, "cancelled": self.cancelled,
               "truncated": self.truncated, "rows": self.n, "seen": self.seen, "cap": self.cap,
               "full": self.full, "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
               "elapsed": el, "columns": self.columns, "kinds": self.kinds,
               "filter": self.filter.desc, "book_safe": self.filter.book_safe,
               "classes": sorted(self.rts),
               "tmin": None if self.tmin is None else str(self.tmin),
               "tmax": None if self.tmax is None else str(self.tmax),
               "matched": sum(self.rt_counts.values())}
        if with_stats:
            sm = self.fi.symmap
            top = self.iid_counts.top(200)
            out["stats"] = {
                "rtype": dict(self.rt_counts), "action": dict(self.action_counts),
                "side": dict(self.side_counts), "n_instruments": len(self.iid_counts),
                "top": [[i, c, sm.lookup(i)] for i, c in top],
                "minutes": self.minute_counts.items()}
        return out

    def _locate(self, row):
        s = bisect.bisect_right(self.seg_start, row) - 1
        return s, row - self.seg_start[s]

    def rows(self, offset, limit, columns=None):
        with self._lock:
            segs = list(zip(self.seg_start, self.segments))
            n = self.n
        cols = columns or self.columns
        offset = max(0, min(offset, n))
        end = min(n, offset + limit)
        out = []
        if offset >= end:
            return {"offset": offset, "rows": out, "columns": cols}
        sm = self.fi.symmap
        si = bisect.bisect_right([s for s, _ in segs], offset) - 1
        while offset + len(out) < end and si < len(segs):
            s0, (rt, recs, ridx) = segs[si]
            a = offset + len(out) - s0
            b = min(len(recs), end - s0)
            part = recs[a:b]
            colvals = []
            for c in cols:
                colvals.append(format_column(c, part, rt, sm, ridx[a:b]))
            out.extend(list(r) for r in zip(*colvals))
            si += 1
        return {"offset": offset, "rows": out, "columns": cols}

    def seek(self, ts_ns):
        with self._lock:
            segs = list(zip(self.seg_start, self.segments))
        for s0, (rt, recs, _) in segs:
            t = recs[self.filter.tf(rt)]
            if len(t) and int(t[-1]) >= ts_ns:
                return s0 + int(np.searchsorted(t, np.uint64(ts_ns)))
        return self.n

    def iter_instrument(self, iid, upto=None):
        with self._lock:
            segs = list(zip(self.seg_start, self.segments))
        for s0, (rt, recs, ridx) in segs:
            if upto is not None and s0 > upto:
                break
            m = recs["instrument_id"] == iid
            if upto is not None and s0 + len(recs) > upto:
                m &= np.arange(len(recs)) <= upto - s0
            if m.any():
                yield rt, recs[m], np.flatnonzero(m) + s0

    def raw(self, row):
        """Bytes + byte layout (with raw values) of one loaded row."""
        s, i = self._locate(row)
        rt, recs, ridx = self.segments[s]
        rec = recs[i:i + 1]
        lay = record_layout(rt)
        vals = {}
        for n in rt.dtype.names:
            v = rec[n][0]
            if isinstance(v, bytes):
                v = v.decode("utf-8", "replace")
            elif hasattr(v, "item"):
                v = v.item()
            vals[n] = str(v) if isinstance(v, int) and abs(v) > 2 ** 53 else v
        for f in lay:
            f.append(vals.get(f[0]))
        return {"hex": rec.tobytes().hex(), "layout": lay, "rtype": rt.rtype, "name": rt.name,
                "cls": rt.cls, "rec": int(ridx[i])}
