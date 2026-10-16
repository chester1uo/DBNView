import datetime as dt
import math
import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import dbn_writer as W  # noqa: E402
from dbnview.analysis.options import black76  # noqa: E402
from dbnview.engine import Job  # noqa: E402

T0 = 1_760_536_800_000_000_000  # 2025-10-15 14:00:00 UTC (10:00 ET)
SEC = 1_000_000_000


def wait(job, timeout=30):
    t0 = time.time()
    while not job.done:
        assert time.time() - t0 < timeout, "scan timed out"
        time.sleep(0.01)
    assert job.error is None, job.error
    return job


@pytest.fixture
def run_job():
    return lambda path, **q: wait(Job(str(path), q))


def mbo_rows():
    """A tiny ES book: clear, adds on both sides, a modify, a partial cancel, a trade and a full cancel."""
    rows = []
    t = T0

    def add(action, side, price, size, oid, flags=128):
        nonlocal t
        t += SEC // 10
        rows.append(dict(ts_event=t, ts_recv=t + 5000, instrument_id=17077, publisher_id=1, action=action, side=side,
                         price=price, size=size, order_id=oid, flags=flags, sequence=len(rows)))

    add("R", "N", None, 0, 0, flags=128 | 8 | 32)
    add("A", "B", 4999.75, 5, 1)
    add("A", "B", 4999.75, 3, 2)
    add("A", "B", 4999.50, 10, 3)
    add("A", "A", 5000.00, 4, 4)
    add("A", "A", 5000.25, 7, 5)
    add("M", "B", 4999.50, 6, 3)          # 3: size 10 -> 6
    add("C", "B", 4999.75, 2, 1)          # 1: size 5 -> 3
    add("T", "A", 4999.75, 1, 99)         # trades do not change the book
    add("C", "A", 5000.00, 4, 4)          # 4 removed entirely
    return rows


@pytest.fixture(params=[1, 2, 3])
def mbo_file(tmp_path, request):
    v = request.param
    return W.write(tmp_path / ("es_v%d.mbo.dbn.zst" % v), v, "GLBX.MDP3", "mbo", T0, T0 + 60 * SEC,
                   W.records("MBOMsg", v, mbo_rows()), stype_in="continuous", symbols=["ES.v.0"],
                   mappings=[("ES.v.0", [(20251015, 20251016, "17077")])])


def option_chain(sigma=0.25, F=100.0, r=0.04, expiries=(30, 60, 120)):
    """CBBO-1m rows for a call/put chain priced with Black-76 at a known volatility."""
    rows, mappings, iid = [], [], 1000
    t_eval = T0 + 60 * SEC
    for days in expiries:
        exp = dt.date(2025, 10, 15) + dt.timedelta(days=days)
        T = ((dt.datetime(exp.year, exp.month, exp.day, 20, 0, tzinfo=dt.timezone.utc).timestamp() * 1e9) - t_eval) \
            / (365 * 86400e9)  # 16:00 ET = 20:00 UTC in October (EDT)
        D = math.exp(-r * T)
        for K in (80, 90, 95, 100, 105, 110, 120):
            for cp in "CP":
                price, _ = black76(np.array(F), np.array(float(K)), np.array(T), np.array(sigma), D, cp == "C")
                p = round(float(price), 4)
                sym = "TEST  %s%s%08d" % (exp.strftime("%y%m%d"), cp, K * 1000)
                mappings.append((sym, [(20251015, 20251016, str(iid))]))
                rows.append(dict(ts_event=t_eval, ts_recv=t_eval, instrument_id=iid, publisher_id=30, side="N",
                                 flags=192, bid_px_00=p - 0.0001, ask_px_00=p + 0.0001, bid_sz_00=10, ask_sz_00=10))
                iid += 1
    return rows, mappings


@pytest.fixture
def option_file(tmp_path):
    rows, mappings = option_chain()
    return W.write(tmp_path / "test-opt.cbbo-1m.dbn.zst", 1, "OPRA.PILLAR", "cbbo-1m", T0, T0 + 3600 * SEC,
                   W.records("CBBO1MMsg", 1, rows), stype_in="parent", symbols=["TEST.OPT"], mappings=mappings)


@pytest.fixture
def trades_file(tmp_path):
    rng = np.random.default_rng(1)
    rows, p = [], 50.0
    for i in range(600):
        p += rng.normal(0, 0.05)
        t = T0 + i * SEC
        rows.append(dict(ts_event=t, ts_recv=t, instrument_id=7, publisher_id=2, action="T",
                         side="B" if i % 3 else "A", price=round(p, 2), size=int(rng.integers(1, 100)), flags=128))
    return W.write(tmp_path / "x.trades.dbn.zst", 3, "XNAS.ITCH", "trades", T0, T0 + 600 * SEC,
                   W.records("TradeMsg", 3, rows), symbols=["XYZ"], mappings=[("XYZ", [(20251015, 20251016, "7")])])
