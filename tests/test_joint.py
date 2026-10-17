import numpy as np

import dbn_writer as W
from conftest import SEC, T0
from dbnview.analysis import joint


def test_option_series_recovers_vol_and_spot(option_file):
    o = joint.option_series(str(option_file), None, 60)
    assert o["root"] == "TEST" and len(o["t"]) >= 1
    i = int(np.argmax(np.isfinite(o["front_iv"])))
    assert abs(o["front_iv"][i] - 0.25) < 0.01 and abs(o["iv30"][i] - 0.25) < 0.01
    assert 99 < o["spot"][i] < 100.1            # forward 100 discounted at 4%
    assert abs(o["skew"][i]) < 0.01             # flat-vol chain has no skew
    assert 0 < o["move"][i] < 0.1


def test_underlying_series_and_root(tmp_path):
    rows, p = [], 100.0
    rng = np.random.default_rng(2)
    for i in range(3600):
        p *= np.exp(rng.normal(0, 0.0005))
        t = T0 + i * SEC
        rows.append(dict(ts_event=t, ts_recv=t, instrument_id=5, publisher_id=2, action="T", side="B",
                         price=round(p, 4), size=10, flags=128))
    path = W.write(tmp_path / "test.trades.dbn.zst", 3, "XNAS.ITCH", "trades", T0, T0 + 3600 * SEC,
                   W.records("TradeMsg", 3, rows), symbols=["BRK.B"], mappings=[("BRK.B", [(20251015, 20251016, "5")])])
    s = joint.underlying_series(str(path), 60)
    assert s["symbol"] == "BRK.B" and joint.symbol_root(s["symbol"]) == "BRKB"
    assert len(s["bars"]["t"]) == 60
    rv = s["rv"][np.isfinite(s["rv"])]
    # 0.05% per second -> annualized over 252 * 6.5 h
    expect = 0.0005 * np.sqrt(252 * 6.5 * 3600)
    assert abs(np.median(rv) - expect) / expect < 0.25
