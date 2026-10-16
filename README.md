# dbnview

Databento DBN 檔（`.dbn` / `.dbn.zst`）的 **macOS 桌面 viewer**。直接串流解 zstd，不需轉檔，也不需要裝 databento。
介面支援 7 種語言：繁體中文、简体中文、English、日本語、Deutsch、한국어、Español（選單「語言 / Language」，預設跟隨系統）。

## 安裝 / 啟動

- **從原始碼執行**：

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/app.py ~/Downloads/file.dbn.zst
```

- **打包成 macOS App**：

```bash
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller --noconfirm packaging/dbnview.spec
xattr -cr dist/dbnview.app && codesign -s - --force --deep dist/dbnview.app
```

  把 `dist/dbnview.app` 拖到「應用程式」，雙擊開啟。也可以在 Finder 對 `.dbn.zst` 按右鍵 →「打開方式」→ dbnview，或直接把檔案拖進視窗。
  （自行建置、未經公證：第一次開啟若被擋，在 Finder 對 app 按右鍵 →「打開」。）
- **只要瀏覽器版**（伺服器上很方便，只需 `numpy` + `zstandard`）：`python dbnview.py /data/databento`，再用 `ssh -L 8765:localhost:8765` 轉發。

## 遠端檔案（ssh）

「檔案 → 開啟遠端檔案（ssh）…」（⇧⌘O）：選 `~/.ssh/config` 裡的主機，瀏覽目錄後雙擊檔案。
資料用 `ssh host cat file` 串流進來、在本機解碼，伺服器上不用裝任何東西。使用你現有的金鑰（BatchMode，不會跳出密碼）。
前面幾十萬列幾秒內就出現；要看整個 28 GB 檔案的後段，建議加上時間篩選（只保留需要的列，但仍需從頭串流）。

## 功能

- **表格**：可捲動上百萬列；價格自動 ÷1e9、時間可切時區（ET/CT/UTC/London/HKT/JST）與格式、side/action 上色、flags 解碼；
  跳到指定時間、右鍵欄位標題可顯示／隱藏欄位、匯出 CSV（⌘E）。
- **篩選**：symbol（輸入時自動完成；選建議 = 精確，直接 Enter = 子字串）、instrument_id、時間區間、action/side、
  `where` 運算式（如 `size >= 10 and side == 'B'`、`ask_px_00 - bid_px_00 <= 0.05`）。
- **明細面板**（⌘I）：全部欄位、MBP/CBBO/CMBP 的買賣盤、MBO「重建此刻的訂單簿」、原始位元組 hex（欄位上色）＋ byte layout。
- **圖表**（十字游標即時讀值，可縮放平移）：
  - **K 線**：ohlcv 直接畫；trades / tbbo / mbp / cmbp / mbo 依週期（1s～1W）由成交聚合，報價資料用 mid 聚合；附成交量、主動買賣量、CVD、價格成交量分布、VWAP。
  - **報價**：bid/ask 階梯線與 spread 帶、mid、spread、盤口量失衡，疊加成交泡泡。
  - **訂單流**：成交泡泡（大小＝量、顏色＝主動方）、每根主動買／賣量、CVD、價格成交量分布。
  - **訂單簿熱圖**：mbp-10 直接取檔位；MBO 重建訂單簿逐格取樣；綠＝買方掛單、紅＝賣方掛單，疊最優價與成交。
  - **價格線**：原始價格欄位＋每分鐘筆數。
- **IV 曲面**（期權資料，自動偵測 OPRA 代碼）：選時間點（滑桿）取各合約最後報價（cbbo/cmbp/tcbbo/bbo 用 mid，trades/ohlcv 用成交價）；
  每個到期日用 put-call parity 推 forward，Black-76 求 IV（也可手填標的價）。3D 曲面＋熱圖；勾選到期日看 smile 截面（含 bid/ask IV 區間），
  輸入 ln(K/F)／履約價／delta 看期限結構；點熱圖直接選截面。可篩最大價差、最短到期、報價年齡，匯出 CSV。
  已載入的列不涵蓋所選時間時，會自動從檔案開頭串流到該時間取快照。
- **統計**：rtype/action/side 分布、前 200 大商品（點「篩選」「圖表」直接跳轉）。
- **格式說明**：這個 schema 每一列代表什麼、record 的 byte layout、metadata header 的實際值與 offset、列舉值、常見陷阱。
  欄位標題滑過也有說明。

## 正確性與效能

- 支援 DBN v1/v2/v3（依檔頭自動切換 layout，layout 取自官方 `databento_dbn`；已對照 databento.com/docs 與 dbn 原始碼稽核所有 schema）。
  v4（尚未正式發布）會明確拒絕。整數「未定義」哨兵值顯示為 —；status/statistics/definition 的代碼直接顯示官方意義。
- 已用實際檔案測過：OPRA cbbo-1m / cmbp-1 / tcbbo / trades / ohlcv-1m / definition、CME MBO / ohlcv-1m、XNAS MBO。
- 已與官方 `databento` 解碼逐欄位比對：CME MBO（v3）、OPRA cbbo-1m（v1）全檔、OPRA cmbp-1（v1）前 300 萬筆，完全一致。
- zstd 只能從頭解。預設載入 100 萬列後停止；勾「掃完整檔」會繼續掃以取得完整統計。約 5–6 M records/s；28 GB 的 OPRA SPY cmbp-1 單日檔整檔約 3.5 分鐘。

## 結構

| 檔案 | 用途 |
|---|---|
| `src/core.py` | 解碼引擎：DBN header/record 解析、zstd 串流、ssh 來源、篩選、掃描、訂單簿重建 |
| `src/app.py` | PySide6 桌面介面 |
| `src/charts.py`, `src/analytics.py` | 圖表（K 線／報價／訂單流／熱圖）與其資料計算 |
| `src/ivsurface.py`, `src/options.py` | IV 曲面介面；OSI 代碼解析、快照、parity forward、Black-76 IV |
| `src/enum_values.py` | 官方列舉代碼意義（英文） |
| `src/i18n.py`, `src/ui_strings.py` | 介面文字與 7 種語言翻譯 |
| `src/docs.py`, `src/locales/*.py` | 欄位／schema／列舉說明（7 種語言） |
| `src/spec.json` | 各 DBN 版本的 record layout |
| `packaging/` | App 圖示與 PyInstaller 設定 |
| `src/gestures.py` | 觸控板捏合縮放、3D 視角 |
| `dbnview.py`, `src/ui.html`, `build.py` | 先前的瀏覽器版（單一檔案，適合直接在伺服器上跑） |
