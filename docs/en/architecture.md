[简体中文](../zh-CN/architecture.md) · [README](../../README.md)

# DBNView architecture

DBNView is one Python package, `dbnview` (in `src/dbnview/`). It is built as a small engine with no UI code, a few
UI-independent helper packages, and three thin front ends on top.

## 1. Package layout

| Path | Responsibility |
|---|---|
| `engine/` | DBN decoding with numpy + zstandard only. See the module table below. |
| `analysis/` | Data derived from loaded rows: chart series (`market.py`), technical indicators on bars (`indicators.py`), the MBO order book (`book.py`) and option chains, snapshots, parity forwards and Black-76 IV (`options.py`). |
| `reference/` | Human-readable documentation of fields, schemas, stypes, enums and pitfalls. `locales/{zh_Hant,zh_Hans,en,ja,de,ko,es}.py` share the same keys, and `enums.py` holds the official English meanings of enum codes for status, statistics and definition records. |
| `i18n/` | UI strings. `T(key)` returns the text for the current language; `strings.py` maps each key to its 7 translations. `LANGS`, `set_lang()`, `get_lang()`, `system_lang()`. |
| `display.py` | Formatting helpers shared by all front ends: bytes, numbers, prices, durations, `TsFmt` (nanosecond timestamps in a time zone), `display_name()`, `ssh_hosts()` (reads `~/.ssh/config`). |
| `gui/` | PySide6 desktop app (see the table below). |
| `tui/` | Textual terminal UI: `app.py` (app, key bindings, workers, file picker), `table.py` (virtual record table), `views.py` (rich renderables, and plotext charts and IV tables). |
| `web/` | Browser UI: `server.py` (stdlib `ThreadingHTTPServer` plus a JSON API over the engine) and `static/ui.html` (single-page front end). |
| `__main__.py`, `tui/__main__.py`, `web/__main__.py` | `python -m dbnview`, `python -m dbnview.tui`, `python -m dbnview.web` |

The `engine/` modules:

| Module | Contents |
|---|---|
| `constants.py` | `RTYPES`, `SCHEMAS`, `STYPES`, sentinels, flag bits, and `spec.json` |
| `records.py` | `RecordType`: the numpy dtype for each (version, rtype, length, ts_out), plus `record_layout()` |
| `metadata.py` | parsing the v1–v3 metadata header, and its byte map |
| `stream.py` | `iter_records()`: yields runs of same-type records as zero-copy numpy views, with zstd decompression on a prefetch thread |
| `sources.py` | local files and `ssh host cat` streams, zstd detection, directory listing, `ssh_run()` |
| `symbology.py` | `SymbolMap`: instrument_id ↔ symbol over time, and symbol search |
| `timeutil.py` | `get_tz`, `parse_time`, `fmt_ts` |
| `filters.py` | `Filter`, and the safe `WhereExpr` evaluator |
| `formatting.py` | numpy column → Python value conversion for display |
| `scan.py` | `FileInfo` (metadata cache) and `Job` (background scan) |

The `gui/` modules:

| Module | Contents |
|---|---|
| `app.py` | entry point; handles Open With / FileOpen events and language switching |
| `main_window.py` | menus, toolbar, the open → scan → poll lifecycle |
| `filter_panel.py` | file info, filters, progress |
| `table_panel.py`, `table_model.py` | virtual table, column menu, seek, CSV export |
| `detail_panel.py` | fields, ladder, MBO book, raw bytes |
| `charts.py` | pyqtgraph charts |
| `stats_view.py` | Statistics tab |
| `format_view.py` | Format Guide tab |
| `iv_panel.py` | IV surface: 3D view, heatmap, smile, term structure |
| `remote_dialog.py` | ssh file browser |
| `gestures.py` | trackpad pinch zoom |
| `common.py` | `run_bg`, theme colors, shared helpers |

### 1.1 Dependency rule

`engine`, `analysis`, `reference`, `i18n` and `display.py` **must not import Qt or Textual**. They form the shared
core:

- The browser UI runs on servers with only `numpy` and `zstandard`.
- `tools/build_web_pyz.py` packs everything except `gui/` and `tui/` into one file.

The only exception is a guarded `try: from PySide6.QtCore import QLocale` in `i18n.system_lang()`. It is used for
OS language detection, and the function falls back to `LANG` and `locale` when Qt is missing.

The front ends depend on the core and never on each other:

```text
front ends   gui/ (PySide6, pyqtgraph)    tui/ (Textual, plotext)    web/ (http.server + ui.html)
                  │                            │                           │
                  └──────────────┬─────────────┴───────────────────────────┘
                                 ▼
core         analysis/ ──► engine/ ◄── display.py        reference/        i18n/
```

## 2. Data flow

```text
path or ssh://host/path
   │
   ▼
FileInfo.get(path)            cached per path (local files: re-read when mtime changes)
   · source_stat()            size, mtime (ssh: stat -L -c)
   · parse_metadata()         dataset, schema, version, ts_out, symbols, mappings
   · first RecordType         so the UI knows the columns before scanning
   · SymbolMap(metadata)
   │
   ▼
Job(path, query)              starts a daemon thread immediately
   · open_stream()            _CountingReader (file or ssh pipe) → zstd stream_reader
   · iter_records()           (RecordType, ndarray) runs; a prefetch thread decompresses
   · Filter.mask()            symbols/ids, time window, rtype, action/side, where
   · keep up to `cap` rows    segments = [(RecordType, records copy, file record index)]
   · counters                 per rtype/action/side, instrument histogram, minute histogram, tmin/tmax
   │
   ├── job.status(with_stats)    polled by the front end (progress, columns, stats)
   ├── job.rows(offset, limit)   formats only the requested rows (format_column)
   ├── job.raw(row)              hex bytes + byte layout of one row
   ├── job.seek(ts_ns)           row index for "jump to time"
   └── job.iter_instrument(iid)  per-instrument record runs → analysis.*
```

The steps in the diagram:

1. `FileInfo.get()` caches file information per path, and re-reads a local file when its modification time changes.
   It gets the size and modification time, parses the metadata header, and peeks at the first record type so the
   UI knows the columns before scanning. It also builds a `SymbolMap` from the metadata.
2. `Job` starts a daemon thread as soon as it is created. The thread opens the stream (a local file or an ssh pipe,
   then zstd decompression), decodes records run by run, applies the filters, keeps up to `cap` rows and updates the
   counters.
3. Front ends read the results through `status()`, `rows()`, `raw()`, `seek()` and `iter_instrument()`.

Some details:

- **Decoding**: `iter_records` reads the record length and rtype at the current position. It then checks how many
  following records have the same length and rtype, and views them all at once with `np.frombuffer` using the
  `RecordType` dtype. All further work (filters, statistics, chart data) is vectorized numpy over these runs.
- **`RecordType`**:
  - It is built from `engine/spec.json`. That file is keyed by DBN version, then by record class; each class lists
    its fields (`f`), price fields (`px`), timestamp fields (`ts`) and display order (`ord`).
  - `RTYPES` maps each rtype to its class and display name.
  - An unknown rtype falls back to the 16-byte common header, so a file never fails to open because of one.
  - TBBO is stored under the MBP-1 rtype; the metadata schema decides which name is shown.
- **Symbols**: `SymbolMap` starts from the metadata mappings. During a scan it also learns from `SymbolMappingMsg`
  records and from `raw_symbol` in definition records.
- **Job registry**: `Job.jobs` keeps the 6 most recent jobs. Older ones are cancelled, which bounds memory in the
  browser UI where scans are addressed by id.

## 3. Threading model

| Where | What runs off the UI thread | How results come back |
|---|---|---|
| engine | every `Job` scans in its own daemon thread; `iter_records` adds a decompression prefetch thread (zstd releases the GIL) | the front end polls `job.status()`. Cancellation is cooperative through `job.cancelled = True`. |
| GUI | `run_bg(fn, *args, done=..., fail=...)` (in `gui/common.py`) runs `fn` on `QThreadPool.globalInstance()`. It is used for opening files (`FileInfo.get`), chart data, book rebuild, the IV surface, CSV export and remote directory listing. | `done` / `fail` are Qt signals, so callbacks run on the GUI thread. A `QTimer` polls the scan every 200 ms. |
| TUI | Textual workers: `@work(thread=True, exclusive=True, group=...)` for file loading, charts, book, IV and export | `self.call_from_thread(...)` updates widgets. `set_interval(0.25, poll)` polls the scan. |
| web | `ThreadingHTTPServer` handles each request in its own thread | the page polls `/api/job` and fetches pages of rows with `/api/rows` |

Rules that keep this safe:

- Engine and analysis objects are never touched by Qt or Textual from worker threads. Workers return plain data.
- `Job` takes a lock while it appends segments. Readers (`rows`, `iter_instrument`, `options.snapshot`) copy the
  segment list under the same lock and then work without it.
- A long computation that the user can supersede checks a token or callback (`cancel=` in `options.surface`, and
  `exclusive=True` workers in the TUI).

## 4. Chart data

`analysis/market.py` turns a `Job` and an `instrument_id` into plain numpy arrays. Times are float seconds since the
epoch, prices are in real units, and undefined values are `NaN`. The front ends only draw: pyqtgraph in the GUI,
plotext in the TUI, and the price line in the browser UI.

| Function | Returns |
|---|---|
| `inst_records(job, iid)` | the dominant record class of the instrument, time-sorted (`ts_recv`, or `ts_event` for OHLCV) |
| `capabilities(job, iid)` | which charts are possible: `bars`, `quotes`, `flow`, `heatmap` |
| `bars(job, iid, interval, source)` | OHLCV candles: native bars (regrouped if coarser), from trades with buy/sell volume, or from quote mid |
| `quotes(job, iid)` | bid/ask/mid/spread, top-of-book imbalance, overlaid trades (thinned to `maxpts`) |
| `flow(job, iid)` | trade points, buy/sell volume per bar, CVD, volume profile, VWAP |
| `heatmap(job, iid)` | bid and ask resting size on a time × price grid, best bid/ask, trades |
| `price_series(job, iid)` | every price field over time, min/max-downsampled to about `maxpts` points |
| `pick_interval(span_s, max_bars)` | the smallest standard interval (1s … 1W) that gives at most `max_bars` bars |

The functions see only the rows the scan loaded, never the whole file.

`analysis/indicators.py` works one level higher, on the bars dict returned by `bars()`:

- It provides pure-numpy `sma`, `ema`, `bollinger`, `vwap`, `rsi`, `macd`, `atr` and `stochastic`. Each returns
  `NaN` until there is enough history.
- `INDICATORS` describes each indicator for the front ends: `kind` is `overlay` (drawn on the price pane) or `pane`
  (its own oscillator pane), plus default `params`, output `lines` with color roles, and guide `levels`.
- `compute(key, bars, params)` returns the output lines, and `label(key, params)` returns the display name.
- The GUI and the TUI only draw these lines.

## 5. MBO order book

`analysis/book.py` holds one `OrderBook` class:

- It stores L3 orders (`order_id → side, price, size`) and keeps L2 levels (`price → size, order count`) up to date
  incrementally.
- It applies `A` (add), `M` (modify; an unknown order is treated as an add), `C` (partial or full cancel) and `R`
  (clear).
- `T`, `F` and `N` don't change the book.
- Messages with the TOB flag replace that side's top level.

The same class serves two features:

- `book_at(job, row, depth)` replays every loaded MBO row of the instrument up to `row`. The detail panel, the TUI
  `b` key and `/api/book` use it. Its result carries:
  - `safe`, from `Filter.book_safe`: false when a start time, action/side, `where` or rtype filter could have dropped
    earlier messages
  - `had_clear`, which tells whether a clear (`R`) was seen
- `market.heatmap()` replays MBO through `_mbo_snapshots()` and samples the top 40 levels at each time-bin edge.

## 6. Options pipeline

`analysis/options.py` is used by the IV Surface tab (GUI) and the IV tab (TUI):

```text
chain(job)            instrument_id → (root, expiry, C/P, strike) from OSI symbols in the SymbolMap
is_option_data(job)   ≥ 50% of the first 200 instruments parse as OSI
roots(chain)          roots by contract count
surface(job, t_ns, root, r, spot, side, max_spread, min_days, max_age_s, ...)
  ├─ loaded_covers(job, t_ns) ? snapshot(job, ...)          last record ≤ t per contract from loaded rows
  │                           : stream_snapshot(job, ...)   re-read the file from the start up to t
  ├─ mid (two-sided) or last trade / close
  ├─ T to 16:00 America/New_York on expiry, D = e^(−rT)
  ├─ forward per expiry: median of K + (C − P)/D over the 5 strikes with the smallest |C − P|
  │                      (fallback: spot·e^(rT) when the user gave a spot)
  ├─ select OTM / call / put / both, drop by max_spread, min_days, max_age
  └─ implied_vol(): vectorized Black-76 bisection (mid, bid, ask) and call delta
grid(s, x)            regular x grid × expiries for the 3D surface / heatmap
term_at(s, x, value)  IV at a fixed x for each expiry
```

How the pipeline works:

1. `chain()` parses the root, expiry, C/P and strike of each instrument_id from the OSI symbols in the `SymbolMap`.
   `is_option_data()` requires at least half of the first 200 instruments to parse as OSI symbols.
2. `surface()` first takes a snapshot. If the loaded rows cover the chosen time, it uses them; otherwise it re-reads
   the file from the start up to that time.
3. It then takes the mid (for two-sided quotes) or the last trade price, computes the time to expiry and the discount
   factor, and derives a forward per expiry from put-call parity. Finally it filters the quotes and computes implied
   volatility and call delta with a vectorized Black-76 bisection.
4. `grid()` builds a regular grid for the 3D surface and the heatmap, and `term_at()` gives the IV of each expiry at a
   fixed x.

`ncdf` (the normal CDF from Abramowitz–Stegun) and `black76` are written in numpy, so SciPy is not needed.

## 7. Front ends

| | Desktop (`gui/`) | Terminal (`tui/`) | Browser (`web/`) |
|---|---|---|---|
| Entry point | `dbnview.gui.app:main` | `dbnview.tui.app:main` | `dbnview.web.server:main` |
| Table | `QTableView` + `RecordModel`, rows fetched on demand | `RecordTable` (`ScrollView`), lines rendered on demand | `/api/rows` pages |
| Charts | all five chart types + technical indicators (pyqtgraph) | candles (+ one indicator) / quotes / flow (plotext) | price line |
| IV surface | full (3D, heatmap, smile, term, CSV) | IV table + ATM term structure | — |
| Remote files | ssh dialog, `ssh://` argument | `ssh://` argument, file picker | local paths on the server |
| Languages | 7 | 7 | Traditional Chinese labels only |

The shared state of the desktop app lives on `MainWindow`:

- `fi` / `meta`: the open file
- `job` / `status`: the scan
- `stats`
- `tsfmt`: the time format and zone
- `colors`, `settings`

Panels receive the window as `win` and read that state from it. They talk to each other through Qt signals
(`rowSelected`, `scanRequested`, `filterRequested`, `chartRequested`).

The browser API (`web/server.py`):

- `GET /api/{init,ls,meta,symbols,job,cancel,rows,seek,chart,raw,book}`
- `POST /api/scan`
- `GET /api/export`, which streams a CSV

Every request must carry the token, as a query parameter, an `X-Token` header or the `dbnview` cookie.
