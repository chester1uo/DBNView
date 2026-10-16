"""Scan filters: symbols, instrument ids, time window, action/side and a safe `where` expression."""
import ast

import numpy as np

from .constants import PRICE_SCALE, UNDEF_PRICE
from .timeutil import parse_time


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

