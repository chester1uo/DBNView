"""instrument_id <-> symbol mapping from the metadata header and in-stream records."""
import collections
import datetime as dt
import threading

from .constants import UNDEF_TS


class SymbolMap:
    """instrument_id -> symbol, from the metadata mappings (+ in-stream records)."""

    def __init__(self, md):
        self.iv = collections.defaultdict(list)  # iid -> [(start_yyyymmdd, end_yyyymmdd, sym)]
        for raw, ivs in md["_mappings"]:
            for sd, ed, sym in ivs:
                if sym.isdigit():
                    iid, name = int(sym), raw
                elif raw.isdigit():
                    iid, name = int(raw), sym
                else:
                    continue
                self.iv[iid].append((sd, ed, name))
        self.static = {}
        self._rebuild()
        self.lock = threading.Lock()

    def _rebuild(self):
        self.static = {}
        for iid, ivs in self.iv.items():
            names = sorted({n for _, _, n in ivs})
            if len(names) == 1:
                self.static[iid] = names[0]

    def add(self, iid, name):
        if not name:
            return
        with self.lock:
            cur = self.static.get(iid)
            if cur is None or (cur != name and name not in cur.split(" | ")):
                if iid not in self.iv or not self.iv[iid]:
                    self.static[iid] = name
                    self.iv[iid] = [(0, 99999999, name)]

    def lookup(self, iid, ts_ns=None):
        s = self.static.get(iid)
        if s is not None:
            return s
        ivs = self.iv.get(iid)
        if not ivs:
            return None
        if ts_ns is not None and ts_ns != UNDEF_TS:
            d = dt.datetime.fromtimestamp(ts_ns / 1e9, dt.timezone.utc)
            ymd = d.year * 10000 + d.month * 100 + d.day
            hit = [n for sd, ed, n in ivs if sd <= ymd < ed]
            if hit:
                return " | ".join(sorted(set(hit)))
        return " | ".join(sorted({n for _, _, n in ivs}))

    def search(self, q, limit=200):
        q = q.strip()
        if not q:
            return []
        ql = q.lower()
        exact = q.endswith("$")
        if exact:
            ql = ql[:-1]
        by_name = collections.defaultdict(set)
        for iid, ivs in self.iv.items():
            for _, _, n in ivs:
                by_name[n].add(iid)
        out = []
        for n in sorted(by_name):
            nl = n.lower()
            if (nl == ql) if exact else (ql in nl):
                out.append((n, sorted(by_name[n])))
        return out

    def ids_matching(self, patterns):
        ids = set()
        for p in patterns:
            for _, iids in self.search(p, limit=10 ** 9):
                ids.update(iids)
        return ids

