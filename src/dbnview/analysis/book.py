"""Market-by-order (MBO) order book: replay add/cancel/modify/clear messages into price levels.

Used both for "rebuild the book at this row" and for the order-book heatmap.
"""
from ..engine.constants import PRICE_SCALE, UNDEF_PRICE

F_TOB = 64


class OrderBook:
    """L3 orders plus incrementally maintained L2 levels (size and order count per price)."""

    def __init__(self):
        self.orders = {}  # order key -> [side, price, size]
        self.levels = {b"B": {}, b"A": {}}  # side -> {price: [size, count]}
        self.applied = 0
        self.had_clear = False

    def clear(self):
        self.orders.clear()
        self.levels = {b"B": {}, b"A": {}}

    def _add(self, key, side, px, sz):
        if px == UNDEF_PRICE:
            return
        self.orders[key] = [side, px, sz]
        lv = self.levels.setdefault(side, {}).setdefault(px, [0, 0])
        lv[0] += sz
        lv[1] += 1

    def _remove(self, key):
        side, px, sz = self.orders.pop(key)
        lv = self.levels[side][px]
        lv[0] -= sz
        lv[1] -= 1
        if lv[1] <= 0:
            del self.levels[side][px]

    def apply(self, action, side, px, size, order_id, flags):
        """Apply one MBO message (action/side are 1-byte bytes, price is fixed-point int)."""
        self.applied += 1
        if action == b"R":
            self.had_clear = True
            self.clear()
            return
        if flags & F_TOB and action == b"A":  # top-of-book message: replaces that side's top level
            for k in [k for k, o in self.orders.items() if o[0] == side]:
                self._remove(k)
            self._add(("tob", side), side, px, size)
            return
        if action in (b"A", b"M"):  # a modify of an unknown order is treated as an add
            if order_id in self.orders:
                self._remove(order_id)
            self._add(order_id, side, px, size)
        elif action == b"C":
            o = self.orders.get(order_id)
            if o is not None:
                d = min(size, o[2])
                o[2] -= d
                self.levels[o[0]][o[1]][0] -= d
                if o[2] <= 0:
                    self._remove(order_id)
        # T (trade), F (fill) and N (none) do not change the book

    def apply_records(self, recs):
        """Apply a numpy array of MBOMsg records in order."""
        for a, sd, px, sz, oid, fl in zip(recs["action"].tolist(), recs["side"].tolist(), recs["price"].tolist(),
                                          recs["size"].tolist(), recs["order_id"].tolist(), recs["flags"].tolist()):
            self.apply(a, sd, px, sz, oid, fl)

    def depth(self, n):
        """Top n levels per side as [(price, size, order_count)], best first, prices in real units."""
        bids = sorted(((p, v) for p, v in self.levels.get(b"B", {}).items() if v[0] > 0), key=lambda kv: -kv[0])[:n]
        asks = sorted(((p, v) for p, v in self.levels.get(b"A", {}).items() if v[0] > 0), key=lambda kv: kv[0])[:n]
        fmt = lambda lv: [(p / PRICE_SCALE, v[0], v[1]) for p, v in lv]
        return fmt(bids), fmt(asks)


def book_at(job, row, depth=20):
    """Rebuild the book of the instrument at loaded row `row`, using every earlier loaded MBO row."""
    s, i = job._locate(row)
    _, recs, _ = job.segments[s]
    iid = int(recs["instrument_id"][i])
    book = OrderBook()
    for rt, part, _ in job.iter_instrument(iid, upto=row):
        if rt.cls == "MBOMsg":
            book.apply_records(part)
    bids, asks = book.depth(depth)
    return {"instrument_id": iid, "symbol": job.fi.symmap.lookup(iid), "applied": book.applied,
            "orders": len(book.orders), "bids": [list(b) for b in bids], "asks": [list(a) for a in asks],
            "safe": job.filter.book_safe, "had_clear": book.had_clear}
