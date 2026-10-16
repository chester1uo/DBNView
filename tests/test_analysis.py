import numpy as np
import pytest

from conftest import T0
from dbnview.analysis import market, options
from dbnview.analysis.book import OrderBook, book_at


def test_book_replay(mbo_file, run_job):
    job = run_job(mbo_file, cap=1000)
    b = book_at(job, job.n - 1, 5)
    assert b["had_clear"] and b["applied"] == 10
    assert b["bids"] == [[4999.75, 6, 2], [4999.5, 6, 1]]   # order 1 cut to 3 + order 2 (3); order 3 modified to 6
    assert b["asks"] == [[5000.25, 7, 1]]                   # order 4 fully cancelled


def test_book_tob_and_modify_unknown():
    ob = OrderBook()
    ob.apply(b"A", b"B", 100_000_000_000, 5, 1, 64)   # top-of-book message replaces the bid side
    ob.apply(b"A", b"B", 101_000_000_000, 7, 2, 64)
    ob.apply(b"M", b"A", 102_000_000_000, 3, 9, 0)    # modify of an unknown order acts as an add
    bids, asks = ob.depth(5)
    assert bids == [(101.0, 7, 1)] and asks == [(102.0, 3, 1)]


def test_bars_from_trades(trades_file, run_job):
    job = run_job(trades_file, cap=10_000)
    b = market.bars(job, 7, interval=60)
    assert b["source"] == "trades" and len(b["t"]) == 10
    assert np.all(b["h"] >= np.maximum(b["o"], b["c"])) and np.all(b["l"] <= np.minimum(b["o"], b["c"]))
    assert b["v"].sum() == pytest.approx(b["buy"].sum() + b["sell"].sum())
    f = market.flow(job, 7, interval=60)
    assert f["n"] == 600 and f["cvd"][-1] == pytest.approx(b["buy"].sum() - b["sell"].sum())


def test_heatmap_from_mbo(mbo_file, run_job):
    job = run_job(mbo_file, cap=1000)
    h = market.heatmap(job, 17077, tbins=20)
    assert h["bid"].shape[0] == 20 and h["tick"] == pytest.approx(0.25)
    assert np.nanmax(h["best_bid"]) == pytest.approx(4999.75)


def test_price_series_downsample(trades_file, run_job):
    job = run_job(trades_file, cap=10_000)
    s = market.price_series(job, 7, maxpts=100)
    assert s["n"] == 600 and s["downsampled"] and len(s["x"]) <= 100


def test_parse_osi():
    assert options.parse_osi("SPY   260116C00690000") == ("SPY", __import__("datetime").date(2026, 1, 16), "C", 690.0)
    assert options.parse_osi("BRKB  261218P00450500")[3] == 450.5
    assert options.parse_osi("ES.v.0") is None


def test_implied_vol_roundtrip():
    F, K, T, D = np.array([100.0] * 3), np.array([90.0, 100.0, 110.0]), np.array([0.5] * 3), 0.98
    for call in (True, False):
        price, _ = options.black76(F, K, T, np.array(0.3), D, np.array([call] * 3))
        iv = options.implied_vol(price, F, K, T, D, np.array([call] * 3))
        assert np.allclose(iv, 0.3, atol=1e-6)


def test_surface_recovers_vol_and_forward(option_file, run_job):
    job = run_job(option_file, cap=10_000)
    assert options.is_option_data(job)
    s = options.surface(job, T0 + 60 * 10**9, "TEST", r=0.04, max_spread=0.5, min_days=1)
    assert set(s["forwards"]) and all(abs(f - 100.0) < 0.05 for f in s["forwards"].values())
    good = np.abs(s["k"]) < 0.15
    assert np.allclose(s["iv"][good], 0.25, atol=0.003)
    g = options.grid(s)
    assert g["Z"].shape[1] == 3
