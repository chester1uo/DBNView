#!/usr/bin/env python3
"""Write a small synthetic ES MBO file (DBN v3, zstd) for smoke-testing a packaged build.

    python tools/make_sample_dbn.py sample.mbo.dbn.zst
    DBNVIEW_SELFTEST=shot DBNView.exe sample.mbo.dbn.zst      -> shot_0.png, shot_1.png, ...
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import dbn_writer as W  # noqa: E402

T0 = 1_760_536_800_000_000_000  # 2025-10-15 14:00:00 UTC (10:00 ET)
SEC = 1_000_000_000


def mbo_rows(minutes=10):
    """A book around 5000 with adds, cancels and trades spread over a few minutes, so bars and charts have data."""
    rng = random.Random(7)
    rows, live, oid, t = [], {}, 0, T0

    def emit(action, side, price, size, order_id, flags=128):
        rows.append(dict(ts_event=t, ts_recv=t + 5000, instrument_id=17077, publisher_id=1, action=action,
                         side=side, price=price, size=size, order_id=order_id, flags=flags, sequence=len(rows)))

    emit("R", "N", None, 0, 0, flags=128 | 8 | 32)
    mid = 5000.0
    while t < T0 + minutes * 60 * SEC:
        t += rng.randint(SEC // 20, SEC // 2)
        mid += rng.choice((-0.25, 0, 0.25))
        r = rng.random()
        if r < 0.55 or not live:
            oid += 1
            side = rng.choice("BA")
            price = mid - 0.25 * rng.randint(1, 8) if side == "B" else mid + 0.25 * rng.randint(1, 8)
            live[oid] = (side, price, rng.randint(1, 20))
            emit("A", side, price, live[oid][2], oid)
        elif r < 0.85:
            k = rng.choice(list(live))
            side, price, size = live.pop(k)
            emit("C", side, price, size, k)
        else:
            emit("T", rng.choice("BA"), mid, rng.randint(1, 5), 0)
    return rows


def main(path):
    W.write(path, 3, "GLBX.MDP3", "mbo", T0, T0 + 10 * 60 * SEC, W.records("MBOMsg", 3, mbo_rows()),
            stype_in="continuous", symbols=["ES.v.0"], mappings=[("ES.v.0", [(20251015, 20251016, "17077")])])
    print(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample.mbo.dbn.zst")
