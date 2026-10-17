import datetime as dt

import numpy as np

import dbn_writer as W
from conftest import SEC, T0, option_chain
from dbnview.analysis import options, walls


def test_walls_from_open_interest(option_file, run_job, tmp_path):
    rows, mappings = option_chain()
    # open interest: calls pile up at 110, puts at 90
    stats = []
    for i, (sym, _) in enumerate(mappings):
        root, d, cp, K = options.parse_osi(sym)
        oi = 5000 if (cp == "C" and K == 110) or (cp == "P" and K == 90) else 100
        stats.append(dict(ts_event=T0, ts_recv=T0, ts_ref=T0, instrument_id=1000 + i, publisher_id=30, stat_type=9,
                          quantity=oi, update_action=1))
    stat_path = W.write(tmp_path / "test-opt.statistics.dbn.zst", 1, "OPRA.PILLAR", "statistics", T0, T0 + 3600 * SEC,
                        W.records("StatMsg", 1, stats), stype_in="parent", symbols=["TEST.OPT"], mappings=mappings)
    oi = walls.load_open_interest(str(stat_path))
    assert len(oi) == len(mappings) and sum(oi.values()) == 2 * 5000 * 3 + 100 * (len(mappings) - 6)
    assert walls.find_statistics_file(str(option_file)) == str(stat_path)

    job = run_job(option_file, cap=10_000)
    s = options.surface(job, T0 + 60 * SEC, "TEST", min_days=0)
    w = walls.walls("TEST", surface=s, oi=oi)
    assert abs(w["spot"] - 100) < 1
    assert w["call_wall"] == 110 and w["put_wall"] == 90
    assert w["has_gex"] and w["zero_gamma"] is not None and 90 < w["zero_gamma"] < 110
    i110, i90 = list(w["strike"]).index(110), list(w["strike"]).index(90)
    assert w["call_gex"][i110] > 0 and w["put_gex"][i90] < 0
    near = walls.walls("TEST", surface=s, oi=oi, max_days=45, asof=dt.date(2025, 10, 15))
    assert near["call_oi"].sum() < w["call_oi"].sum()   # only the 30-day expiry is kept


def test_volume_walls(trades_file, run_job):
    # a non-option file has no OSI symbols, so there is no option volume
    job = run_job(trades_file, cap=10_000)
    assert walls.volume_by_contract(job) == {}


def test_gamma_matches_finite_difference():
    F, K, T, iv = 100.0, 105.0, 0.25, 0.3
    g = float(walls._gamma(np.array(F), np.array(K), np.array(T), np.array(iv)))
    h = 0.01
    p = lambda f: float(options.black76(np.array(f), np.array(K), np.array(T), np.array(iv), 1.0, True)[0])
    assert abs(g - (p(F + h) - 2 * p(F) + p(F - h)) / h ** 2) < 1e-4
