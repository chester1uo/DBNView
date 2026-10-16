[English](../en/architecture.md) · [README](../../README.zh-CN.md)

# DBNView 架构

DBNView 是一个 Python 包 `dbnview`（位于 `src/dbnview/`）。它由三部分组成：一个不含任何界面代码的小型引擎、
几个与界面无关的辅助包，以及构建在它们之上的三个轻量前端。

## 1. 包结构

| 路径 | 职责 |
|---|---|
| `engine/` | DBN 解码，只依赖 numpy 和 zstandard。各模块见下表。 |
| `analysis/` | 基于已载入行的派生数据：图表序列（`market.py`）、K 线上的技术指标（`indicators.py`）、MBO 订单簿（`book.py`），以及期权链、快照、平价远期价格和 Black-76 隐含波动率（`options.py`）。 |
| `reference/` | 字段、schema、stype、枚举和常见陷阱的可读说明。`locales/{zh_Hant,zh_Hans,en,ja,de,ko,es}.py` 使用相同的键；`enums.py` 存放 status、statistics、definition 记录中枚举代码的官方英文含义。 |
| `i18n/` | 界面文字。`T(key)` 返回当前语言的文字；`strings.py` 把每个键映射到 7 种翻译。还提供 `LANGS`、`set_lang()`、`get_lang()`、`system_lang()`。 |
| `display.py` | 所有前端共用的格式化工具：字节数、数字、价格、时长、`TsFmt`（按时区格式化纳秒时间戳）、`display_name()`、`ssh_hosts()`（读取 `~/.ssh/config`）。 |
| `gui/` | PySide6 桌面应用（见下表）。 |
| `tui/` | Textual 终端界面：`app.py`（应用、按键绑定、worker、文件选择器）、`table.py`（虚拟记录表格）、`views.py`（rich 渲染内容，以及 plotext 图表和 IV 表格）。 |
| `web/` | 浏览器界面：`server.py`（标准库的 `ThreadingHTTPServer`，加上基于引擎的 JSON API）和 `static/ui.html`（单页前端）。 |
| `__main__.py`、`tui/__main__.py`、`web/__main__.py` | `python -m dbnview`、`python -m dbnview.tui`、`python -m dbnview.web` |

`engine/` 的各个模块：

| 模块 | 内容 |
|---|---|
| `constants.py` | `RTYPES`、`SCHEMAS`、`STYPES`、哨兵值、flag 位，以及 `spec.json` |
| `records.py` | `RecordType`：每个 (version, rtype, length, ts_out) 对应的 numpy dtype，以及 `record_layout()` |
| `metadata.py` | 解析 v1–v3 元数据头，并生成它的字节映射 |
| `stream.py` | `iter_records()`：把同类型的连续记录作为零拷贝 numpy 视图逐段产出，zstd 解压在预取线程中进行 |
| `sources.py` | 本地文件和 `ssh host cat` 流、zstd 检测、目录列表、`ssh_run()` |
| `symbology.py` | `SymbolMap`：随时间变化的 instrument_id ↔ symbol 映射，以及 symbol 搜索 |
| `timeutil.py` | `get_tz`、`parse_time`、`fmt_ts` |
| `filters.py` | `Filter`，以及安全的 `WhereExpr` 求值器 |
| `formatting.py` | 把 numpy 列转换成用于显示的 Python 值 |
| `scan.py` | `FileInfo`（元数据缓存）和 `Job`（后台扫描） |

`gui/` 的各个模块：

| 模块 | 内容 |
|---|---|
| `app.py` | 入口；处理“打开方式”/ FileOpen 事件和语言切换 |
| `main_window.py` | 菜单、工具栏，以及“打开 → 扫描 → 轮询”的流程 |
| `filter_panel.py` | 文件信息、筛选条件、进度 |
| `table_panel.py`、`table_model.py` | 虚拟表格、列菜单、时间跳转、CSV 导出 |
| `detail_panel.py` | 字段、买卖盘档位、MBO 订单簿、原始字节 |
| `charts.py` | pyqtgraph 图表 |
| `stats_view.py` | 统计标签页 |
| `format_view.py` | 格式说明标签页 |
| `iv_panel.py` | IV 曲面：3D 视图、热图、波动率微笑、期限结构 |
| `remote_dialog.py` | ssh 文件浏览器 |
| `gestures.py` | 触控板双指缩放 |
| `common.py` | `run_bg`、主题颜色、共用工具 |

### 1.1 依赖规则

`engine`、`analysis`、`reference`、`i18n` 和 `display.py` **不得导入 Qt 或 Textual**。它们构成共享核心：

- 浏览器界面要在只装有 `numpy` 和 `zstandard` 的服务器上运行。
- `tools/build_web_pyz.py` 会把 `gui/` 和 `tui/` 以外的所有内容打包成一个文件。

唯一的例外是 `i18n.system_lang()` 中带保护的 `try: from PySide6.QtCore import QLocale`。它用于检测操作系统语言，
没有 Qt 时会退回使用 `LANG` 和 `locale`。

前端依赖核心，前端之间互不依赖：

```text
front ends   gui/ (PySide6, pyqtgraph)    tui/ (Textual, plotext)    web/ (http.server + ui.html)
                  │                            │                           │
                  └──────────────┬─────────────┴───────────────────────────┘
                                 ▼
core         analysis/ ──► engine/ ◄── display.py        reference/        i18n/
```

## 2. 数据流

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

图中各步骤：

1. `FileInfo.get()` 按路径缓存文件信息（本地文件的修改时间变化时会重新读取）。它获取文件大小和修改时间，
   解析元数据头，预读第一种记录类型，好让界面在扫描前就知道有哪些列，并根据元数据建立 `SymbolMap`。
2. `Job` 创建后立即启动一个守护线程。该线程打开数据流（本地文件或 ssh 管道，再接 zstd 解压），逐段解码记录，
   应用筛选，最多保留 `cap` 行，并累计各类计数。
3. 前端通过 `status()`、`rows()`、`raw()`、`seek()` 和 `iter_instrument()` 读取结果。

一些细节：

- **解码**：`iter_records` 先读取当前位置的记录长度和 rtype，再检查后面有多少条记录的长度和 rtype 相同，然后用
  `np.frombuffer` 和对应 `RecordType` 的 dtype 一次性取得这些记录的视图。之后的所有处理（筛选、统计、图表数据）
  都是在这些连续段上做向量化的 numpy 运算。
- **`RecordType`**：
  - 它根据 `engine/spec.json` 构建。该文件先按 DBN 版本、再按记录类分组；每个类列出字段（`f`）、价格字段
    （`px`）、时间戳字段（`ts`）和显示顺序（`ord`）。
  - `RTYPES` 把每个 rtype 映射到记录类和显示名称。
  - 未知的 rtype 会退回只解析 16 字节的公共头，所以文件不会因为未知记录类型而无法打开。
  - TBBO 使用 MBP-1 的 rtype 存储，显示哪个名称由元数据中的 schema 决定。
- **Symbol**：`SymbolMap` 以元数据中的映射为基础。扫描过程中，它还会从 `SymbolMappingMsg` 记录和 definition
  记录的 `raw_symbol` 中补充映射。
- **Job 登记表**：`Job.jobs` 只保留最近 6 个 job，更早的会被取消。这样可以限制浏览器界面的内存占用，因为那里的
  扫描是按 id 访问的。

## 3. 线程模型

| 位置 | 在界面线程之外运行的工作 | 结果如何返回 |
|---|---|---|
| engine | 每个 `Job` 在自己的守护线程中扫描；`iter_records` 另有一个解压预取线程（zstd 解压时会释放 GIL） | 前端轮询 `job.status()`。通过 `job.cancelled = True` 协作式取消。 |
| GUI | `run_bg(fn, *args, done=..., fail=...)`（位于 `gui/common.py`）在 `QThreadPool.globalInstance()` 上运行 `fn`。用于打开文件（`FileInfo.get`）、图表数据、订单簿重建、IV 曲面、CSV 导出和远程目录列表。 | `done` / `fail` 是 Qt 信号，所以回调在 GUI 线程上执行。一个 `QTimer` 每 200 ms 轮询一次扫描。 |
| TUI | Textual worker：`@work(thread=True, exclusive=True, group=...)`，用于载入文件、图表、订单簿、IV 和导出 | `self.call_from_thread(...)` 更新界面组件。`set_interval(0.25, poll)` 轮询扫描。 |
| web | `ThreadingHTTPServer` 在单独的线程中处理每个请求 | 页面轮询 `/api/job`，并通过 `/api/rows` 分页获取行 |

保证线程安全的规则：

- Qt 或 Textual 不会在工作线程中操作引擎和分析对象。工作线程只返回普通数据。
- `Job` 在追加数据段时持有锁。读取方（`rows`、`iter_instrument`、`options.snapshot`）在同一把锁下复制数据段列表，
  之后不再持锁。
- 用户可能中途换掉的耗时计算会检查令牌或回调（`options.surface` 的 `cancel=` 参数，以及 TUI 中
  `exclusive=True` 的 worker）。

## 4. 图表数据

`analysis/market.py` 把一个 `Job` 和一个 `instrument_id` 转换成普通 numpy 数组。时间是自 epoch 起的浮点秒数，
价格是实际数值，未定义值为 `NaN`。前端只负责绘制：GUI 用 pyqtgraph，TUI 用 plotext，浏览器界面只画价格线。

| 函数 | 返回 |
|---|---|
| `inst_records(job, iid)` | 该品种的主要记录类，按时间排序（`ts_recv`；OHLCV 用 `ts_event`） |
| `capabilities(job, iid)` | 可以绘制哪些图表：`bars`、`quotes`、`flow`、`heatmap` |
| `bars(job, iid, interval, source)` | OHLCV K 线：原生 K 线（周期更粗时重新合并）、由成交聚合并附主动买卖量，或由报价中间价聚合 |
| `quotes(job, iid)` | 买价、卖价、中间价、价差、盘口失衡，以及叠加的成交（抽稀到 `maxpts` 个点） |
| `flow(job, iid)` | 成交点、每根 K 线的主动买卖量、CVD、成交量分布、VWAP |
| `heatmap(job, iid)` | 时间 × 价格网格上的买卖挂单量、最优买卖价、成交 |
| `price_series(job, iid)` | 每个价格字段随时间的变化，按最小/最大值降采样到约 `maxpts` 个点 |
| `pick_interval(span_s, max_bars)` | 使 K 线数量不超过 `max_bars` 的最小标准周期（1s … 1W） |

这些函数只能看到扫描已载入的行，看不到整个文件。

`analysis/indicators.py` 在更上一层工作，输入是 `bars()` 返回的 K 线字典：

- 提供纯 numpy 实现的 `sma`、`ema`、`bollinger`、`vwap`、`rsi`、`macd`、`atr` 和 `stochastic`。历史数据不足时
  输出 `NaN`。
- `INDICATORS` 为前端描述每个指标：`kind` 为 `overlay`（叠加在价格图上）或 `pane`（单独的振荡指标副图），
  另有默认参数 `params`、带颜色角色的输出线 `lines`，以及参考线 `levels`。
- `compute(key, bars, params)` 返回输出线，`label(key, params)` 返回显示名称。
- GUI 和 TUI 只负责绘制这些线。

## 5. MBO 订单簿

`analysis/book.py` 中只有一个 `OrderBook` 类：

- 它保存 L3 订单（`order_id → side, price, size`），并增量维护 L2 价位（`price → 数量, 挂单笔数`）。
- 它处理 `A`（新增）、`M`（修改；未知订单视为新增）、`C`（部分或全部撤单）和 `R`（清簿）。
- `T`、`F` 和 `N` 不改变订单簿。
- 带 TOB 标志的消息会替换该方向的最优价位。

同一个类服务于两个功能：

- `book_at(job, row, depth)` 重放该品种直到 `row` 为止的所有已载入 MBO 记录。详情面板、TUI 的 `b` 键和
  `/api/book` 都使用它。返回结果包含：
  - `safe`，来自 `Filter.book_safe`：如果起始时间、action/side、`where` 或 rtype 筛选可能漏掉更早的消息，则为 false
  - `had_clear`：表示是否遇到过清簿（`R`）
- `market.heatmap()` 通过 `_mbo_snapshots()` 重放 MBO，并在每个时间分箱的边界上采样前 40 档。

## 6. 期权处理流程

`analysis/options.py` 供 GUI 的 IV 曲面标签页和 TUI 的 IV 标签页使用：

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

流程说明：

1. `chain()` 从 `SymbolMap` 的 OSI 代码中解析出每个 instrument_id 的标的、到期日、C/P 和行权价。
   `is_option_data()` 要求前 200 个品种中至少一半能解析为 OSI 代码。
2. `surface()` 先取快照：如果已载入的行覆盖了所选时间，就直接使用这些行；否则从文件开头重新读取到该时间。
3. 然后取中间价（双边报价时）或最新成交价，计算到期时间和折现因子，用买卖权平价推算各到期日的远期价格，
   按条件筛选报价，最后用向量化 Black-76 二分法计算隐含波动率和 call delta。
4. `grid()` 为 3D 曲面和热图生成规则网格，`term_at()` 计算固定 x 处各到期日的 IV。

`ncdf`（Abramowitz–Stegun 正态分布函数）和 `black76` 都用 numpy 实现，所以不需要 SciPy。

## 7. 前端

| | 桌面（`gui/`） | 终端（`tui/`） | 浏览器（`web/`） |
|---|---|---|---|
| 入口 | `dbnview.gui.app:main` | `dbnview.tui.app:main` | `dbnview.web.server:main` |
| 表格 | `QTableView` + `RecordModel`，按需读取行 | `RecordTable`（`ScrollView`），按需渲染行 | `/api/rows` 分页 |
| 图表 | 全部五种图表 + 技术指标（pyqtgraph） | K 线（+ 一个指标）/ 报价 / 订单流（plotext） | 价格线 |
| IV 曲面 | 完整功能（3D、热图、波动率微笑、期限结构、CSV） | IV 表格 + 平值期限结构 | — |
| 远程文件 | ssh 对话框、`ssh://` 参数 | `ssh://` 参数、文件选择器 | 服务器上的本地路径 |
| 语言 | 7 种 | 7 种 | 目前只有繁体中文 |

桌面应用的共享状态保存在 `MainWindow` 上：

- `fi` / `meta`：当前打开的文件
- `job` / `status`：扫描
- `stats`
- `tsfmt`：时间格式和时区
- `colors`、`settings`

各面板通过 `win` 拿到窗口，并从中读取这些状态。面板之间通过 Qt 信号通信（`rowSelected`、`scanRequested`、
`filterRequested`、`chartRequested`）。

浏览器 API（`web/server.py`）：

- `GET /api/{init,ls,meta,symbols,job,cancel,rows,seek,chart,raw,book}`
- `POST /api/scan`
- `GET /api/export`，以流的方式返回 CSV

每个请求都必须带上令牌：可以是查询参数、`X-Token` 请求头或 `dbnview` cookie。
