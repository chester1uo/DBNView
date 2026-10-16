import numpy as np
import pytest

from dbnview.analysis import indicators as I


def test_sma_ema_basic():
    x = np.arange(1, 11, dtype=float)
    s = I.sma(x, 3)
    assert np.isnan(s[:2]).all() and np.allclose(s[2:], np.arange(2, 10))
    assert np.allclose(I.ema(np.full(30, 5.0), 10)[9:], 5.0)
    e = I.ema(x, 3)
    assert e[2] == pytest.approx(2.0) and e[3] == pytest.approx(0.5 * 4 + 0.5 * 2.0)


def test_bollinger_and_vwap():
    x = np.array([1, 2, 3, 4, 5], dtype=float)
    mid, up, lo = I.bollinger(x, 5, 2)
    assert mid[-1] == pytest.approx(3) and up[-1] - mid[-1] == pytest.approx(2 * np.std(x))
    assert I.vwap(x, x, x, np.ones(5))[-1] == pytest.approx(3)


def test_rsi_extremes():
    assert I.rsi(np.arange(30, dtype=float), 14)[-1] == pytest.approx(100)
    assert I.rsi(np.arange(30, 0, -1, dtype=float), 14)[-1] == pytest.approx(0)


def test_macd_constant_is_zero():
    line, sig, hist = I.macd(np.full(60, 7.0))
    assert np.allclose(line[25:], 0) and np.allclose(sig[33:], 0) and np.allclose(hist[33:], 0)


def test_atr_and_stochastic():
    n = 40
    c = np.linspace(10, 20, n)
    h, l = c + 0.5, c - 0.5
    a = I.atr(h, l, c, 14)
    assert np.isnan(a[:13]).all() and np.all(a[14:] > 0.99)
    k, d = I.stochastic(h, l, c, 14, 3)
    assert np.nanmin(k) >= 0 and np.nanmax(k) <= 100 and np.isfinite(d[-1])


@pytest.mark.parametrize("key", list(I.INDICATORS))
def test_registry_compute(key):
    rng = np.random.default_rng(0)
    c = 100 + np.cumsum(rng.normal(0, 1, 120))
    bars = {"o": c, "h": c + 1, "l": c - 1, "c": c, "v": rng.integers(1, 100, 120).astype(float)}
    out = I.compute(key, bars)
    assert len(out) == len(I.INDICATORS[key]["lines"])
    assert all(len(o) == 120 and np.isfinite(o[-1]) for o in out)
