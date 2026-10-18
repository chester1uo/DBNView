[简体中文](README.zh-CN.md)

# DBNView

DBNView is a viewer for [Databento](https://databento.com) DBN market-data files (`.dbn` / `.dbn.zst`, DBN v1–v3).
It decodes zstd-compressed streams directly, so there is no conversion step and you don't need the `databento` SDK.
The decoding engine depends only on `numpy` and `zstandard`.

The same engine drives three front ends:

| Front end | Command | Good for |
|---|---|---|
| Desktop app (PySide6) | `dbnview` | interactive work on a laptop or workstation |
| Terminal UI (Textual) | `dbnview-tui` | a plain ssh session with no display |
| Browser UI | `dbnview-web` | servers without Qt, reached through an ssh tunnel |

It runs on macOS, Windows and Linux with Python 3.9 or newer.

## Quick start

Prebuilt packages (macOS DMG, Windows installer, Linux tarball) are on the
[Releases](https://github.com/chester1uo/DBNView/releases) page.

Install from a clone:

```bash
git clone https://github.com/chester1uo/DBNView.git
cd DBNView
python -m venv .venv
.venv/bin/pip install -e ".[gui,tui]"      # Windows: .venv\Scripts\pip install -e ".[gui,tui]"
```

The extras are `gui` (desktop app), `tui` (terminal UI), `all` (both) and `dev` (everything plus pytest, pyflakes
and PyInstaller). A plain `pip install -e .` installs only the engine and the browser UI.

**Desktop app**: open a local file, or stream one over ssh:

```bash
.venv/bin/dbnview ~/data/glbx-mdp3-20260102.mbo.dbn.zst
.venv/bin/dbnview ssh://myserver/data/databento/opra-20260102.cbbo-1m.dbn.zst
```

**Terminal UI**: open a file, a directory, or an ssh directory:

```bash
.venv/bin/dbnview-tui ~/data --tz America/New_York --lang en
```

Keys: `o` open · `s` scan · `x` stop · `/` filter · `f` sidebar · `enter` detail · `b` MBO book · `c` cycle chart ·
`i` cycle indicator · `t` time zone · `1`–`6` tabs · `e` export CSV · `q` quit.

**Browser UI**: run it on the machine that holds the data, then tunnel the port to your laptop:

```bash
dbnview-web /data/databento                  # on the server; prints http://localhost:8765/?token=...
ssh -N -L 8765:localhost:8765 myserver       # on your laptop, then open the printed URL
```

If the server has no package install, build a single-file version with `python tools/build_web_pyz.py`.
Copy `dist/dbnview-web.pyz` to the server and run `python dbnview-web.pyz /data`.

## Features

- **Table**: scrolls through millions of rows. Prices are scaled to real units, timestamps can be shown in several
  time zones, flags and enum codes are decoded, and you can jump to a time or export to CSV.
- **Filters**: symbol (substring, or exact when you pick a suggestion), instrument_id, time window, action/side,
  and a safe `where` expression such as `size >= 10 and side == 'B'`.
- **Detail panel**: every field of a row, the bid/ask ladder, an MBO order-book rebuild at that row, and the raw
  bytes in hex with their byte layout.
- **Charts**:
  - candles, either native or built from trades or quotes, with buy/sell volume, CVD, volume profile and VWAP
  - technical indicators on the candles: SMA, EMA, Bollinger Bands, VWAP, RSI, MACD, ATR and Stochastic
  - quotes with a spread band and top-of-book imbalance
  - order-flow bubbles
  - an order-book heatmap from MBP-10, or from a replayed MBO book
  - price lines
- **Statistics and format guide**: record-type, action and side distributions, and the top instruments. The format
  guide covers what the schema means, the record and metadata-header byte layouts, enum meanings and common pitfalls.
- **Option walls**: open interest (from OPRA statistics), volume and dealer gamma exposure by strike, with the
  call wall, put wall, total GEX and the gamma flip level (desktop tab and terminal tab 7).
- **Stock + options analysis** (Tools → Stock + Options Analysis…, Ctrl/⌘+J): a separate window that lines up an
  underlying file and an option file on one time grid — price with the parity-implied spot and the front straddle's
  expected move, front and ~30-day ATM IV against realized volatility, skew, call/put volume and the put/call ratio.
- **IV surface** for OPRA options: a snapshot at a chosen time, put-call-parity forwards and Black-76 implied
  volatility. Results show as a 3D surface, a heatmap, smile and term-structure slices, and can be exported to CSV.
- **Remote files over ssh** (`ssh host cat`, using your `~/.ssh/config` keys), drag & drop, trackpad pinch zoom.
- **Seven UI languages**: Traditional Chinese, Simplified Chinese, English, Japanese, German, Korean and Spanish.

**Correctness**: the decoder has been checked field by field against the official Databento decoder on CME MBO
(v3), OPRA cbbo-1m (v1) and OPRA cmbp-1 (v1).

**Speed**: decoding runs at about 5–6 million records per second.

## Documentation

- [User guide](docs/en/user-guide.md): installation, front ends, filters, charts, the IV surface, shortcuts and
  troubleshooting
- [Architecture](docs/en/architecture.md): package layout, data flow, threading and the chart and options pipelines
- [Development](docs/en/development.md): setup, tests, translations, new record types, packaging and releases

## License

MIT
