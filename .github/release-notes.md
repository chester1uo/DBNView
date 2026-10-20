## What's new / 更新内容

- **The downloadable builds now include the LOB-WASR replay engine** on macOS, Windows and Linux: MBO order book
  replay restores any moment of the day exactly (L3 queues included) in milliseconds; the first replay of a file
  indexes it (a few seconds). **下载版现已内置 LOB-WASR 回放引擎**（macOS、Windows、Linux）：MBO 订单簿回放可在毫秒级
  精确恢复当天任意时刻（含 L3 队列），每个文件第一次回放时建索引，约需数秒。
- **Replay chart legend**: best bid / ask lines; dots are trades only (MBO action T), green buyer-initiated, red
  seller-initiated, grey no aggressor (auctions). **回放图表图例**：最优买卖价线；圆点只表示成交（MBO action T），
  绿为买方主动、红为卖方主动、灰为无主动方（集合竞价）。
- 0.6.0: **MBO order book replay** (Tools → MBO Order Book Replay…, ⇧⌘R / Ctrl+Shift+R) with a depth ladder, per-order
  queues (L3), a bid/ask/trades chart and an event tape. **MBO 订单簿回放**（工具 → MBO 订单簿回放…）。
- **SSH connection profiles**: login, key or password, jump hosts / SOCKS5 / HTTP / custom proxy, log level and a
  connection test. **SSH 连接配置**：登录、密钥或密码、跳板机 / SOCKS5 / HTTP / 自定义代理、日志等级和连接测试。
- Startup splash with version and disclaimer; 3D IV view falls back to 2D when OpenGL is unavailable; UI translations
  keyed by English text. 启动画面；无 OpenGL 时 3D IV 曲面自动改用 2D；界面翻译改用英文键。

## Downloads / 下载

| Platform / 平台 | File / 文件 |
| --- | --- |
| macOS (Apple silicon) | `DBNView-*-macOS-arm64.dmg` |
| Windows 10/11 x64 | `DBNView-*-Windows-Setup.exe` (installer / 安装程序) or `*-Windows-x64-portable.zip` (no install / 免安装) |
| Linux x64 | `DBNView-*-Linux-x64.tar.gz` |
| Any OS, browser UI / 浏览器界面 | `dbnview-web-*.pyz`: `python3 dbnview-web-*.pyz DIR` on a server with `numpy` and `zstandard` |

`SHA256SUMS.txt` lists the checksums of every file.

### First launch / 首次打开

The builds are not signed with an Apple or Microsoft developer certificate, so the system warns on first launch.
安装包没有 Apple / Microsoft 开发者签名，第一次打开时系统会提示。

- **macOS**: open the DMG and drag DBNView to Applications. If macOS says the app "cannot be opened", right-click it
  and choose **Open**, or run `xattr -dr com.apple.quarantine /Applications/DBNView.app`.
  打开 DMG，把 DBNView 拖进“应用程序”。若提示无法打开，右键点 App 选“打开”，或运行上面的 `xattr` 命令。
- **Windows**: if SmartScreen shows "Windows protected your PC", click **More info → Run anyway**. The installer
  installs for the current user and does not need administrator rights.
  若 SmartScreen 提示“Windows 已保护你的电脑”，点“更多信息 → 仍要运行”。安装程序只为当前用户安装，不需要管理员权限。
- Intel Macs: install from a clone of this repository (see the README).
  Intel Mac 请按 README 从源码克隆安装。

### Disclaimer / 免责声明

For research and education only; not investment advice. DBNView is an independent project with no affiliation to
Databento, Inc.
仅供研究与教育用途，不构成投资建议。DBNView 为独立项目，与 Databento, Inc. 无任何关联。
