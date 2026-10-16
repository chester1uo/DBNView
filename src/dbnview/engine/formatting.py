"""Converting decoded record columns into JSON/GUI-friendly Python values."""
import numpy as np

from .constants import PRICE_SCALE, UNDEF_PRICE, UNDEF_TS


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

