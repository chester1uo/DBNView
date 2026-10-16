"""Record types: numpy dtypes per (DBN version, rtype, record length) and byte layouts."""
import numpy as np

from .constants import HEADER_FIELDS, NULL_MAX_CLASSES, RTYPES, SPEC


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


_RT_CACHE = {}


def record_type(version, rtype, length, ts_out, schema=None):
    key = (version, rtype, length, ts_out, schema == "tbbo" and rtype == 0x01)
    rt = _RT_CACHE.get(key)
    if rt is None:
        rt = _RT_CACHE[key] = RecordType(version, rtype, length, ts_out)
        if key[-1]:  # DBN v1-v3 store TBBO records under the MBP-1 rtype
            rt.name = "tbbo"
    return rt


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

