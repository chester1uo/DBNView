[English](README.md)

# DBNView

DBNView 是 [Databento](https://databento.com) DBN 行情数据文件（`.dbn` / `.dbn.zst`，DBN v1–v3）的查看器。
它直接解码 zstd 压缩流，无需转换文件，也不需要安装 `databento` SDK。解码引擎只依赖 `numpy` 和 `zstandard`。

同一个引擎驱动三个前端：

| 前端 | 命令 | 适用场景 |
|---|---|---|
| 桌面应用（PySide6） | `dbnview` | 在笔记本或工作站上交互使用 |
| 终端界面（Textual） | `dbnview-tui` | 没有图形界面的普通 ssh 会话 |
| 浏览器界面 | `dbnview-web` | 没有 Qt 的服务器，通过 ssh 隧道访问 |

支持 macOS、Windows 和 Linux，需要 Python 3.9 或更高版本。

## 快速开始

现成的安装包（macOS DMG、Windows 安装程序、Linux 压缩包）在 [Releases](https://github.com/chester1uo/DBNView/releases) 页面。

从克隆的仓库安装：

```bash
git clone https://github.com/chester1uo/DBNView.git
cd DBNView
python -m venv .venv
.venv/bin/pip install -e ".[gui,tui]"      # Windows: .venv\Scripts\pip install -e ".[gui,tui]"
```

可选依赖组有 `gui`（桌面应用）、`tui`（终端界面）、`all`（两者）和 `dev`（全部，外加 pytest、pyflakes 和
PyInstaller）。直接运行 `pip install -e .` 只会安装引擎和浏览器界面。

**桌面应用**：打开本地文件，或通过 ssh 以流的方式读取远程文件：

```bash
.venv/bin/dbnview ~/data/glbx-mdp3-20260102.mbo.dbn.zst
.venv/bin/dbnview ssh://myserver/data/databento/opra-20260102.cbbo-1m.dbn.zst
```

**终端界面**：打开一个文件、一个目录或一个 ssh 目录：

```bash
.venv/bin/dbnview-tui ~/data --tz America/New_York --lang en
```

按键：`o` 打开 · `s` 扫描 · `x` 停止 · `/` 筛选 · `f` 侧栏 · `enter` 详情 · `b` MBO 订单簿 · `c` 切换图表 ·
`i` 切换技术指标 · `t` 时区 · `1`–`6` 标签页 · `e` 导出 CSV · `q` 退出。

**浏览器界面**：在存放数据的机器上运行，再把端口转发到你的笔记本：

```bash
dbnview-web /data/databento                  # on the server; prints http://localhost:8765/?token=...
ssh -N -L 8765:localhost:8765 myserver       # on your laptop, then open the printed URL
```

第一行在服务器上运行，会输出带令牌的 URL；第二行在笔记本上运行，然后在本地浏览器中打开输出的 URL。

如果服务器上无法安装包，可以用 `python tools/build_web_pyz.py` 构建单文件版本。把
`dist/dbnview-web.pyz` 复制到服务器后，运行 `python dbnview-web.pyz /data`。

## 功能

- **表格**：可滚动浏览数百万行。价格换算为实际数值，时间戳可按多种时区显示，flags 和枚举代码会自动解码，
  还可以跳转到指定时间或导出为 CSV。
- **筛选**：symbol（子字符串匹配；选择建议项时为精确匹配）、instrument_id、时间范围、action/side，
  以及安全的 `where` 表达式，例如 `size >= 10 and side == 'B'`。
- **详情面板**：一行记录的全部字段、买卖盘档位、在该行时刻重建的 MBO 订单簿，以及十六进制原始字节和字节布局。
- **图表**：
  - K 线：可以是原生 K 线，也可以由成交或报价聚合，附主动买卖量、CVD、成交量分布和 VWAP
  - K 线上的技术指标：SMA、EMA、布林带、VWAP、RSI、MACD、ATR 和随机指标
  - 报价图：带价差带和盘口失衡
  - 订单流气泡图
  - 订单簿热图：来自 MBP-10，或来自重放的 MBO 订单簿
  - 价格线
- **统计与格式说明**：记录类型、action 和 side 的分布，以及最活跃的品种。格式说明介绍 schema 的含义、
  记录和元数据头的字节布局、枚举值含义和常见陷阱。
- **期权墙**：按行权价显示持仓量（来自 OPRA statistics）、成交量和做市商 Gamma 敞口，并标出 Call 墙、Put 墙、
  总 GEX 和 Gamma 翻转点（桌面版分页与终端界面第 7 页）。
- **股票＋期权联合分析**（工具 → 股票＋期权联合分析…，Ctrl/⌘+J）：独立子窗口，把标的文件和期权文件对齐到同一时间轴——
  股价叠加 parity 推出的隐含标的价与近月跨式预期波动区间、近月与约 30 天 ATM IV 对比实现波动率、偏斜、Call/Put 成交量与 P/C 比。
- **MBO 订单簿回放**（工具 → MBO 订单簿回放…，Ctrl/⌘+Shift+R）：播放或拖动回看一整天的 MBO 订单簿，包括档位、
  逐笔挂单队列（L3）、买卖价与成交图和事件流。安装 [LOB-WASR](https://github.com/chester1uo/LOB-WASR)
  （`pip install "dbnview[replay]"`）后，当天任意时刻都能在毫秒级精确恢复；未安装时回放已加载的行。
- **IV 曲面**（OPRA 期权）：在指定时刻取快照，用买卖权平价推算远期价格，再用 Black-76 计算隐含波动率。
  结果以 3D 曲面、热图、波动率微笑和期限结构截面显示，并可导出 CSV。
- **通过 ssh 读取远程文件**（`ssh host cat`，使用 `~/.ssh/config` 中的密钥）、拖放打开、触控板双指缩放。
- **7 种界面语言**：繁体中文、简体中文、英语、日语、德语、韩语和西班牙语。

**正确性**：解码器已在 CME MBO（v3）、OPRA cbbo-1m（v1）和 OPRA cmbp-1（v1）上与 Databento 官方解码器
逐字段比对。

**速度**：解码速度约为每秒 500–600 万条记录。

## 文档

- [用户指南](docs/zh-CN/user-guide.md)：安装、各前端、筛选、图表、IV 曲面、快捷键和故障排查
- [架构](docs/zh-CN/architecture.md)：包结构、数据流、线程模型、图表和期权的数据处理流程
- [开发指南](docs/zh-CN/development.md)：环境搭建、测试、翻译、新增记录类型、打包和发布

## 许可证

MIT
