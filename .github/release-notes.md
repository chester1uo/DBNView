## What's new / 更新内容

- **MBO order book replay** (Tools → MBO Order Book Replay…, ⇧⌘R / Ctrl+Shift+R): play back or scrub a whole MBO day
  with a depth ladder, per-order queues (L3), a bid/ask/trades chart and an event tape; step by event or by second,
  0.1×–1800× playback. Builds from source with [LOB-WASR](https://github.com/chester1uo/LOB-WASR) restore any moment
  exactly in milliseconds; the downloadable builds replay the rows loaded by the scan (queue order approximate).
  **MBO 订单簿回放**（工具 → MBO 订单簿回放…）：播放或拖动回看一整天的 MBO 订单簿，包括档位、逐笔挂单队列（L3）、
  买卖价与成交图和事件流，可逐事件或逐秒步进，0.1×–1800× 播放。从源码安装并装有 LOB-WASR 时，任意时刻毫秒级精确恢复；
  下载版回放扫描已加载的行（队列顺序为近似）。
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
