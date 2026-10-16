#!/usr/bin/env python3
"""dbnview — a local web viewer for Databento DBN files (.dbn / .dbn.zst).

Reads DBN v1/v2/v3 directly (zstd streamed, nothing converted to disk).
Only needs numpy + zstandard; databento itself is NOT required.

    python dbnview.py                       # browse from the current directory
    python dbnview.py /data/databento        # browse from a directory
    python dbnview.py file.dbn.zst           # open a file straight away
    python dbnview.py file.dbn.zst --head 20 # print the first rows in the terminal

On a remote box: run it there, then `ssh -L 8765:localhost:8765 host` and open the
printed URL locally.
"""
import argparse
import ast
import base64
import collections
import csv
import datetime as dt
import io
import json
import os
import secrets
import struct
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
import zlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

try:
    import zstandard
except ImportError:  # pragma: no cover
    zstandard = None

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

__version__ = "0.1.0"
HERE = os.path.dirname(os.path.abspath(__file__))

_SPEC_B64 = None  # @@SPEC@@
_HTML_B64 = None  # @@HTML@@


def _asset(b64, fname):
    if b64 is not None:
        return zlib.decompress(base64.b64decode(b64)).decode("utf-8")
    for base in (HERE, getattr(sys, "_MEIPASS", HERE)):
        p = os.path.join(base, fname)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(fname)


SPEC = json.loads(_asset(_SPEC_B64, "spec.json"))
PUBLISHERS = {int(k): v for k, v in SPEC["pubs"].items()}

# ---------------------------------------------------------------------------
# DBN constants
# ---------------------------------------------------------------------------
UNDEF_PRICE = np.iinfo(np.int64).max
UNDEF_TS = np.iinfo(np.uint64).max
UNDEF_U32 = np.iinfo(np.uint32).max
PRICE_SCALE = 1e9

SCHEMAS = ["mbo", "mbp-1", "mbp-10", "tbbo", "trades", "ohlcv-1s", "ohlcv-1m", "ohlcv-1h",
           "ohlcv-1d", "definition", "statistics", "status", "imbalance", "ohlcv-eod",
           "cmbp-1", "cbbo-1s", "cbbo-1m", "tcbbo", "bbo-1s", "bbo-1m"]
STYPES = ["instrument_id", "raw_symbol", "smart", "continuous", "parent", "nasdaq_symbol",
          "cms_symbol", "isin", "us_code", "bbg_comp_id", "bbg_comp_ticker", "figi", "figi_ticker"]

RTYPES = {  # rtype -> (record class in spec, display name)
    0x00: ("TradeMsg", "trade"),
    0x01: ("MBP1Msg", "mbp-1"),
    0x0A: ("MBP10Msg", "mbp-10"),
    0x11: ("OHLCVMsg", "ohlcv"),
    0x12: ("StatusMsg", "status"),
    0x13: ("InstrumentDefMsg", "definition"),
    0x14: ("ImbalanceMsg", "imbalance"),
    0x15: ("ErrorMsg", "error"),
    0x16: ("SymbolMappingMsg", "symbol-mapping"),
    0x17: ("SystemMsg", "system"),
    0x18: ("StatMsg", "statistics"),
    0x20: ("OHLCVMsg", "ohlcv-1s"),
    0x21: ("OHLCVMsg", "ohlcv-1m"),
    0x22: ("OHLCVMsg", "ohlcv-1h"),
    0x23: ("OHLCVMsg", "ohlcv-1d"),
    0x24: ("OHLCVMsg", "ohlcv-eod"),
    0xA0: ("MBOMsg", "mbo"),
    0xB1: ("CMBP1Msg", "cmbp-1"),
    0xC0: ("CBBO1SMsg", "cbbo-1s"),
    0xC1: ("CBBO1MMsg", "cbbo-1m"),
    0xC2: ("TCBBOMsg", "tcbbo"),
    0xC3: ("BBO1SMsg", "bbo-1s"),
    0xC4: ("BBO1MMsg", "bbo-1m"),
}
HEADER_FIELDS = [["length", "u1"], ["rtype", "u1"], ["publisher_id", "u2"],
                 ["instrument_id", "u4"], ["ts_event", "u8"]]
FLAG_BITS = [(128, "LAST"), (64, "TOB"), (32, "SNAPSHOT"), (16, "MBP"),
             (8, "BAD_TS_RECV"), (4, "MAYBE_BAD_BOOK"), (2, "PUBLISHER_SPECIFIC")]


class RecordType:
    """numpy dtype + display info for one (version, rtype, record length)."""

    def __init__(self, version, rtype, length, ts_out):
        cls, name = RTYPES.get(rtype, (None, "rtype-%d" % rtype))
        spec = SPEC["versions"].get(str(min(max(version, 1), 3)), {}).get(cls) if cls else None
        fields = [tuple(f) for f in (spec["f"] if spec else HEADER_FIELDS)]
        base = np.dtype(fields)
        if base.itemsize > length:  # unexpected layout: fall back to the common header
            spec, base = None, np.dtype([tuple(f) for f in HEADER_FIELDS])
        names, formats, offsets = list(base.names), [base.fields[n][0] for n in base.names], \
            [base.fields[n][1] for n in base.names]
        if ts_out and length >= base.itemsize + 8:
            names.append("ts_out")
            formats.append(np.dtype("u8"))
            offsets.append(length - 8)
        self.dtype = np.dtype({"names": names, "formats": formats, "offsets": offsets,
                               "itemsize": max(length, base.itemsize)})
        self.cls = cls or name
        self.name = name
        self.rtype = rtype
        self.known = spec is not None
        if spec:
            order = list(spec["ord"])
            self.px = set(spec["px"])
            self.ts = set(spec["ts"])
        else:
            order = ["ts_event", "rtype", "publisher_id", "instrument_id"]
            self.px, self.ts = set(), {"ts_event"}
        if "ts_out" in names:
            order.append("ts_out")
            self.ts.add("ts_out")
        self.order = order
        self.kinds = {}
        for f in order:
            fmt = self.dtype.fields[f][0]
            if f in self.px:
                k = "px"
            elif f in self.ts:
                k = "ts"
            elif f == "flags":
                k = "flags"
            elif f == "publisher_id" or "_pb_" in f:
                k = "pub"
            elif fmt.kind == "S":
                k = "chr" if fmt.itemsize == 1 else "str"
            else:
                k = "int"
            self.kinds[f] = k
        self.time_field = "ts_recv" if "ts_recv" in names else "ts_event"
        # integer fields whose type-maximum means "undefined" (DBN null sentinels)
        self.nulls = {}
        for f in order:
            fmt = self.dtype.fields[f][0]
            if self.kinds[f] != "int" or fmt.kind not in "iu" or f in ("rtype", "length"):
                continue
            if self.cls in NULL_MAX_CLASSES or (f == "size" and fmt.kind == "u" and fmt.itemsize == 4):
                self.nulls[f] = int(np.iinfo(fmt).max)


NULL_MAX_CLASSES = {"InstrumentDefMsg", "StatMsg", "ErrorMsg", "SystemMsg", "StatusMsg", "ImbalanceMsg"}
_RT_CACHE = {}


def record_type(version, rtype, length, ts_out, schema=None):
    key = (version, rtype, length, ts_out, schema == "tbbo" and rtype == 0x01)
    rt = _RT_CACHE.get(key)
    if rt is None:
        rt = _RT_CACHE[key] = RecordType(version, rtype, length, ts_out)
        if key[-1]:  # DBN v1-v3 store TBBO records under the MBP-1 rtype
            rt.name = "tbbo"
    return rt


# ---------------------------------------------------------------------------
# Metadata + streaming
# ---------------------------------------------------------------------------
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ControlMaster=auto",
            "-o", "ControlPath=~/.ssh/dbnview-%r@%h:%p", "-o", "ControlPersist=120"]


def is_remote(path):
    return path.startswith("ssh://")


def split_remote(path):
    """'ssh://host/abs/path' -> (host, '/abs/path')"""
    rest = path[6:]
    host, _, p = rest.partition("/")
    return host, "/" + p


def ssh_run(host, cmd, timeout=30):
    import subprocess
    r = subprocess.run(["ssh"] + SSH_OPTS + [host, cmd], capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise OSError("ssh %s: %s" % (host, r.stderr.decode(errors="replace").strip() or r.returncode))
    return r.stdout.decode("utf-8", "replace")


def source_stat(path):
    """(size, mtime) of a local path or ssh://host/path."""
    if is_remote(path):
        import shlex
        host, p = split_remote(path)
        size, mtime = ssh_run(host, "stat -L -c '%s %Y' " + shlex.quote(p)).split()
        return int(size), float(mtime)
    st = os.stat(path)
    return st.st_size, st.st_mtime


def list_dir(path):
    """Directory entries (dirs + DBN files) of a local or ssh:// directory."""
    ents = []
    keep = lambda n: n.endswith((".dbn", ".dbn.zst", ".zst"))
    if is_remote(path):
        import shlex
        host, p = split_remote(path)
        out = ssh_run(host, "find %s -mindepth 1 -maxdepth 1 -printf '%%y\\t%%s\\t%%T@\\t%%f\\n'"
                      % shlex.quote(p))
        for line in out.splitlines():
            parts = line.split("\t", 3)
            if len(parts) != 4 or parts[3].startswith("."):
                continue
            typ, size, mtime, name = parts
            if typ == "d":
                ents.append({"name": name, "dir": True})
            elif keep(name):
                ents.append({"name": name, "dir": False, "size": int(size), "mtime": float(mtime)})
    else:
        with os.scandir(path) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir():
                        ents.append({"name": e.name, "dir": True})
                    elif keep(e.name):
                        st = e.stat()
                        ents.append({"name": e.name, "dir": False, "size": st.st_size, "mtime": st.st_mtime})
                except OSError:
                    pass
    ents.sort(key=lambda x: (not x["dir"], x["name"]))
    return ents


class _CountingReader:
    """Raw byte source with .read/.tell/.close; local file or `ssh host cat path`."""

    def __init__(self, path):
        self.n = 0
        self.proc = None
        self.prefix = b""
        if is_remote(path):
            import shlex
            import subprocess
            host, p = split_remote(path)
            self.proc = subprocess.Popen(["ssh"] + SSH_OPTS + [host, "cat " + shlex.quote(p)],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            self.f = self.proc.stdout
        else:
            self.f = open(path, "rb")

    def peek(self, k):
        while len(self.prefix) < k:
            b = self.f.read(k - len(self.prefix))
            if not b:
                break
            self.prefix += b
        if not self.prefix and self.proc is not None:
            self.proc.wait(timeout=30)
            raise OSError("ssh: " + self.proc.stderr.read().decode(errors="replace").strip())
        return self.prefix[:k]

    def read(self, k=-1):
        if self.prefix:
            out, self.prefix = self.prefix[:k] if k >= 0 else self.prefix, \
                self.prefix[k:] if k >= 0 else b""
            self.n += len(out)
            return out
        b = self.f.read(k) if k >= 0 else self.f.read()
        self.n += len(b)
        return b

    def readinto(self, buf):
        b = self.read(len(buf))
        buf[:len(b)] = b
        return len(b)

    def readable(self):
        return True

    def tell(self):
        return self.n

    def close(self):
        try:
            self.f.close()
        finally:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()


def open_stream(path):
    """Return (raw byte source with .tell(), decoded DBN byte stream)."""
    fh = _CountingReader(path)
    magic = fh.peek(4)
    if magic == b"\x28\xb5\x2f\xfd":
        if zstandard is None:
            raise RuntimeError("pip install zstandard  (needed for .zst files)")
        try:
            rd = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20,
                                                             read_across_frames=True)
        except TypeError:  # very old zstandard
            rd = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20)
        return fh, rd
    return fh, fh


def _readn(f, n):
    out = bytearray()
    while len(out) < n:
        b = f.read(n - len(out))
        if not b:
            break
        out += b
    return bytes(out)


def _cstr(b):
    return b.split(b"\0", 1)[0].decode("utf-8", "replace")


def parse_metadata(f):
    head = _readn(f, 8)
    if len(head) < 8 or head[:3] != b"DBN":
        raise ValueError("not a DBN stream (missing 'DBN' magic)")
    ver = head[3]
    if ver > 3:
        raise ValueError("DBN v%d is not supported yet (this viewer reads v1-v3)" % ver)
    (n,) = struct.unpack("<I", head[4:8])
    b = _readn(f, n)
    md = {"version": ver, "dataset": _cstr(b[0:16])}
    (schema,) = struct.unpack_from("<H", b, 16)
    start, end, limit = struct.unpack_from("<QQQ", b, 18)
    p = 42
    if ver == 1:
        (md["record_count"],) = struct.unpack_from("<Q", b, p)
        p += 8
    stype_in, stype_out, ts_out = b[p], b[p + 1], b[p + 2]
    p += 3
    if ver >= 2:
        (cl,) = struct.unpack_from("<H", b, p)
        p += 2 + 53
    else:
        cl = 22
        p += 47
    (sdl,) = struct.unpack_from("<I", b, p)
    p += 4 + sdl

    def strs():
        nonlocal p
        (cnt,) = struct.unpack_from("<I", b, p)
        p += 4
        out = [_cstr(b[p + i * cl:p + (i + 1) * cl]) for i in range(cnt)]
        p += cnt * cl
        return out

    md["symbols"], md["partial"], md["not_found"] = strs(), strs(), strs()
    (cnt,) = struct.unpack_from("<I", b, p)
    p += 4
    mappings = []
    for _ in range(cnt):
        raw = _cstr(b[p:p + cl])
        p += cl
        (icnt,) = struct.unpack_from("<I", b, p)
        p += 4
        ivs = []
        for _ in range(icnt):
            sd, ed = struct.unpack_from("<II", b, p)
            p += 8
            ivs.append((sd, ed, _cstr(b[p:p + cl])))
            p += cl
        mappings.append((raw, ivs))
    md.update(
        schema=None if schema == 0xFFFF else (SCHEMAS[schema] if schema < len(SCHEMAS) else str(schema)),
        start=start, end=None if end == UNDEF_TS else end,
        limit=limit, stype_in=None if stype_in == 255 else STYPES[stype_in] if stype_in < len(STYPES) else stype_in,
        stype_out=STYPES[stype_out] if stype_out < len(STYPES) else stype_out,
        ts_out=bool(ts_out), symbol_cstr_len=cl, header_bytes=8 + n)
    md["_mappings"] = mappings
    return md


def _typename(fmt):
    if fmt.kind == "S":
        return "char" if fmt.itemsize == 1 else "char[%d]" % fmt.itemsize
    return {"u": "u", "i": "i", "f": "f"}.get(fmt.kind, fmt.kind) + str(fmt.itemsize * 8)


def record_layout(rt):
    """[(name, offset, size, type)] in byte order, including padding/reserved fields."""
    out = []
    for n in rt.dtype.names:
        fmt, off = rt.dtype.fields[n][:2]
        out.append([n, off, fmt.itemsize, _typename(fmt)])
    out.sort(key=lambda x: x[1])
    end = rt.dtype.itemsize
    last = out[-1][1] + out[-1][2] if out else 0
    if last < end:
        out.append(["(padding)", last, end - last, "bytes"])
    return out


def metadata_layout(md, t=lambda s: s):
    """Byte map of the DBN metadata header for this file (offsets from file start, decoded)."""
    v, cl = md["version"], md["symbol_cstr_len"]
    L = [["magic", 0, 3, "char[3]", "DBN"], ["version", 3, 1, "u8", v],
         ["length", 4, 4, "u32", md["header_bytes"] - 8],
         ["dataset", 8, 16, "char[16]", md["dataset"]], ["schema", 24, 2, "u16", md["schema"] or "mixed (0xFFFF)"],
         ["start", 26, 8, "u64", str(md["start"])],
         ["end", 34, 8, "u64", str(md["end"]) if md["end"] is not None else "UNDEF"],
         ["limit", 42, 8, "u64", md["limit"]]]
    p = 50
    if v == 1:
        L.append(["record_count", 50, 8, "u64", md.get("record_count")])
        p = 58
    L += [["stype_in", p, 1, "u8", md["stype_in"]], ["stype_out", p + 1, 1, "u8", md["stype_out"]],
          ["ts_out", p + 2, 1, "u8", int(md["ts_out"])]]
    p += 3
    if v >= 2:
        L.append(["symbol_cstr_len", p, 2, "u16", cl])
        p += 2
        L.append(["_reserved", p, 53, "bytes", ""])
        p += 53
    else:
        L.append(["_reserved", p, 47, "bytes", t("(v1: symbol length fixed at 22)")])
        p += 47
    L.append(["schema_definition_length", p, 4, "u32", 0])
    p += 4
    for name in ("symbols", "partial", "not_found"):
        n = len(md[name])
        L.append([name, p, 4 + n * cl, "u32 + %d×char[%d]" % (n, cl),
                  ", ".join(md[name][:5]) + (" …" if n > 5 else "")])
        p += 4 + n * cl
    mb = 4 + sum(cl + 4 + len(ivs) * (8 + cl) for _, ivs in md["_mappings"])
    ex = md["_mappings"][0] if md["_mappings"] else None
    L.append(["mappings", p, mb, t("u32 + each: char[{cl}] raw_symbol, u32 n, n×(u32 start_date, u32 end_date, char[{cl}])").format(cl=cl),
              t("{n} entries").format(n=len(md["_mappings"])) +
              (t("; e.g. {a} → {b}").format(a=ex[0], b=ex[1][0][2]) if ex and ex[1] else "")])
    p += mb
    if p < md["header_bytes"]:
        L.append(["(padding)", p, md["header_bytes"] - p, "bytes", t("padded to 8-byte alignment")])
        p = md["header_bytes"]
    L.append(["(records start)", p, 0, "", t("first record starts at byte {p} (decompressed)").format(p=p)])
    return L


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


def _prefetch(stream, chunk, depth=3):
    """Decompress on a background thread (zstd releases the GIL) while the caller parses."""
    import queue
    q = queue.Queue(maxsize=depth)
    stop = threading.Event()

    def work():
        try:
            while not stop.is_set():
                data = stream.read(chunk)
                q.put(data)
                if not data:
                    return
        except Exception as e:  # pragma: no cover
            q.put(e)

    threading.Thread(target=work, daemon=True).start()
    try:
        while True:
            data = q.get()
            if isinstance(data, Exception):
                raise data
            if not data:
                return
            yield data
    finally:
        stop.set()
        while not q.empty():
            q.get_nowait()


def iter_records(stream, version, ts_out, chunk=8 << 20, on_bytes=None, schema=None):
    """Yield (RecordType, ndarray) runs of same-type records from a decoded DBN body."""
    buf = b""
    for data in _prefetch(stream, chunk):
        buf = buf + data if buf else data
        if on_bytes:
            on_bytes()
        p, n = 0, len(buf)
        while n - p >= 16:
            L = buf[p] * 4
            if L < 16:
                raise ValueError("corrupt record header at decoded offset (length=%d)" % L)
            r = buf[p + 1]
            k = (n - p) // L
            if k == 0:
                break
            u8 = np.frombuffer(buf, np.uint8, count=k * L, offset=p).reshape(k, L)
            bad = (u8[:, 0] != buf[p]) | (u8[:, 1] != r)
            if bad.any():
                k = int(bad.argmax())
            rt = record_type(version, r, L, ts_out, schema)
            yield rt, np.frombuffer(buf, rt.dtype, count=k, offset=p)
            p += k * L
        buf = buf[p:]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
_TZ_CACHE = {}


def _tz(name):
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
    z = _tz(tz)
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


_ALLOWED_FUNCS = {"abs": np.abs, "isnan": np.isnan}


class WhereExpr:
    """A tiny, safe numpy expression: `size > 10 and side == 'B'`, `ask_px_00 - bid_px_00 < 0.05`.
    Prices are in real units (float), undefined prices are NaN."""

    def __init__(self, text):
        self.text = text
        self.tree = ast.parse(text, mode="eval")
        for node in ast.walk(self.tree):
            ok = isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
                                   ast.USub, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
                                   ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
                                   ast.Name, ast.Load, ast.Constant, ast.Call, ast.BitAnd, ast.BitOr,
                                   ast.In, ast.NotIn, ast.Tuple, ast.List))
            if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name)
                                                   and node.func.id in _ALLOWED_FUNCS):
                ok = False
            if not ok:
                raise ValueError("unsupported syntax in where: %s" % type(node).__name__)

    def __call__(self, arr, rt):
        cache = {}

        def name(n):
            if n in _ALLOWED_FUNCS:
                return _ALLOWED_FUNCS[n]
            if n not in cache:
                if n not in arr.dtype.names:
                    raise KeyError(n)
                v = arr[n]
                if n in rt.px:
                    v = np.where(v == UNDEF_PRICE, np.nan, v / PRICE_SCALE)
                cache[n] = v
            return cache[n]

        def const(v):
            return v.encode() if isinstance(v, str) else v

        def ev(nd):
            if isinstance(nd, ast.Expression):
                return ev(nd.body)
            if isinstance(nd, ast.BoolOp):
                vals = [ev(v) for v in nd.values]
                out = vals[0]
                for v in vals[1:]:
                    out = (out & v) if isinstance(nd.op, ast.And) else (out | v)
                return out
            if isinstance(nd, ast.UnaryOp):
                v = ev(nd.operand)
                return ~v if isinstance(nd.op, ast.Not) else -v
            if isinstance(nd, ast.BinOp):
                a, b = ev(nd.left), ev(nd.right)
                if isinstance(nd.op, (ast.Add, ast.Sub)):
                    r = (np.add if isinstance(nd.op, ast.Add) else np.subtract)(a, b)
                    return np.round(r, 9) if np.asarray(r).dtype.kind == "f" else r
                return {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
                        ast.Div: np.true_divide, ast.Mod: np.mod, ast.BitAnd: np.bitwise_and,
                        ast.BitOr: np.bitwise_or}[type(nd.op)](a, b)
            if isinstance(nd, ast.Compare):
                left, out = ev(nd.left), None
                for op, rc in zip(nd.ops, nd.comparators):
                    right = ev(rc)
                    if isinstance(op, (ast.In, ast.NotIn)):
                        r = np.isin(left, list(right))
                        r = ~r if isinstance(op, ast.NotIn) else r
                    else:
                        r = {ast.Eq: np.equal, ast.NotEq: np.not_equal, ast.Lt: np.less,
                             ast.LtE: np.less_equal, ast.Gt: np.greater,
                             ast.GtE: np.greater_equal}[type(op)](left, right)
                    out = r if out is None else (out & r)
                    left = right
                return out
            if isinstance(nd, ast.Name):
                return name(nd.id)
            if isinstance(nd, ast.Constant):
                return const(nd.value)
            if isinstance(nd, (ast.Tuple, ast.List)):
                return [ev(e) for e in nd.elts]
            if isinstance(nd, ast.Call):
                return name(nd.func.id)(*[ev(a) for a in nd.args])
            raise ValueError(type(nd).__name__)

        res = ev(self.tree)
        if np.ndim(res) == 0:
            return np.full(len(arr), bool(res))
        return np.asarray(res, dtype=bool)


class Filter:
    def __init__(self, q, md, symmap):
        self.desc = []
        ids = set()
        syms = [s for s in (q.get("symbols") or []) if s.strip()]
        if syms:
            found = symmap.ids_matching(syms)
            ids |= found
            self.desc.append("symbol∈%s (%d ids)" % (syms, len(found)))
        for tok in str(q.get("iids") or "").replace(",", " ").split():
            ids.add(int(tok))
        if syms or q.get("iids"):
            self.desc.append("instrument_id filter: %d ids" % len(ids))
        self.iids = np.array(sorted(ids), dtype=np.uint32) if (syms or q.get("iids")) else None
        tz = q.get("tz") or "UTC"
        self.tfield = q.get("tfield") or "auto"
        self.t0 = parse_time(q.get("t0"), tz, md.get("start"))
        self.t1 = parse_time(q.get("t1"), tz, md.get("start"))
        self.rtypes = set(int(x) for x in (q.get("rtypes") or []))
        self.actions = [a.encode() for a in (q.get("actions") or [])]
        self.sides = [s.encode() for s in (q.get("sides") or [])]
        w = (q.get("where") or "").strip()
        self.where = WhereExpr(w) if w else None
        self.trivial = (self.iids is None and self.t0 is None and self.t1 is None and not self.rtypes
                        and not self.actions and not self.sides and self.where is None)
        # an MBO book can only be rebuilt when no earlier message of an instrument was dropped
        self.book_safe = (self.t0 is None and not self.actions and not self.sides
                          and self.where is None and not self.rtypes)

    def tf(self, rt):
        if self.tfield != "auto" and self.tfield in rt.dtype.names:
            return self.tfield
        return rt.time_field

    def mask(self, arr, rt):
        if self.trivial:
            return None
        m = np.ones(len(arr), dtype=bool)
        if self.rtypes and rt.rtype not in self.rtypes:
            m[:] = False
            return m
        if self.iids is not None:
            m &= np.isin(arr["instrument_id"], self.iids)
        if self.t0 is not None or self.t1 is not None:
            t = arr[self.tf(rt)]
            if self.t0 is not None:
                m &= t >= np.uint64(self.t0)
            if self.t1 is not None:
                m &= t < np.uint64(self.t1)
        if self.actions and "action" in arr.dtype.names and arr.dtype["action"].kind == "S":
            m &= np.isin(arr["action"], self.actions)
        if self.sides and "side" in arr.dtype.names:
            m &= np.isin(arr["side"], self.sides)
        if self.where is not None and m.any():
            try:
                m &= self.where(arr, rt)
            except KeyError:  # field not in this record type -> no match
                m[:] = False
        return m


# ---------------------------------------------------------------------------
# Scan jobs
# ---------------------------------------------------------------------------
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
        import bisect
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
        import bisect
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

    def chart(self, iid, maxpts=6000):
        xs, cols, names = [], collections.defaultdict(list), []
        size_x, sizes = [], []
        for rt, recs, _ in self.iter_instrument(iid):
            t = recs[self.filter.tf(rt)]
            ok = t != UNDEF_TS
            recs, t = recs[ok], t[ok]
            xs.append(t.astype(np.float64) / 1e9)
            for f in rt.order:
                if f in rt.px:
                    if f not in names:
                        names.append(f)
            for f in names:
                if f in recs.dtype.names:
                    v = recs[f]
                    cols[f].append(np.where(v == UNDEF_PRICE, np.nan, v / PRICE_SCALE))
                else:
                    cols[f].append(np.full(len(recs), np.nan))
        if not xs:
            return {"x": [], "series": {}}
        x = np.concatenate(xs)
        ser = {f: np.concatenate(cols[f]) for f in names}
        ser = {f: v for f, v in ser.items() if np.isfinite(v).any()}
        n = len(x)
        if n > maxpts:
            nb = maxpts // 2
            starts = np.linspace(0, n, nb + 1).astype(np.int64)[:-1]
            starts = np.unique(starts)
            ends = np.append(starts[1:], n) - 1
            nx = np.empty(len(starts) * 2)
            nx[0::2], nx[1::2] = x[starts], x[ends]
            out = {}
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    for f, v in ser.items():
                        lo = np.fmin.reduceat(v, starts)
                        hi = np.fmax.reduceat(v, starts)
                        nv = np.empty(len(starts) * 2)
                        nv[0::2], nv[1::2] = lo, hi
                        out[f] = nv
            x, ser = nx, out
        clean = lambda a: [None if not np.isfinite(v) else round(float(v), 9) for v in a]
        return {"x": x.tolist(), "series": {f: clean(v) for f, v in ser.items()}, "n": n,
                "downsampled": n > maxpts}

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

    def book(self, row, depth=20):
        s, i = self._locate(row)
        rt, recs, _ = self.segments[s]
        iid = int(recs["instrument_id"][i])
        orders = {}
        bids, asks = collections.defaultdict(lambda: [0, 0]), collections.defaultdict(lambda: [0, 0])
        applied, had_clear = 0, False
        for rt2, part, _ in self.iter_instrument(iid, upto=row):
            if rt2.cls != "MBOMsg":
                continue
            A = part["action"].tolist()
            S = part["side"].tolist()
            P = part["price"].tolist()
            Z = part["size"].tolist()
            O = part["order_id"].tolist()
            F = part["flags"].tolist()
            for a, sd, px, sz, oid, fl in zip(A, S, P, Z, O, F):
                applied += 1
                if a == b"R":
                    had_clear = True
                    orders.clear()
                    continue
                if fl & 64 and a == b"A":  # top-of-book style message: replaces that side's top
                    for k in [k for k, o in orders.items() if o[0] == sd]:
                        del orders[k]
                    if px != UNDEF_PRICE:
                        orders[("tob", sd)] = [sd, px, sz]
                    continue
                if a == b"A":
                    orders[oid] = [sd, px, sz]
                elif a == b"C":
                    o = orders.get(oid)
                    if o is not None:
                        o[2] -= sz
                        if o[2] <= 0:
                            del orders[oid]
                elif a == b"M":
                    o = orders.get(oid)
                    if o is None:
                        orders[oid] = [sd, px, sz]
                    else:
                        o[1], o[2] = px, sz
        for sd, px, sz in orders.values():
            lv = (bids if sd == b"B" else asks)[px]
            lv[0] += sz
            lv[1] += 1
        b = sorted(bids.items(), key=lambda kv: -kv[0])[:depth]
        a = sorted(asks.items(), key=lambda kv: kv[0])[:depth]
        fmt = lambda lv: [[p / PRICE_SCALE, v[0], v[1]] for p, v in lv]
        return {"instrument_id": iid, "symbol": self.fi.symmap.lookup(iid), "applied": applied,
                "orders": len(orders), "bids": fmt(b), "asks": fmt(a),
                "safe": self.filter.book_safe, "had_clear": had_clear}


def format_column(c, part, rt, sm, ridx):
    n = len(part)
    if c == "symbol":
        iids = part["instrument_id"].tolist()
        tf = part[rt.time_field].tolist()
        return [sm.lookup(i, t) for i, t in zip(iids, tf)]
    if c == "_rec":
        return ridx.tolist()
    if c not in part.dtype.names:
        return [None] * n
    v = part[c]
    k = rt.kinds.get(c, "int")
    if k == "px":
        und = v == UNDEF_PRICE
        out = (v / PRICE_SCALE).tolist()
        if und.any():
            for i in np.flatnonzero(und).tolist():
                out[i] = None
        return out
    if k == "ts":
        return [None if x == UNDEF_TS else str(x) for x in v.tolist()]
    if v.dtype.kind == "S":
        return [x.decode("utf-8", "replace") for x in v.tolist()]
    if v.dtype.kind == "f":
        return [None if x != x else x for x in v.tolist()]
    nul = rt.nulls.get(c)
    if nul is not None:
        out = v.tolist()
        return [None if x == nul else (str(x) if abs(x) > 2 ** 53 else x) for x in out]
    if v.dtype.kind == "u" and v.dtype.itemsize == 8:
        return [str(x) if x > 2 ** 53 else x for x in v.tolist()]
    if v.dtype.kind == "i" and v.dtype.itemsize == 8:
        return [None if x == UNDEF_PRICE else (str(x) if abs(x) > 2 ** 53 else x) for x in v.tolist()]
    return v.tolist()


def fmt_ts(ns, tz=dt.timezone.utc):
    if ns is None:
        return ""
    ns = int(ns)
    d = dt.datetime.fromtimestamp(ns // 1_000_000_000, tz)
    return d.strftime("%Y-%m-%d %H:%M:%S") + ".%09d" % (ns % 1_000_000_000)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class App:
    def __init__(self, roots, token, open_path=None):
        self.roots = roots
        self.token = token
        self.open_path = open_path
        self.html = _asset(_HTML_B64, "ui.html")


def _json(obj):
    return json.dumps(obj, separators=(",", ":"), default=str, allow_nan=False).encode()


class Handler(BaseHTTPRequestHandler):
    app: App = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authed(self, qs):
        tok = self.app.token
        if not tok:
            return True
        if qs.get("token", [None])[0] == tok:
            return True
        if self.headers.get("X-Token") == tok:
            return True
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return "dbnview" in c and c["dbnview"].value == tok

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if not self._authed(qs):
            return self._send(403, b"forbidden: open the URL with ?token=... printed in the terminal",
                              "text/plain")
        try:
            if u.path in ("/", "/index.html"):
                cookie = {"Set-Cookie": "dbnview=%s; HttpOnly; SameSite=Strict; Path=/" % self.app.token} \
                    if self.app.token else {}
                return self._send(200, self.app.html.encode(), "text/html; charset=utf-8", cookie)
            if u.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if u.path == "/api/export":
                return self._export(qs)
            fn = getattr(self, "api_" + u.path[5:], None) if u.path.startswith("/api/") else None
            if fn is None:
                return self._send(404, b'{"error":"not found"}')
            return self._send(200, _json(fn({k: v[0] for k, v in qs.items()})))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send(400, _json({"error": "%s: %s" % (type(e).__name__, e)}))

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if not self._authed(qs):
            return self._send(403, b'{"error":"forbidden"}')
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            fn = getattr(self, "post_" + u.path[5:], None)
            if fn is None:
                return self._send(404, b'{"error":"not found"}')
            return self._send(200, _json(fn(body)))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send(400, _json({"error": "%s: %s" % (type(e).__name__, e)}))

    # --- api ---
    def api_init(self, q):
        return {"roots": self.app.roots, "open": self.app.open_path, "version": __version__,
                "cwd": os.getcwd(), "home": os.path.expanduser("~"), "publishers": PUBLISHERS}

    def api_ls(self, q):
        d = q.get("dir") or self.app.roots[0]
        if not is_remote(d):
            d = os.path.abspath(os.path.expanduser(d))
            if os.path.isfile(d):
                d = os.path.dirname(d)
        parent = d.rsplit("/", 1)[0] or "/"
        if is_remote(d) and len(split_remote(d)[1]) <= 1:
            parent = d
        return {"dir": d, "parent": parent, "entries": list_dir(d)}

    def api_meta(self, q):
        return FileInfo.get(q["path"]).to_json()

    def api_symbols(self, q):
        fi = FileInfo.get(q["path"])
        res = fi.symmap.search(q.get("q", ""))
        lim = int(q.get("limit", 50))
        return {"total": len(res), "items": [[n, ids[:5], len(ids)] for n, ids in res[:lim]]}

    def post_scan(self, body):
        old = body.get("cancel")
        if old and old in Job.jobs:
            Job.jobs[old].cancelled = True
        job = Job(body["path"], body.get("query") or {})
        return job.status()

    def _job(self, q):
        j = Job.jobs.get(q.get("id"))
        if j is None:
            raise KeyError("scan expired, run it again")
        return j

    def api_job(self, q):
        return self._job(q).status(with_stats=q.get("stats") == "1")

    def api_cancel(self, q):
        j = self._job(q)
        j.cancelled = True
        return j.status()

    def api_rows(self, q):
        j = self._job(q)
        cols = q.get("cols")
        return j.rows(int(q.get("offset", 0)), min(int(q.get("limit", 200)), 5000),
                      cols.split(",") if cols else None)

    def api_seek(self, q):
        j = self._job(q)
        ns = parse_time(q["t"], q.get("tz", "UTC"), j.tmin or j.fi.md["start"])
        return {"row": j.seek(ns)}

    def api_chart(self, q):
        j = self._job(q)
        iid = q.get("iid")
        if not iid:
            top = j.iid_counts.top(1)
            if not top:
                return {"x": [], "series": {}}
            iid = top[0][0]
        res = j.chart(int(iid), int(q.get("max", 6000)))
        res["instrument_id"] = int(iid)
        res["symbol"] = j.fi.symmap.lookup(int(iid))
        return res

    def api_raw(self, q):
        return self._job(q).raw(int(q["row"]))

    def api_book(self, q):
        return self._job(q).book(int(q["row"]), int(q.get("depth", 20)))

    def _export(self, qs):
        j = self._job({k: v[0] for k, v in qs.items()})
        tzname = qs.get("tz", ["UTC"])[0]
        tz = _tz(tzname)
        name = os.path.basename(j.fi.path).replace(".dbn.zst", "").replace(".dbn", "") + ".csv"
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        cols = j.columns

        def chunk(s):
            b = s.encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(b), b))

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for off in range(0, j.n, 20000):
            res = j.rows(off, 20000)
            for r in res["rows"]:
                w.writerow([fmt_ts(v, tz) if j.kinds.get(c) == "ts" and v is not None else
                            ("" if v is None else v) for c, v in zip(cols, r)])
            chunk(buf.getvalue())
            buf.seek(0)
            buf.truncate()
        chunk(buf.getvalue()) if buf.getvalue() else None
        self.wfile.write(b"0\r\n\r\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def print_head(path, n, tz):
    fi = FileInfo.get(path)
    md = fi.md
    print("%s  DBN v%d  %s  %s  %s -> %s  stype %s->%s  %d mappings" % (
        os.path.basename(path), md["version"], md["dataset"], md["schema"],
        fmt_ts(md["start"]), fmt_ts(md["end"]) if md["end"] else "?", md["stype_in"],
        md["stype_out"], len(md["_mappings"])))
    j = Job(path, {"cap": n})
    while not j.done:
        time.sleep(0.02)
    if j.error:
        sys.exit(j.error)
    res = j.rows(0, n)
    z = _tz(tz)
    cols = [c for c in res["columns"]]
    table = [[fmt_ts(v, z) if j.kinds.get(c) == "ts" and v is not None else
              ("" if v is None else str(v)) for c, v in zip(cols, r)] for r in res["rows"]]
    w = [max([len(c)] + [len(r[i]) for r in table]) for i, c in enumerate(cols)]
    print("  ".join(c.rjust(w[i]) for i, c in enumerate(cols)))
    for r in table:
        print("  ".join(v.rjust(w[i]) for i, v in enumerate(r)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Databento DBN (.dbn/.dbn.zst) viewer")
    ap.add_argument("paths", nargs="*", help="file(s) or directories")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default localhost; use an ssh tunnel for remote boxes)")
    ap.add_argument("--no-token", action="store_true", help="disable the access token")
    ap.add_argument("--open", action="store_true", help="open a browser tab")
    ap.add_argument("--head", type=int, metavar="N", help="print the first N records and exit")
    ap.add_argument("--tz", default="America/New_York", help="timezone for --head output")
    a = ap.parse_args(argv)

    paths = [os.path.abspath(os.path.expanduser(p)) for p in a.paths] or [os.getcwd()]
    files = [p for p in paths if os.path.isfile(p)]
    if a.head:
        for p in files:
            print_head(p, a.head, a.tz)
        return
    roots = [p if os.path.isdir(p) else os.path.dirname(p) for p in paths]
    token = None if a.no_token else secrets.token_urlsafe(12)
    Handler.app = App(roots, token, files[0] if files else None)
    srv = None
    for port in range(a.port, a.port + 20):
        try:
            srv = ThreadingHTTPServer((a.host, port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("no free port near %d" % a.port)
    srv.daemon_threads = True
    url = "http://%s:%d/%s" % ("localhost" if a.host in ("127.0.0.1", "0.0.0.0") else a.host,
                               srv.server_address[1], "?token=" + token if token else "")
    print("dbnview %s  ->  %s" % (__version__, url), flush=True)
    if a.host == "127.0.0.1" and os.environ.get("SSH_CONNECTION"):
        print("remote? on your laptop:  ssh -N -L %d:localhost:%d <this-host>  then open the URL"
              % (srv.server_address[1], srv.server_address[1]), flush=True)
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
