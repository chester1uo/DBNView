"""Technical indicators on bar arrays (pure numpy, NaN until enough history).

All functions take 1-D float arrays (open/high/low/close/volume of the bars) and return arrays of the
same length. INDICATORS describes each one for the front ends: where it is drawn (overlay on the price
chart or its own oscillator pane), its parameters and how to compute its output lines.
"""
import numpy as np


def sma(x, n):
    x = np.asarray(x, dtype=np.float64)
    out = np.full(len(x), np.nan)
    if n <= 0 or len(x) < n:
        return out
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def ema(x, n):
    """Exponential moving average seeded with the first n-bar SMA (alpha = 2 / (n + 1))."""
    x = np.asarray(x, dtype=np.float64)
    out = np.full(len(x), np.nan)
    if n <= 0 or len(x) < n:
        return out
    a = 2.0 / (n + 1)
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def wilder(x, n):
    """Wilder's smoothing (RMA), used by RSI and ATR."""
    x = np.asarray(x, dtype=np.float64)
    out = np.full(len(x), np.nan)
    if n <= 0 or len(x) < n:
        return out
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def rolling_std(x, n):
    x = np.asarray(x, dtype=np.float64)
    out = np.full(len(x), np.nan)
    if len(x) >= n > 0:
        w = np.lib.stride_tricks.sliding_window_view(x, n)
        out[n - 1:] = w.std(axis=1)
    return out


def bollinger(close, n=20, k=2.0):
    mid = sma(close, n)
    sd = rolling_std(close, n)
    return mid, mid + k * sd, mid - k * sd


def vwap(high, low, close, volume):
    """Cumulative VWAP of the typical price (H + L + C) / 3 over the bars shown."""
    tp = (np.asarray(high) + np.asarray(low) + np.asarray(close)) / 3.0
    v = np.nan_to_num(np.asarray(volume, dtype=np.float64))
    cv = np.cumsum(v)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cv > 0, np.cumsum(tp * v) / cv, np.nan)


def rsi(close, n=14):
    d = np.diff(np.asarray(close, dtype=np.float64), prepend=np.nan)
    gain, loss = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ag, al = wilder(gain[1:], n), wilder(loss[1:], n)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = 100 - 100 / (1 + ag / al)
    r = np.where((al == 0) & (ag > 0), 100.0, r)
    return np.insert(r, 0, np.nan)


def macd(close, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    first = np.argmax(np.isfinite(line)) if np.isfinite(line).any() else len(line)
    sig = np.full(len(line), np.nan)
    sig[first:] = ema(line[first:], signal)
    return line, sig, line - sig


def atr(high, low, close, n=14):
    h, low_, c = (np.asarray(a, dtype=np.float64) for a in (high, low, close))
    prev = np.insert(c[:-1], 0, np.nan)
    tr = np.nanmax(np.vstack([h - low_, np.abs(h - prev), np.abs(low_ - prev)]), axis=0)
    return wilder(tr, n)


def stochastic(high, low, close, k=14, d=3):
    """Stochastic oscillator: %K over k bars and its d-bar SMA %D (both 0-100)."""
    h, low_, c = (np.asarray(a, dtype=np.float64) for a in (high, low, close))
    out = np.full(len(c), np.nan)
    if len(c) >= k:
        hh = np.lib.stride_tricks.sliding_window_view(h, k).max(axis=1)
        ll = np.lib.stride_tricks.sliding_window_view(low_, k).min(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[k - 1:] = 100 * (c[k - 1:] - ll) / (hh - ll)
    d_line = np.full(len(c), np.nan)
    if len(c) >= k:
        d_line[k - 1:] = sma(out[k - 1:], d)
    return out, d_line


# ---- registry used by the GUI / TUI ---------------------------------------------------------
# kind: "overlay" (drawn on the price pane) or "pane" (its own oscillator pane)
# lines: (label, color role) per output; levels: horizontal guide lines for oscillators
INDICATORS = {
    "sma": dict(name="SMA", kind="overlay", params={"n": 20}, lines=[("SMA", "accent")]),
    "sma2": dict(name="SMA", kind="overlay", params={"n": 50}, lines=[("SMA", "warn")]),
    "ema": dict(name="EMA", kind="overlay", params={"n": 20}, lines=[("EMA", "violet")]),
    "boll": dict(name="Bollinger Bands", kind="overlay", params={"n": 20, "k": 2.0},
                 lines=[("Middle", "muted"), ("Upper", "teal"), ("Lower", "teal")]),
    "vwap": dict(name="VWAP", kind="overlay", params={}, lines=[("VWAP", "warn")]),
    "rsi": dict(name="RSI", kind="pane", params={"n": 14}, lines=[("RSI", "violet")], levels=[30, 70]),
    "macd": dict(name="MACD", kind="pane", params={"fast": 12, "slow": 26, "signal": 9},
                 lines=[("MACD", "accent"), ("Signal", "warn"), ("Histogram", "hist")], levels=[0]),
    "atr": dict(name="ATR", kind="pane", params={"n": 14}, lines=[("ATR", "teal")]),
    "stoch": dict(name="Stochastic", kind="pane", params={"k": 14, "d": 3},
                  lines=[("%K", "accent"), ("%D", "warn")], levels=[20, 80]),
}


def label(key, params=None):
    spec = INDICATORS[key]
    p = dict(spec["params"], **(params or {}))
    vals = ", ".join("%g" % v for v in p.values())
    return "%s (%s)" % (spec["name"], vals) if vals else spec["name"]


def compute(key, bars, params=None):
    """Output lines of indicator `key` for a bars dict from analysis.market.bars()."""
    p = dict(INDICATORS[key]["params"], **(params or {}))
    h, low_, c, v = bars["h"], bars["l"], bars["c"], bars["v"]
    if key in ("sma", "sma2"):
        return [sma(c, int(p["n"]))]
    if key == "ema":
        return [ema(c, int(p["n"]))]
    if key == "boll":
        return list(bollinger(c, int(p["n"]), float(p["k"])))
    if key == "vwap":
        return [vwap(h, low_, c, v)]
    if key == "rsi":
        return [rsi(c, int(p["n"]))]
    if key == "macd":
        return list(macd(c, int(p["fast"]), int(p["slow"]), int(p["signal"])))
    if key == "atr":
        return [atr(h, low_, c, int(p["n"]))]
    if key == "stoch":
        return list(stochastic(h, low_, c, int(p["k"]), int(p["d"])))
    raise KeyError(key)
