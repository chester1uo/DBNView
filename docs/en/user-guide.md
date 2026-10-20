[简体中文](../zh-CN/user-guide.md) · [README](../../README.md)

# DBNView user guide

DBNView opens Databento DBN files (`.dbn` and zstd-compressed `.dbn.zst`, DBN versions 1–3) without converting
them. This guide covers installation, the three front ends, filters, charts, the IV surface, keyboard shortcuts and
troubleshooting.

## 1. Installation

### 1.1 From a clone

You need Python 3.9 or newer.

```bash
git clone https://github.com/chester1uo/DBNView.git
cd DBNView
python -m venv .venv
.venv/bin/pip install -e ".[gui,tui]"      # Windows: .venv\Scripts\pip install -e ".[gui,tui]"
```

| Extra | Adds | Needed for |
|---|---|---|
| (none) | `numpy`, `zstandard` (and `tzdata` on Windows) | engine and browser UI (`dbnview-web`) |
| `gui` | `PySide6`, `pyqtgraph`, `PyOpenGL` | desktop app (`dbnview`) |
| `tui` | `textual`, `plotext` | terminal UI (`dbnview-tui`) |
| `all` | `gui` + `tui` | both interactive front ends |
| `dev` | `all` + `pytest`, `pyflakes`, `pyinstaller` | development and packaging |

Installing the package creates three commands. Each one also has a module form:

| Command | Module form | Front end |
|---|---|---|
| `dbnview` | `python -m dbnview` | desktop app |
| `dbnview-tui` | `python -m dbnview.tui` | terminal UI |
| `dbnview-web` | `python -m dbnview.web` | browser UI |

### 1.2 Platform notes

- **macOS**: works out of the box. Trackpad pinch zoom works in charts and in the 3D IV surface.
- **Windows**:
  - Time zones come from the `tzdata` package, which is installed automatically.
  - Remote files use the built-in OpenSSH client (`ssh.exe`). It has no connection sharing, so each directory listing
    or file open opens a new connection.
- **Linux**: the desktop app needs the usual Qt xcb libraries. On Debian/Ubuntu, for example:

  ```bash
  sudo apt install libxkbcommon-x11-0 libxcb-cursor0 libegl1
  ```

  The terminal UI and the browser UI need none of these.

### 1.3 Packaged desktop app

A standalone desktop app can be built with PyInstaller (see [development.md](development.md#8-packaging)):

- **macOS**: `dist/DBNView.app`. Drag it to Applications. Finder offers it under **Open With** for `.dbn` and
  `.zst` files.
- **Windows and Linux**: a `dist/DBNView/` folder that contains `DBNView.exe` or `DBNView`.

The packaged app contains only the desktop front end.

## 2. Opening files

- **Desktop app**:
  - Pass a path on the command line: `dbnview file.dbn.zst`.
  - Use **File → Open File…** (⌘O / Ctrl+O), drag a file onto the window, or pick one from **File → Open Recent**.
- **Terminal UI**: `dbnview-tui file.dbn.zst`.
  - If you pass a directory, or nothing (the current directory), a file picker opens. Press `o` to open it again later.
- **Browser UI**: `dbnview-web DIR_OR_FILE …`. The page has a file browser rooted at the given directories.

After a file opens, DBNView reads its metadata header (dataset, schema, time range, symbology) and starts a scan
right away.

### 2.1 Remote files over ssh

The desktop app and the terminal UI can read files on another machine without installing anything there.

- **Desktop**: use **File → Open Remote File (ssh)…** (⇧⌘O / Ctrl+Shift+O).
  1. Pick an SSH profile. The list includes DBNView profiles and `Host` entries from `~/.ssh/config`; wildcard
     patterns are skipped.
  2. Click **+** to add a profile, or **Edit** a selected `~/.ssh/config` host to import it (address, user, port and
     proxy are read with `ssh -G`). A profile has:
     - **Login**: name, address, port, username.
     - **Authentication**: a key (a private-key file, or blank for the OpenSSH defaults and `ssh-agent`) or a password.
     - **Proxy**: none; a jump host (`ProxyJump`: a `~/.ssh/config` alias or `user@host:port`, several hops joined by
       commas, e.g. `tokyo-ec2,hluo@localhost:2222`); a SOCKS5 or HTTP CONNECT proxy (`host:port`, run through `nc`);
       or a custom `ProxyCommand`.
     - **Logging and security**: an OpenSSH log file with a level (`ERROR` … `DEBUG3`), and whether to trust a new
       host key on first connection (`StrictHostKeyChecking=accept-new`; a changed key is still rejected).
     - **Test Connection** connects once and shows the remote `uname` or the ssh error.
  3. Type or browse to a directory. Double-click a folder to enter it, or a file to open it.
- **Command line**: use a URL of the form `ssh://HOST/ABSOLUTE/PATH`, where HOST is a `~/.ssh/config` alias or the
  name of a DBNView profile:

  ```bash
  dbnview ssh://myserver/data/databento/opra-20260102.cbbo-1m.dbn.zst
  dbnview-tui ssh://myserver/data/databento
  ```

`HOST` is anything `ssh` accepts, such as an alias from `~/.ssh/config` or `user@hostname`. The path must be
absolute because `~` is not expanded.

How it works:

- Data is streamed with `ssh HOST cat PATH` and decoded locally.
- ssh runs with `BatchMode=yes` and `ConnectTimeout=10`, so it uses your existing keys and agent and never prompts
  for a password.
- DBNView profiles are stored in `~/.config/dbnview/ssh_profiles.json` (`%APPDATA%\dbnview` on Windows). Passwords
  stay in process memory only, must be entered again after restarting, and are never written to the profile or SSH log.
- Key authentication can name a private-key file; when blank, OpenSSH defaults and `ssh-agent` are used. Password
  authentication uses OpenSSH `SSH_ASKPASS`. SOCKS5 / HTTP proxies need `nc` with `-X` (built into macOS; the
  OpenBSD netcat on Linux; install one separately on Windows).
- On macOS and Linux, connections are shared for 120 seconds (`ControlMaster=auto`, control sockets at
  `~/.ssh/dbnview-*`), so browsing and then opening a file reuses one connection.
- Directory listing and file size use GNU `find -printf` and `stat -c`, so the remote machine should be a Linux host.
- zstd streams can't be seeked, so a scan always transfers the file from the beginning, even with a time filter.
  For very large remote files, running `dbnview-web` on the server is usually faster (see
  [section 9](#9-browser-ui)).

## 3. Scanning

A scan reads the file from the start, applies the filters and keeps matching rows in memory.

- **Row limit**: 1,000,000 by default (the **Max rows** field). When it is reached, the scan stops and the status
  shows that the file was not read to the end.
- **Scan entire file** (desktop): keeps reading past the row limit, so the statistics (counts, distributions, top
  instruments, time range) cover the whole file. The table still holds at most **Max rows** rows.
- **Scan / Stop**: ⌘R / ⌘. (Ctrl+R / Ctrl+. on Windows and Linux) in the desktop app, `s` / `x` in the terminal UI.
  Pressing Enter in any filter field also starts a new scan.
- **Speed**: about 5–6 million records per second, depending on the record size and the disk or network.

Charts, the book rebuild and the IV snapshot all work on the rows the scan loaded. Each one notes when it only covers
part of the file. The IV surface can also stream the file up to the time you choose (see [section 7](#7-iv-surface)).

## 4. Filters

All filters are combined with AND. A new scan applies them.

| Filter | Meaning |
|---|---|
| symbol | Matches the symbols in the file's symbology mappings, case-insensitively. Typing text and pressing Enter adds a **substring** pattern. Picking a suggestion adds an **exact** pattern. Several patterns are combined with OR. To remove a pattern, double-click it or press Delete. In the terminal UI, separate patterns with commas and end a pattern with `$` for an exact match (`ESZ6$`). |
| instrument_id | Comma- or space-separated ids. They are combined with the symbol matches. |
| From / To | Time window. From is inclusive and To is exclusive (see the time formats below). |
| Time field | `auto` (`ts_recv` when the record has it, otherwise `ts_event`), `ts_recv` or `ts_event`. Desktop and browser UI only. |
| action / side | Checkboxes, shown only when the record type has those fields. Desktop and browser UI only. In the terminal UI, use `where`. |
| where | A safe expression evaluated on each record (see below). |

**Time formats.** Times are read in the selected display time zone.

| Input | Meaning |
|---|---|
| `09:30`, `09:30:15.250` | a time on the file's start date |
| `2026-01-02 09:30:00` | a date and time |
| `2026-01-02T14:30:00Z` | UTC (the trailing `Z`) |
| `1767364200000000000` | raw nanoseconds since the epoch (any integer longer than 12 digits) |

Fractions are accepted down to nanoseconds.

### 4.1 `where` expressions

A `where` expression is parsed with Python's `ast` module and evaluated on whole numpy columns, never with `eval`.
Only the syntax listed here is allowed.

- **Names**: record field names such as `price`, `size`, `side`, `bid_px_00` or `ask_sz_00`.
  - Price fields are in real units, as floats, and an undefined price is `NaN`.
  - Character fields compare with one-character strings: `side == 'B'`.
- **Operators**:
  - `and`, `or`, `not`
  - `+ - * / %`
  - `&` and `|` (bitwise)
  - `== != < <= > >=`, which can be chained: `1 <= size < 10`
  - `in` / `not in` with a tuple or list
- **Functions**: `abs()`, `isnan()`.
- **Missing fields**: if a record type doesn't have a field the expression uses, no rows of that type match.

Examples:

```text
size >= 10 and side == 'B'
ask_px_00 - bid_px_00 <= 0.05
action in ('T', 'F')
not isnan(price) and price > 450
(flags & 128) != 0
```

### 4.2 Filters and the MBO book

Rebuilding an MBO order book needs every earlier message of the instrument. These filters can drop such messages:

- a **From** time
- action / side
- `where`
- record-type filters

When any of them is active, the book rebuild shows a warning. Filtering by symbol, by instrument_id, or by a
**To** time alone is safe.

## 5. Desktop app

The window has three areas:

- **Left panel**: file information (path, size, dataset, schema, DBN version, time range, stype, symbols,
  mappings), the filters, and scan progress.
- **Tabs**: Table, Chart, Statistics, Format Guide, IV Surface.
- **Detail panel** on the right.

Toggle the left panel with ⌘L and the detail panel with ⌘I.

The toolbar controls the **time zone** (ET, CT, UTC, London, HKT, JST) and the **time format**:

- **Date+Time**
- **Time Only**
- **Raw ns**

Both settings apply everywhere and are remembered.

### 5.1 Table

- Rows are fetched only as you scroll, so millions of rows stay responsive.
- Prices are divided by 1e9, and undefined values are shown as `—`.
- side and action are colored, and flags are decoded.
- Codes from status, statistics and definition records are shown with their official meanings.
- **Column help**: hover over a column header to see what the field means.
- **Columns**:
  - Right-click a column header, or use the **Columns** menu, to show or hide columns.
  - Choose **Show All**, or the compact preset that hides rtype, publisher, sequence and so on.
- **Jump to time**: type a time (for example `15:45`) in the box above the table and press Enter.
- **Export CSV**: ⌘E exports all loaded rows. Timestamps are written in the selected time zone.

### 5.2 Detail panel

Click a row to see the following:

- **Fields**: every field with its decoded value and a short description.
- **Bid/ask ladder**: for MBP-1/MBP-10, BBO, CBBO and CMBP records, with size and count (or publisher) per level.
- **Rebuild Order Book Here (MBO)**: replays all earlier loaded MBO rows of the same instrument and shows the book
  as of this row: price levels, sizes and order counts.
  - It warns when the filters may have dropped earlier messages (see [4.2](#42-filters-and-the-mbo-book)).
  - It also warns when the file has no clear (`R`) or snapshot at the start, because orders resting before the file
    began are then missing.
- **Raw bytes**: the record's bytes in hex, colored by field, plus a byte-layout table (offset, field, type, raw
  value). Records are little-endian.

### 5.3 Charts

Choose an instrument from the list, or type an instrument_id. Then choose the following:

- **Chart type**: Candles, Quotes, Order Flow, Order Book Heatmap or Price Line.
- **Interval**: Auto, or 1s through 1W.
- **Source**: Auto, Trades or Quote mid.

Chart types the instrument's records can't support are disabled. The default chart depends on the record type:

- OHLCV and trades open as candles.
- MBO and MBP-10 open as a heatmap.
- Quote schemas open as quotes.

| Chart | What it shows |
|---|---|
| **Candles** | OHLCV records are drawn as they are, or regrouped into a coarser interval. Trade-bearing records (trades, tbbo, mbp, cmbp, mbo trades) become candles with total volume and buy/sell volume by aggressor side. Quote-only data becomes candles from the mid price; volume is then the number of quotes. Extra panels show CVD (cumulative volume delta), the volume profile and VWAP. |
| **Quotes** | Bid and ask step lines with a shaded spread band and the mid. Sub-panels show the spread and the top-of-book imbalance `(bid size − ask size) / (bid size + ask size)`. Trades are overlaid as bubbles. |
| **Order Flow** | Trade bubbles: size is volume, green is an aggressive buy and red an aggressive sell. Also buy/sell volume per bar, CVD and the volume profile. |
| **Order Book Heatmap** | Resting size per price over time, on a log color scale: green for bids, red for asks. MBP-10 levels are read directly; MBO is replayed into a book and sampled per time bin. Best bid/ask lines and trades are drawn on top. |
| **Price Line** | Every price field of the record over time, plus records per minute. Long series are min/max-downsampled. |

**Technical indicators** (Candles only): the **Indicators** button above the chart opens a menu.

| Kind | Indicators (default parameters) |
|---|---|
| Overlays on the price chart | SMA (20), a second SMA (50), EMA (20), Bollinger Bands (20, 2), VWAP (cumulative, typical price) |
| Separate panes | RSI (14), MACD (12, 26, 9), ATR (14), Stochastic (14, 3) |

- The two SMAs are on by default.
- **Indicator Parameters…** changes the periods, and **Clear All** removes every indicator.
- The selection and the parameters are remembered.
- Indicators are computed on the bars shown, so they start after enough bars (for example 20 for SMA 20).

Chart controls:

- Scroll or pinch to zoom, and drag to pan.
- A crosshair readout above the plot shows the values under the cursor.

### 5.4 Statistics

The Statistics tab shows the following:

- matched and read record counts, the number of instruments and the time range
- distributions by record type, action and side
- the top 200 instruments by row count

Each top-instrument row has two links. **Filter** rescans with only that instrument, and **Chart** opens it in the
Chart tab. While a scan is running, or when it stopped at the row limit, the numbers cover only the part already read.

### 5.5 Format guide

The Format Guide tab explains the open file:

- **What the schema means**: what one row represents.
- **The layers**: the zstd wrapper, the metadata header and the fixed-size records.
- **The metadata header**: a byte map with this file's actual values and offsets.
- **The record layout**: offset, size, type and meaning of every field, including padding.
- **Enum meanings**: action, side, flags bits, `stat_type` and the undefined-value sentinels.
- **Common pitfalls**: for example, prices are integers ÷ 1e9, `ts_recv` versus `ts_event`, MBO `T`/`F` versus
  `C`/`M`, and OPRA instrument ids changing from day to day.

### 5.6 MBO order book replay

**Tools → MBO Order Book Replay…** (⇧⌘R, MBO files only) opens a window that replays the order book of the day.
It starts at the selected table row (its instrument and receive time), or at 09:30 New York for Nasdaq days.

- **Ladder** (left): the top *Depth* levels per side with size bars and order counts; levels that just changed flash.
  **Show queues (L3)** splits each bar into the resting orders in queue order (first in queue next to the price);
  hover a segment for its queue position, order ID and size.
- **Chart** (top right): bid and ask as step lines and trades as dots (size by volume, colour by aggressor side) in a
  moving window around the current time; click it to jump there.
- **Event tape** (bottom right): the 40 events before the current position, newest first.
- **Playback**: ▶ / Space plays at the chosen speed (0.1× to 1800×); ←/→ step one second, ⇧←/⇧→ one event; the slider
  and the time box (`10:30`, `10:30:15.250` or a full date-time) jump anywhere.

Two engines:

- **LOB-WASR** ([github.com/chester1uo/LOB-WASR](https://github.com/chester1uo/LOB-WASR)), when the `wasr` package is
  installed (`pip install "dbnview[replay]"`, which builds it from source and needs a C++17 compiler, CMake and libzstd).
  The first replay of a file indexes it into a `.wasr` file in the cache (`~/Library/Caches/DBNView/wasr` on macOS,
  `%LOCALAPPDATA%\DBNView\cache\wasr` on Windows, `~/.cache/dbnview/wasr` on Linux; `DBNVIEW_CACHE_DIR` overrides) —
  about 5 s for a 10-million-event day — and later opens are instant. Seeking anywhere takes a few milliseconds, playback
  frames well under one, and queues are exact (including the CME modify rules). Remote files are downloaded into the
  cache for indexing. LOB-WASR needs one instrument per file.
- **Loaded rows** otherwise (or for files with several instruments): the MBO rows already loaded by the scan, for one
  instrument, with checkpoints in memory. It covers only the loaded rows (*Max Rows*), and queue order is approximate
  (a modify moves the order to the back).

## 6. Charts in the terminal UI

The terminal UI draws charts with plotext in the Chart tab (key `3`). Press `c` to cycle between three modes:

- **candles**: the interval is picked to fit the terminal width.
- **quotes**: bid and ask lines.
- **flow**: trade dots, green for buy and red for sell, with VWAP in the title.

Press `i` to switch to candles and cycle through the indicators: none → SMA → EMA → Bollinger → VWAP → RSI → MACD →
Stochastic → ATR. Overlays are drawn on the candles, and oscillators in a second plot below them.

The chart shows the instrument of the selected table row. If no row is selected, it shows the most active instrument.

## 7. IV surface

The IV Surface tab works on option data with OSI-style symbols, which is the OPRA `raw_symbol` format:

```text
SPY   260116C00690000   root padded to 6 chars + YYMMDD + C/P + strike × 1000 (8 digits)
```

Suitable files include OPRA cbbo-1s/1m, cmbp-1, tcbbo, bbo, trades and ohlcv. After a scan, DBNView checks
whether at least half of the instruments have OSI symbols. If they do, it fills the **Underlying** list, with the
most frequent root first.

### 7.1 Controls (desktop)

| Control | Default | Meaning |
|---|---|---|
| Underlying | most frequent root | option root to compute |
| Time / slider | last loaded time | snapshot time. Type it (same formats as the filters) or drag the slider across the loaded time range. |
| Underlying price | blank (auto) | Optional spot. Used only for expiries where parity can't give a forward. |
| r | 4 % | continuously compounded risk-free rate |
| Options | Out-of-the-money (OTM) | which quotes to use: OTM, Call, Put or Call + Put |
| X axis | ln(K/F) | log-moneyness, strike K, or call delta |
| Max spread | 50 % | drop two-sided quotes with (ask − bid) / mid above this |
| Min expiry | 2 days | skip expiries closer than this |
| Max quote age | 30 min | drop contracts whose last update is older than this (0 = no limit) |

Press **Compute**. You can then use these views:

- **3D surface**:
  - Drag to rotate.
  - Scroll or pinch to zoom.
  - Middle-drag or ⌘-drag (Ctrl-drag on Windows and Linux) to pan.
  - Use the buttons for top, front and side views, a camera reset, and zoom in and out.
- **Heatmap**: click a cell to select that expiry and x value as slices.
- **Expiry list**: tick expiries to draw their **smile**. Circles are calls and triangles are puts, and vertical
  bars show the bid–ask IV range.
- **Term structure**: IV at a fixed x for each expiry: for example ATM `ln(K/F) = 0`, a fixed strike, or a fixed
  delta.
- **Export CSV…**: one row per IV point, with columns
  `sym, iid, exp, days, cp, K, F, k, delta, bid, ask, mid, iv, iv_bid, iv_ask, age_s`.

The terminal UI's IV tab (key `6`) computes the most frequent root with fixed settings: r = 4 %, OTM, max spread
50 %, min expiry 0.5 days and max quote age 30 min. Type a time in its input and press Enter. It shows the IV of
each expiry at fixed `ln(K/F)` buckets, followed by an ATM term-structure plot.

### 7.2 Method

1. **Snapshot**: for each contract, take the last record at or before the chosen time.
   - The price is the bid/ask **mid** when the quote is two-sided (bid > 0 and ask ≥ bid).
   - Otherwise it is the last trade price: `price`, or `close` for OHLCV.
   - If the loaded rows don't reach the chosen time (the scan was filtered or stopped at the row limit), the file is
     streamed from the start up to that time instead, and the progress is shown.
2. **Time to expiry**: expiry is taken as 16:00 America/New_York on the expiry date, and T = (expiry − t) / 365 days.
   The discount factor is D = e^(−rT).
3. **Forward per expiry (put-call parity)**:
   - Among strikes with both a call and a put mid, take the 5 where |C − P| is smallest.
   - Compute F = K + (C − P) / D for each of them and use the median.
   - If no strike has both, F = S·e^(rT) when an underlying price was entered; otherwise the expiry is skipped.
4. **Implied volatility**: Black-76, solved by vectorized bisection on [0.01 %, 600 %].
   - Prices outside the no-arbitrage range (at or below intrinsic value, or at or above the upper bound) get no IV.
   - Bid and ask IVs are computed the same way for the smile error bars.
5. **Quote selection**: OTM uses calls for K ≥ F and puts for K < F. Quotes are then dropped by the max-spread,
   min-expiry and max-age limits.
6. **Surface grid**:
   - Each expiry is linearly interpolated on a common x grid. For log-moneyness the grid is clipped to [−1, 1].
   - At most 40 expiries are drawn.

### 7.3 Caveats

- **OSI symbols only**: futures options and other symbologies aren't recognized.
- **Expiry time**: expiry is fixed at 16:00 New York. AM-settled contracts, such as SPX monthlies, actually expire
  hours earlier, which matters for short-dated expiries.
- **European model on American options**: Black-76 is a European model, while US equity options are American.
  - OTM selection keeps the early-exercise premium small.
  - **Call** / **Put** / **Call + Put** include in-the-money quotes, and their IVs can be biased.
- **One flat rate**: r is a single number. Dividends and borrow costs are absorbed into the parity forward of each
  expiry, not modeled separately.
- **Stale and wide quotes**:
  - Sampled schemas such as cbbo-1m are up to 60 s old by construction.
  - Use **Max quote age** and **Max spread** to drop illiquid contracts.
  - Trade-only data (trades, ohlcv) gives noisy IVs.
- **Streaming cost**: streaming to a time outside the loaded rows reads the file from the start, which can take
  minutes on a full OPRA day.

## 8. Terminal UI

```bash
dbnview-tui [FILE | DIR | ssh://HOST/DIR] [--tz America/New_York] [--lang en]
```

| Option | Meaning |
|---|---|
| `--tz` | display time zone (default `America/New_York`). Press `t` to cycle: New York, UTC, Chicago, London, Hong Kong, Tokyo. |
| `--lang` | `zh_Hant`, `zh_Hans`, `en`, `ja`, `de`, `ko` or `es` (default: the system language) |

**Layout**:

- **Sidebar**: file metadata, then filter inputs (symbol, instrument_id, from, to, where, max rows), a Scan button
  and scan progress.
- **Tabs**: `1` table · `2` detail · `3` chart · `4` stats · `5` format · `6` IV.

The detail tab shows all fields, the bid/ask ladder and the raw bytes. Press `b` on an MBO row to add the rebuilt
order book.

Press `e` to export the loaded rows as `NAME.csv` in the current directory.

## 9. Browser UI

```bash
dbnview-web [DIR_OR_FILE ...] [--port 8765] [--head N]
```

| Option | Meaning |
|---|---|
| `--port` | first port to try (default 8765). If it is taken, the next 19 ports are tried. |
| `--host` | bind address (default `127.0.0.1`). Keep the default and use an ssh tunnel for remote access. |
| `--no-token` | turn off the access token (not recommended) |
| `--open` | open a browser tab |
| `--head N` | print the first N records of each file given and exit, without starting a server |
| `--tz` | time zone for `--head` output (default `America/New_York`) |

**Security**:

- The server binds to localhost only.
- It prints a URL with a random `?token=…`. Requests without the token, or without the cookie set on the first
  visit, are rejected.

**Use on a server**: this is the usual way to look at data that lives on a server.

```bash
# on the server (only numpy + zstandard are needed)
dbnview-web /data/databento
# on your laptop
ssh -N -L 8765:localhost:8765 myserver
# then open the printed http://localhost:8765/?token=... in a local browser
```

**Single-file version**: if you can't install the package on the server, build a zipapp from a clone:

```bash
python tools/build_web_pyz.py           # writes dist/dbnview-web.pyz
scp dist/dbnview-web.pyz myserver:
ssh myserver python3 dbnview-web.pyz /data
```

**What the page offers**:

- a file browser, file metadata, the same filters as the desktop app, and the record table with jump-to-time
- row detail with raw bytes, and the MBO book rebuild
- a price-line chart, statistics, the format guide and CSV export

The page's labels are currently in Traditional Chinese only. The desktop app and the terminal UI have all seven languages.

## 10. Keyboard shortcuts

### 10.1 Desktop app

On Windows and Linux, ⌘ is Ctrl.

| Shortcut | Action |
|---|---|
| ⌘O | Open File… |
| ⇧⌘O | Open Remote File (ssh)… |
| ⌘R | Scan (rerun with the current filters) |
| ⌘. | Stop scan |
| ⌘E | Export CSV… |
| ⇧⌘R | MBO Order Book Replay… (MBO files) |
| ⌘I | show/hide the detail panel |
| ⌘L | show/hide the file and filter panel |
| ⌘Q | Quit (the platform's standard quit key) |
| Enter | in a filter field: scan. In the symbol field: add a substring pattern. |
| Delete / Backspace | remove the selected symbol pattern |
| mouse wheel / pinch, drag | zoom and pan charts |
| drag, wheel / pinch, middle-drag or ⌘-drag | rotate, zoom and pan the 3D IV surface |
| Space, ←/→, ⇧←/⇧→ | in the replay window: play/pause, step one second, step one event |

### 10.2 Terminal UI

| Key | Action |
|---|---|
| `o` | open (file picker: Enter opens, Backspace goes up, Esc cancels) |
| `s` / `x` | scan / stop |
| `/` | focus the symbol filter |
| `f` | show/hide the sidebar |
| `enter` | show the detail tab for the selected row |
| `b` | rebuild the MBO book at the selected row |
| `c` | cycle the chart mode: candles → quotes → flow |
| `i` | cycle the technical indicator on the candles |
| `t` | cycle the time zone |
| `1`–`6` | table, detail, chart, stats, format, IV |
| `e` | export the loaded rows to CSV |
| `q` | quit |
| `↑ ↓` / `j k`, `PgUp PgDn`, `Home End` / `g G`, `← →` | move in the table, scroll horizontally |

## 11. Languages

The desktop app and the terminal UI come in seven languages:

- Traditional Chinese
- Simplified Chinese
- English
- Japanese
- German
- Korean
- Spanish

This covers the menus, labels and the field, schema and enum documentation.

- **Desktop**: by default the app follows the system language. Change it in the **Language** menu, which switches
  immediately and is remembered.
- **Terminal UI**: use `--lang`.

## 12. Correctness and performance

- **Formats**: DBN v1, v2 and v3 are supported, and the layout is chosen from the file header. Newer versions are
  rejected with a clear error.
- **Record layouts**: they come from the official `databento_dbn` definitions, and the enum meanings were checked
  against databento.com/docs.
- **Checked against the official decoder**: the decoder was compared field by field with the official Databento
  decoder on CME MBO (v3), OPRA cbbo-1m (v1) and OPRA cmbp-1 (v1). All fields matched.
- **Undefined values**: integer "undefined" sentinels are shown as `—`. Prices use INT64_MAX, timestamps UINT64_MAX
  and quantities UINT32_MAX.
- **Throughput**: about 5–6 million records per second. Decompression runs on a background thread while records are
  parsed.
- **Large files**: zstd is not seekable, so every scan starts at the beginning of the file. Narrow a scan with
  filters. Use **Scan entire file** only when you need complete statistics.

## 13. Troubleshooting

| Problem | What to do |
|---|---|
| macOS says the app "can't be opened" or is damaged | The self-built app is ad-hoc signed and not notarized. In Finder, right-click the app → **Open** once, or run `xattr -cr /Applications/DBNView.app`. |
| Linux: `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | Install the Qt xcb libraries, for example `sudo apt install libxkbcommon-x11-0 libxcb-cursor0 libegl1`. Or use `dbnview-tui` / `dbnview-web`. |
| Remote open fails with `Permission denied`, `Host key verification failed` or a timeout | ssh runs in BatchMode, so it can't ask for anything. First run `ssh HOST true` in a terminal: it must succeed without a prompt (accept the host key, load your key into the agent, check `~/.ssh/config`). |
| Remote directory listing is empty or fails | The remote side needs GNU `find` and `stat` (Linux). Check that the path is absolute. |
| Scan stops at 1,000,000 rows | That is the row limit. Raise **Max rows**, narrow the filters, or tick **Scan entire file** for complete statistics. |
| A huge file takes long to reach the afternoon | Scans always start at the beginning. Add a time filter so only the rows you need are kept. For remote files, consider running `dbnview-web` next to the data. |
| Order book looks wrong | See [4.2](#42-filters-and-the-mbo-book). Rescan without start-time, action/side or `where` filters. Files without an initial clear or snapshot miss orders placed before the file starts. |
| `DBN vN is not supported yet` | The file uses a DBN version newer than 3. |
| `pip install zstandard` error | The engine needs `zstandard` to read `.zst` files. Reinstall the package. |
| IV tab says the file is not option data | No OSI option symbols were found in the mappings (see [7.3](#73-caveats)). |
