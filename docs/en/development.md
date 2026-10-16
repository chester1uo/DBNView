[简体中文](../zh-CN/development.md) · [README](../../README.md)

# DBNView development guide

This guide covers setting up a development environment, running and testing DBNView, adding translations and
record types, and packaging and releasing it. For how the code is organized, see [architecture.md](architecture.md).

## 1. Setup

```bash
git clone https://github.com/chester1uo/DBNView.git
cd DBNView
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip install -e ".[dev]"
```

The `dev` extra installs both front ends plus `pytest`, `pyflakes` and `pyinstaller`.

The install is editable, so changes under `src/dbnview/` take effect on the next run. This includes the package data
files `engine/spec.json` and `web/static/ui.html`.

On Windows, replace `.venv/bin/` with `.venv\Scripts\` in every command below.

Never commit market data: `.gitignore` excludes `*.dbn`, `*.zst` and `*.parquet`.

## 2. Running from source

```bash
.venv/bin/python -m dbnview path/to/file.dbn.zst          # desktop app
.venv/bin/python -m dbnview.tui path/to/dir               # terminal UI
.venv/bin/python -m dbnview.web path/to/dir --open        # browser UI
.venv/bin/python -m dbnview.web file.dbn.zst --head 20    # print the first 20 records and exit
```

The installed commands `dbnview`, `dbnview-tui` and `dbnview-web` do the same thing.

The desktop app stores its settings with `QSettings("dbnview", "dbnview")`: language, time zone and time format,
recent files, hidden columns, window layout, the last remote host and directory, and chart indicators.

**Screenshot self-test.** With `DBNVIEW_SELFTEST` set, the desktop app waits for the scan to finish, renders every
tab to `PREFIX_<n>.png`, and quits. It also computes the IV surface if the file has options.

```bash
DBNVIEW_SELFTEST=/tmp/dbnview_shot .venv/bin/python -m dbnview path/to/file.dbn.zst
```

## 3. Tests

```bash
.venv/bin/python -m pytest              # whole suite
.venv/bin/python -m pytest -x -k mbo    # stop at first failure, only tests matching "mbo"
```

The tests need no market data. `tests/dbn_writer.py` writes small synthetic DBN files (v1–v3, plain or zstd) using
the layouts in `engine/spec.json`. Fixtures in `tests/conftest.py` build MBO, trades and option files in a temporary
directory.

| File | Covers |
|---|---|
| `test_engine.py` | metadata round trip, decoding, v4 rejection, filters, time filter and seek, row limit, raw layout, statistics |
| `test_analysis.py` | MBO book replay, bars, heatmap, price series, OSI parsing, Black-76 IV round trip, surface/forward recovery |
| `test_indicators.py` | SMA/EMA, Bollinger, VWAP, RSI, MACD, ATR, Stochastic, the indicator registry |
| `test_i18n.py` | every `T("…")` literal has a complete translation with matching placeholders; reference locales share keys |
| `test_frontends.py` | web API, headless TUI, offscreen GUI. Each is skipped when its optional dependencies are missing. |

The GUI test sets `QT_QPA_PLATFORM=offscreen`, so it runs without a display. On Linux CI it still needs the Qt
system libraries.

## 4. Lint

```bash
.venv/bin/python -m pyflakes src
```

No output means the code is clean. Keep it that way before committing. CI also lints the tests:
`python -m pyflakes src tests`.

## 5. Code rules

- **Dependency rule**: `engine/`, `analysis/`, `reference/`, `i18n/` and `display.py` must not import Qt or
  Textual (see [architecture.md](architecture.md#11-dependency-rule)). Put shared logic there and keep front ends
  thin.
- **Never block the UI thread**: anything that reads a file, the network or many rows runs in the background.
  - GUI: `run_bg(fn, *args, done=..., fail=...)` from `gui/common.py`.
  - TUI: `@work(thread=True)` plus `call_from_thread`.
- **Scan state**: front ends read it from `job.status()` and `job.rows()` and never reach into numpy segments
  directly. The exceptions are `analysis.*` functions, which take the `Job`.
- **Translated text**: every user-visible string goes through `T()`. Field and enum help comes from `reference`.

## 6. Translations

The desktop app and the terminal UI support 7 languages:

| Code | Language |
|---|---|
| `zh_Hant` | Traditional Chinese |
| `zh_Hans` | Simplified Chinese |
| `en` | English |
| `ja` | Japanese |
| `de` | German |
| `ko` | Korean |
| `es` | Spanish |

### 6.1 Adding a UI string

1. Wrap the text in `T(...)` where it is used:

   ```python
   from ..i18n import T

   go = QtWidgets.QPushButton(T("IV 曲面"))
   ```

   The key is the source string itself. Existing keys are the original (Chinese) UI text. If no entry exists,
   `T()` returns the key unchanged, which is why missing translations show up as untranslated text rather than
   errors.

2. Add an entry with **all 7 languages** to `src/dbnview/i18n/strings.py`:

   ```python
   STRINGS = {
       # ...
       'IV 曲面': {'zh_Hant': 'IV 曲面', 'zh_Hans': 'IV 曲面', 'en': 'IV Surface', 'ja': 'IV サーフェス',
                   'de': 'IV-Fläche', 'ko': 'IV 곡면', 'es': 'Superficie de IV'},
   }
   ```

3. Run `pytest tests/test_i18n.py`. It fails in three cases:
   - a `T("…")` literal has no entry
   - an entry lacks a language
   - a translation's placeholders (`%s`, `%d`, `%.1f`, `{name}`) don't match the key's

Tips:

- Leading and trailing spaces are part of the key.
- Write shortcut hints with macOS glyphs (⌘, ⇧⌘). In the GUI, pass the result through `native_shortcuts()`, which
  turns them into `Ctrl+` / `Ctrl+Shift+` on Windows and Linux.
- Translations are looked up by the literal key, so never pass already-formatted text to `T()`. Keep the placeholders
  in the key and format the result: `T(key) % n`.

### 6.2 Field, schema and enum documentation

The help texts shown in column-header tooltips, the detail panel and the Format Guide live in
`src/dbnview/reference/`.

- `locales/<code>.py` (one file per language) each define:
  - `FIELD_DOC`: field name → explanation
  - `LEVEL`: templates used to generate `bid_px_00` … `ask_ct_09` texts
  - `RESERVED`: text for padding fields
  - `SCHEMA_DOC`: schema → what one row means
  - `STYPE_DOC`: symbology type → explanation
  - `ENUMS`: action, side, flags, `stat_type` and sentinel tables
  - `TIPS`: the "common pitfalls" list
- **All locale files share the same keys.** `test_i18n.py` checks that `FIELD_DOC`, `SCHEMA_DOC` and the `ENUMS`
  tables match across languages.
- `enums.py` holds `ENUM_VALUES[(record class, field)] = {code: meaning}`: the official English meanings from
  databento.com/docs, used for status, statistics and definition codes. These are not translated.

To document a new field, add its key to `FIELD_DOC` in **every** `locales/*.py` file. Write `en.py` first, then
translate.

To add an eighth language:

1. Create `locales/<code>.py` with the same names and keys.
2. Add `(code, native name)` to `LANGS` in `i18n/__init__.py`.
3. Add the code to every entry in `strings.py`.
4. Let `system_lang()` recognize the code.

## 7. Supporting a new record type

1. **Layout**: add the record class to `src/dbnview/engine/spec.json` under `versions → "1" / "2" / "3"` for each
   DBN version that has it.

   ```json
   "NewMsg": {
     "f":   [["length", "u1"], ["rtype", "u1"], ["publisher_id", "u2"], ["instrument_id", "u4"],
             ["ts_event", "u8"], ["price", "i8"], ["size", "u4"], ["_reserved", "S4"], ["ts_recv", "u8"]],
     "px":  ["price"],
     "ts":  ["ts_event", "ts_recv"],
     "ord": ["ts_recv", "ts_event", "rtype", "publisher_id", "instrument_id", "price", "size"]
   }
   ```

   - `f`: every field in byte order with its numpy type, including reserved and padding fields, so that the dtype
     size equals the record length.
   - `px`: fixed-point price fields (÷ 1e9).
   - `ts`: nanosecond timestamps.
   - `ord`: display order.
   - Take the definitions from the official `databento_dbn` sources, which the existing layouts come from.
   - If the dtype is larger than the record length in a file, `RecordType` falls back to the 16-byte header.

2. **rtype**: add `rtype: ("NewMsg", "display-name")` to `RTYPES` in `src/dbnview/engine/constants.py`.
   - If the class uses the integer maximum as "undefined", add it to `NULL_MAX_CLASSES`.
   - For a new schema, append it to `SCHEMAS`. The list index is the schema id stored in the metadata header, so the
     order matters.

3. **Docs**:
   - Add `(rtype, name)` to `RTYPE_DOC` in `reference/__init__.py`.
   - Add the schema to `SCHEMA_DOC` and new fields to `FIELD_DOC` in every locale.
   - Add official enum meanings to `enums.py`.

4. **Charts** (optional): if the record carries trades, quotes or bars, add the class to `TRADE_CLASSES`,
   `QUOTE_CLASSES` or `BAR_CLASSES` in `analysis/market.py`.

5. **Tests**:
   - Add the class to `CLASS_RTYPE` in `tests/dbn_writer.py`.
   - Write a synthetic file in a fixture, and assert that the decoded values, filters and `job.raw()` layout are
     right.
   - If you can, also compare against the official `databento` decoder on a real file.

## 8. Packaging

### 8.1 Desktop app (PyInstaller)

PyInstaller doesn't cross-compile, so build on each target OS with the `dev` extra installed:

```bash
.venv/bin/pyinstaller --noconfirm packaging/dbnview.spec
```

| OS | Output | Notes |
|---|---|---|
| macOS | `dist/DBNView.app` | Ad-hoc sign it after building (command below). It registers as a viewer for `.dbn` / `.zst` files. |
| Windows | `dist/DBNView/DBNView.exe` | Ship the whole `dist/DBNView/` folder. Windows has no console window. |
| Linux | `dist/DBNView/DBNView` | Ship the folder. The target machine needs the Qt xcb libraries. |

On macOS, sign the app after building:

```bash
xattr -cr dist/DBNView.app && codesign -s - --force --deep dist/DBNView.app
```

The ad-hoc signature is enough for your own machine. To distribute to others without Gatekeeper warnings, you need a
Developer ID certificate and notarization, which are not set up.

About `packaging/dbnview.spec`:

- The entry script is `packaging/launcher.py`.
- It bundles the `dbnview` package data (`spec.json`, `ui.html`) and pyqtgraph's data files.
- It excludes `textual`, `plotext` and unused Qt modules, so the bundle contains only the desktop front end.
- The icons `packaging/dbnview.icns` (macOS), `packaging/dbnview.ico` (Windows) and `packaging/icon.png` (Linux)
  are drawn by `packaging/make_icon.py`. Building the `.icns` needs macOS `iconutil`.

Smoke-test the bundle with the self-test:

```bash
DBNVIEW_SELFTEST=/tmp/shot dist/DBNView.app/Contents/MacOS/DBNView path/to/file.dbn.zst   # macOS
DBNVIEW_SELFTEST=/tmp/shot dist/DBNView/DBNView path/to/file.dbn.zst                      # Linux
```

Then check the PNGs it writes.

### 8.2 Single-file browser UI for servers

```bash
python tools/build_web_pyz.py            # writes dist/dbnview-web.pyz
```

This zipapp contains everything except `gui/` and `tui/`. It runs with `python3 dbnview-web.pyz /data` on any
machine that has Python 3.9+ with `numpy` and `zstandard`.

### 8.3 Python package

```bash
.venv/bin/pip wheel . --no-deps -w dist
```

The version comes from `dbnview.__version__` (`src/dbnview/__init__.py`). `pyproject.toml` declares the package data
(`engine/spec.json`, `web/static/*.html`).

## 9. Continuous integration

`.github/workflows/ci.yml` runs on GitHub Actions on every push and pull request. It has two jobs:

- **test**: on Ubuntu, macOS and Windows with Python 3.9 and 3.12, it installs `.[all]`, runs
  `python -m pyflakes src tests` and `python -m pytest -q`. Qt runs offscreen, and the Linux runner installs the Qt
  system libraries first.
- **package**: after the tests pass, it builds the desktop app with PyInstaller on each OS. It uploads
  `DBNView-macOS.zip` (ad-hoc signed), `DBNView-Windows.zip` and `DBNView-Linux.tar.gz` as workflow artifacts; the
  Linux job also uploads `dist/dbnview-web.pyz`. You can download them from the run's page.

## 10. Release checklist

1. Bump `__version__` in `src/dbnview/__init__.py`. It is the only place the version is stored.
2. `python -m pyflakes src` prints nothing, and `pytest` passes, including `test_i18n.py` for new strings.
3. Open real files of the main kinds:
   - CME MBO and MBP-10, OPRA cbbo-1m / cmbp-1, and an OHLCV file
   - one file over ssh
   - check the table, detail and book, every chart type, the IV surface and CSV export
4. Run the terminal UI and the browser UI once on the same files.
5. Build the desktop app on macOS, Windows and Linux, or take the CI artifacts, and run the `DBNVIEW_SELFTEST` smoke
   test on each. On macOS, check that right-click → **Open** and **Open With** work.
6. Build `dist/dbnview-web.pyz` and start it on a server through an ssh tunnel.
7. Update `README.md` / `README.zh-CN.md` and `docs/en/` / `docs/zh-CN/` together. The two languages mirror each
   other section by section.
8. Commit, tag `vX.Y.Z`, push the tag, and attach the desktop builds and `dbnview-web.pyz` to the GitHub release.
