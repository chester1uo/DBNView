"""Write small synthetic DBN files (v1-v3, plain or zstd) so tests need no market data."""
import struct

import numpy as np
import zstandard

from dbnview.engine.constants import PRICE_SCALE, RTYPES, SCHEMAS, SPEC, STYPES

CLASS_RTYPE = {"MBOMsg": 0xA0, "TradeMsg": 0x00, "MBP1Msg": 0x01, "MBP10Msg": 0x0A, "CBBO1MMsg": 0xC1,
               "CMBP1Msg": 0xB1, "OHLCVMsg": 0x21, "StatMsg": 0x18, "InstrumentDefMsg": 0x13}


def dtype_for(cls, version):
    return np.dtype([tuple(f) for f in SPEC["versions"][str(version)][cls]["f"]])


def records(cls, version, rows):
    """rows: list of dicts (prices in real units for price fields, everything else raw)."""
    dt = dtype_for(cls, version)
    px = set(SPEC["versions"][str(version)][cls]["px"])
    arr = np.zeros(len(rows), dtype=dt)
    rtype = CLASS_RTYPE[cls]
    assert RTYPES[rtype][0] == cls or cls == "OHLCVMsg"
    arr["length"] = dt.itemsize // 4
    arr["rtype"] = rtype
    for f in px:  # default every price to "undefined"
        arr[f] = np.iinfo(np.int64).max
    for i, r in enumerate(rows):
        for k, v in r.items():
            if v is None:
                continue
            if k in px:
                v = int(round(v * PRICE_SCALE))
            elif isinstance(v, str):
                v = v.encode()
            arr[k][i] = v
    return arr.tobytes()


def metadata(version, dataset, schema, start, end, stype_in="raw_symbol", stype_out="instrument_id",
             symbols=(), mappings=()):
    """mappings: [(raw_symbol, [(start_yyyymmdd, end_yyyymmdd, symbol_string), ...]), ...]"""
    cl = 22 if version == 1 else 71
    cstr = lambda s: s.encode().ljust(cl, b"\0")[:cl]
    b = dataset.encode().ljust(16, b"\0")
    b += struct.pack("<HQQQ", SCHEMAS.index(schema) if schema else 0xFFFF, start, end, 0)
    if version == 1:
        b += struct.pack("<Q", 0)
    b += bytes([STYPES.index(stype_in), STYPES.index(stype_out), 0])
    b += struct.pack("<H", cl) + b"\0" * 53 if version >= 2 else b"\0" * 47
    b += struct.pack("<I", 0)
    for lst in (list(symbols), [], []):
        b += struct.pack("<I", len(lst)) + b"".join(cstr(s) for s in lst)
    b += struct.pack("<I", len(mappings))
    for raw, ivs in mappings:
        b += cstr(raw) + struct.pack("<I", len(ivs))
        for sd, ed, sym in ivs:
            b += struct.pack("<II", sd, ed) + cstr(sym)
    if version >= 2:
        b += b"\0" * ((-(8 + len(b))) % 8)
    return b"DBN" + bytes([version]) + struct.pack("<I", len(b)) + b


def write(path, version, dataset, schema, start, end, body, compress=True, **meta):
    raw = metadata(version, dataset, schema, start, end, **meta) + body
    with open(path, "wb") as f:
        f.write(zstandard.ZstdCompressor().compress(raw) if compress else raw)
    return path
