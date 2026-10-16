[English](../en/development.md) · [README](../../README.zh-CN.md)

# DBNView 开发指南

本指南介绍如何搭建开发环境、运行和测试 DBNView、添加翻译和记录类型，以及如何打包和发布。代码的组织方式见
[architecture.md](architecture.md)。

## 1. 环境搭建

```bash
git clone https://github.com/chester1uo/DBNView.git
cd DBNView
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip install -e ".[dev]"
```

`dev` 依赖组会安装两个前端，以及 `pytest`、`pyflakes` 和 `pyinstaller`。

这是可编辑安装，所以对 `src/dbnview/` 的修改在下次运行时就会生效，包括包数据文件 `engine/spec.json` 和
`web/static/ui.html`。

在 Windows 上，请把下面所有命令中的 `.venv/bin/` 换成 `.venv\Scripts\`。

不要提交行情数据：`.gitignore` 已排除 `*.dbn`、`*.zst` 和 `*.parquet`。

## 2. 从源码运行

```bash
.venv/bin/python -m dbnview path/to/file.dbn.zst          # desktop app
.venv/bin/python -m dbnview.tui path/to/dir               # terminal UI
.venv/bin/python -m dbnview.web path/to/dir --open        # browser UI
.venv/bin/python -m dbnview.web file.dbn.zst --head 20    # print the first 20 records and exit
```

上面四行依次是：桌面应用、终端界面、浏览器界面，以及打印前 20 条记录后退出。安装后的命令 `dbnview`、
`dbnview-tui` 和 `dbnview-web` 作用相同。

桌面应用用 `QSettings("dbnview", "dbnview")` 保存设置：语言、时区和时间格式、最近打开的文件、隐藏的列、
窗口布局、上次使用的远程主机和目录，以及图表指标。

**截图自检。** 设置 `DBNVIEW_SELFTEST` 后，桌面应用会等扫描结束，把每个标签页渲染为 `PREFIX_<n>.png`，然后退出。
如果文件包含期权，还会计算 IV 曲面。

```bash
DBNVIEW_SELFTEST=/tmp/dbnview_shot .venv/bin/python -m dbnview path/to/file.dbn.zst
```

## 3. 测试

```bash
.venv/bin/python -m pytest              # whole suite
.venv/bin/python -m pytest -x -k mbo    # stop at first failure, only tests matching "mbo"
```

第一行运行全部测试；第二行只运行名称匹配“mbo”的测试，并在第一次失败时停止。

测试不需要行情数据。`tests/dbn_writer.py` 按 `engine/spec.json` 中的布局生成小型合成 DBN 文件（v1–v3，
可以不压缩或用 zstd 压缩）。`tests/conftest.py` 中的 fixture 会在临时目录中生成 MBO、成交和期权文件。

| 文件 | 覆盖内容 |
|---|---|
| `test_engine.py` | 元数据往返、解码、拒绝 v4、筛选、时间筛选和跳转、行数上限、原始字节布局、统计 |
| `test_analysis.py` | MBO 订单簿重放、K 线、热图、价格序列、OSI 解析、Black-76 IV 往返、曲面和远期价格还原 |
| `test_indicators.py` | SMA/EMA、布林带、VWAP、RSI、MACD、ATR、随机指标、指标注册表 |
| `test_i18n.py` | 每个 `T("…")` 字面量都有完整翻译且占位符一致；reference 各语言文件使用相同的键 |
| `test_frontends.py` | web API、无界面 TUI、离屏 GUI。缺少对应的可选依赖时会跳过。 |

GUI 测试会设置 `QT_QPA_PLATFORM=offscreen`，所以不需要显示器。在 Linux CI 上仍然需要 Qt 系统库。

## 4. 代码检查

```bash
.venv/bin/python -m pyflakes src
```

没有输出就表示代码干净。提交前请保持这种状态。CI 还会检查测试代码：`python -m pyflakes src tests`。

## 5. 编码规则

- **依赖规则**：`engine/`、`analysis/`、`reference/`、`i18n/` 和 `display.py` 不得导入 Qt 或 Textual
  （见 [architecture.md](architecture.md#11-依赖规则)）。共享逻辑放在这些包里，前端保持轻量。
- **不要阻塞界面线程**：凡是读取文件、网络或大量行的操作都在后台运行。
  - GUI：使用 `gui/common.py` 中的 `run_bg(fn, *args, done=..., fail=...)`。
  - TUI：使用 `@work(thread=True)` 加 `call_from_thread`。
- **扫描状态**：前端通过 `job.status()` 和 `job.rows()` 读取，不直接访问 numpy 数据段。例外是 `analysis.*` 中的
  函数，它们接收 `Job` 对象。
- **需要翻译的文字**：所有用户可见的文字都要经过 `T()`。字段和枚举的说明来自 `reference`。

## 6. 翻译

桌面应用和终端界面支持 7 种语言：

| 代码 | 语言 |
|---|---|
| `zh_Hant` | 繁体中文 |
| `zh_Hans` | 简体中文 |
| `en` | 英语 |
| `ja` | 日语 |
| `de` | 德语 |
| `ko` | 韩语 |
| `es` | 西班牙语 |

### 6.1 添加界面文字

1. 在使用的地方用 `T(...)` 包住文字：

   ```python
   from ..i18n import T

   go = QtWidgets.QPushButton(T("IV 曲面"))
   ```

   键就是源字符串本身。现有的键是原始的（中文）界面文字。如果找不到对应条目，`T()` 会原样返回键，所以缺少翻译
   时会显示未翻译的文字，而不是报错。

2. 在 `src/dbnview/i18n/strings.py` 中添加一个包含**全部 7 种语言**的条目：

   ```python
   STRINGS = {
       # ...
       'IV 曲面': {'zh_Hant': 'IV 曲面', 'zh_Hans': 'IV 曲面', 'en': 'IV Surface', 'ja': 'IV サーフェス',
                   'de': 'IV-Fläche', 'ko': 'IV 곡면', 'es': 'Superficie de IV'},
   }
   ```

3. 运行 `pytest tests/test_i18n.py`。以下三种情况会导致测试失败：
   - 某个 `T("…")` 字面量没有对应条目
   - 某个条目缺少一种语言
   - 某个翻译的占位符（`%s`、`%d`、`%.1f`、`{name}`）与键不一致

提示：

- 键首尾的空格也是键的一部分。
- 快捷键提示用 macOS 符号书写（⌘、⇧⌘）。在 GUI 中，把结果交给 `native_shortcuts()`，它会在 Windows 和 Linux
  上把这些符号转换为 `Ctrl+` / `Ctrl+Shift+`。
- 翻译是按字面量键查找的，所以不要把已经格式化过的文字传给 `T()`。占位符应保留在键里，翻译后再格式化：
  `T(key) % n`。

### 6.2 字段、schema 和枚举说明

列标题提示、详情面板和格式说明中显示的说明文字位于 `src/dbnview/reference/`。

- `locales/<code>.py`（每种语言一个文件）分别定义：
  - `FIELD_DOC`：字段名 → 说明
  - `LEVEL`：用来生成 `bid_px_00` … `ask_ct_09` 说明的模板
  - `RESERVED`：填充字段的说明
  - `SCHEMA_DOC`：schema → 每一行的含义
  - `STYPE_DOC`：symbology 类型 → 说明
  - `ENUMS`：action、side、flags、`stat_type` 和哨兵值的表
  - `TIPS`：“常见陷阱”列表
- **所有语言文件使用相同的键。** `test_i18n.py` 会检查各语言的 `FIELD_DOC`、`SCHEMA_DOC` 和 `ENUMS` 表是否一致。
- `enums.py` 中的 `ENUM_VALUES[(记录类, 字段)] = {代码: 含义}` 是来自 databento.com/docs 的官方英文含义，
  用于 status、statistics 和 definition 的代码。这部分不翻译。

要为新字段添加说明，需要在**每一个** `locales/*.py` 文件的 `FIELD_DOC` 中加上它的键。先写 `en.py`，再翻译。

要添加第 8 种语言：

1. 新建 `locales/<code>.py`，定义相同的名称和键。
2. 在 `i18n/__init__.py` 的 `LANGS` 中加入 `(代码, 语言自称)`。
3. 在 `strings.py` 的每个条目中加入该语言代码。
4. 让 `system_lang()` 能识别这个代码。

## 7. 支持新的记录类型

1. **布局**：在 `src/dbnview/engine/spec.json` 的 `versions → "1" / "2" / "3"` 下，为包含该记录类的每个 DBN
   版本添加定义。

   ```json
   "NewMsg": {
     "f":   [["length", "u1"], ["rtype", "u1"], ["publisher_id", "u2"], ["instrument_id", "u4"],
             ["ts_event", "u8"], ["price", "i8"], ["size", "u4"], ["_reserved", "S4"], ["ts_recv", "u8"]],
     "px":  ["price"],
     "ts":  ["ts_event", "ts_recv"],
     "ord": ["ts_recv", "ts_event", "rtype", "publisher_id", "instrument_id", "price", "size"]
   }
   ```

   - `f`：按字节顺序列出所有字段及其 numpy 类型，包括保留字段和填充字段，使 dtype 的大小等于记录长度。
   - `px`：定点价格字段（÷ 1e9）。
   - `ts`：纳秒时间戳。
   - `ord`：显示顺序。
   - 定义请取自官方 `databento_dbn` 源码，现有布局也来自那里。
   - 如果 dtype 比文件中的记录长度还大，`RecordType` 会退回只解析 16 字节的公共头。

2. **rtype**：在 `src/dbnview/engine/constants.py` 的 `RTYPES` 中加入 `rtype: ("NewMsg", "display-name")`。
   - 如果该记录类用整数最大值表示“未定义”，把它加入 `NULL_MAX_CLASSES`。
   - 如果是新的 schema，把它追加到 `SCHEMAS` 中。列表下标就是元数据头中保存的 schema id，所以顺序很重要。

3. **说明文字**：
   - 在 `reference/__init__.py` 的 `RTYPE_DOC` 中加入 `(rtype, 名称)`。
   - 在每个语言文件的 `SCHEMA_DOC` 中加入该 schema，在 `FIELD_DOC` 中加入新字段。
   - 把官方枚举含义加入 `enums.py`。

4. **图表**（可选）：如果记录包含成交、报价或 K 线，把记录类加入 `analysis/market.py` 中的 `TRADE_CLASSES`、
   `QUOTE_CLASSES` 或 `BAR_CLASSES`。

5. **测试**：
   - 在 `tests/dbn_writer.py` 的 `CLASS_RTYPE` 中加入该类。
   - 在 fixture 中生成一个合成文件，并断言解码值、筛选和 `job.raw()` 的布局都正确。
   - 如果条件允许，再用真实文件与官方 `databento` 解码器比对。

## 8. 打包

### 8.1 桌面应用（PyInstaller）

PyInstaller 不能交叉编译，所以要在每个目标操作系统上分别构建，并预先安装 `dev` 依赖组：

```bash
.venv/bin/pyinstaller --noconfirm packaging/dbnview.spec
```

| 操作系统 | 产物 | 说明 |
|---|---|---|
| macOS | `dist/DBNView.app` | 构建后进行 ad-hoc 签名（命令见下）。它会注册为 `.dbn` / `.zst` 文件的查看器。 |
| Windows | `dist/DBNView/DBNView.exe` | 发布整个 `dist/DBNView/` 文件夹。运行时没有控制台窗口。 |
| Linux | `dist/DBNView/DBNView` | 发布整个文件夹。目标机器需要 Qt xcb 库。 |

在 macOS 上，构建后进行签名：

```bash
xattr -cr dist/DBNView.app && codesign -s - --force --deep dist/DBNView.app
```

ad-hoc 签名足够在自己的机器上使用。要分发给他人而不触发 Gatekeeper 警告，需要 Developer ID 证书和公证，
目前尚未配置。

关于 `packaging/dbnview.spec`：

- 入口脚本是 `packaging/launcher.py`。
- 它会打包 `dbnview` 的包数据（`spec.json`、`ui.html`）和 pyqtgraph 的数据文件。
- 它排除了 `textual`、`plotext` 和用不到的 Qt 模块，所以打包产物只包含桌面前端。
- 图标 `packaging/dbnview.icns`（macOS）、`packaging/dbnview.ico`（Windows）和 `packaging/icon.png`（Linux）由
  `packaging/make_icon.py` 绘制。生成 `.icns` 需要 macOS 的 `iconutil`。

用自检功能对打包产物做冒烟测试：

```bash
DBNVIEW_SELFTEST=/tmp/shot dist/DBNView.app/Contents/MacOS/DBNView path/to/file.dbn.zst   # macOS
DBNVIEW_SELFTEST=/tmp/shot dist/DBNView/DBNView path/to/file.dbn.zst                      # Linux
```

然后检查它写出的 PNG 图片。

### 8.2 服务器用的单文件浏览器界面

```bash
python tools/build_web_pyz.py            # writes dist/dbnview-web.pyz
```

这个 zipapp 包含 `gui/` 和 `tui/` 以外的所有内容。在任何装有 Python 3.9+、`numpy` 和 `zstandard` 的机器上，
都可以用 `python3 dbnview-web.pyz /data` 运行。

### 8.3 Python 包

```bash
.venv/bin/pip wheel . --no-deps -w dist
```

版本号来自 `dbnview.__version__`（`src/dbnview/__init__.py`）。`pyproject.toml` 声明了包数据
（`engine/spec.json`、`web/static/*.html`）。

## 9. 持续集成

`.github/workflows/ci.yml` 在每次 push 和 pull request 时于 GitHub Actions 上运行，包含两个 job：

- **test**：在 Ubuntu、macOS 和 Windows 上分别用 Python 3.9 和 3.12 安装 `.[all]`，运行
  `python -m pyflakes src tests` 和 `python -m pytest -q`。Qt 以离屏模式运行，Linux runner 会先安装 Qt 系统库。
- **package**：测试通过后，在每个操作系统上用 PyInstaller 构建桌面应用。它把 `DBNView-macOS.zip`（已 ad-hoc 签名）、
  `DBNView-Windows.zip` 和 `DBNView-Linux.tar.gz` 作为 workflow artifact 上传；Linux job 还会上传
  `dist/dbnview-web.pyz`。可以在该次运行的页面上下载。

## 10. 发布检查清单

1. 修改 `src/dbnview/__init__.py` 中的 `__version__`。版本号只保存在这一个地方。
2. `python -m pyflakes src` 没有任何输出，`pytest` 全部通过（包括检查新文字的 `test_i18n.py`）。
3. 打开几类主要的真实文件：
   - CME MBO 和 MBP-10、OPRA cbbo-1m / cmbp-1，以及一个 OHLCV 文件
   - 一个通过 ssh 读取的文件
   - 检查表格、详情和订单簿、每种图表类型、IV 曲面和 CSV 导出
4. 在同样的文件上各运行一次终端界面和浏览器界面。
5. 在 macOS、Windows 和 Linux 上构建桌面应用（或使用 CI 产物），并在每个平台上运行 `DBNVIEW_SELFTEST` 冒烟测试。
   在 macOS 上确认右键 → **打开** 和 **打开方式** 都能正常使用。
6. 构建 `dist/dbnview-web.pyz`，并在服务器上通过 ssh 隧道启动它。
7. 同时更新 `README.md` / `README.zh-CN.md` 和 `docs/en/` / `docs/zh-CN/`。两种语言的文档逐节对应。
8. 提交，打上 `vX.Y.Z` 标签并推送，然后把桌面应用构建产物和 `dbnview-web.pyz` 附加到 GitHub release。
