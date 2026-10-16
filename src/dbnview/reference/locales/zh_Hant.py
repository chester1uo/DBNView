"""Traditional Chinese (Taiwan) documentation strings for dbnview."""

FIELD_DOC = {
    "length": "紀錄長度，以 4 bytes 為單位（實際位元組 = length × 4）。解碼器靠它跳到下一筆紀錄。",
    "rtype": "紀錄類型 (record type)，決定後面欄位的 layout，例如 0xA0 = MBO、0xB1 = CMBP-1。",
    "publisher_id": "資料來源編號 = dataset + 交易所 (venue)，例如 30 = OPRA.PILLAR.OPRA、1 = GLBX.MDP3.GLBX。",
    "instrument_id": "交易所／Databento 指派的商品數字 ID。要對回 symbol 需查 metadata 的 symbology mappings（依日期而定）。",
    "ts_event": "交易所撮合引擎的事件時間，UNIX epoch 奈秒 (UTC)。cbbo/bbo 取樣 schema 中是「最近一筆成交」的時間，"
                "沒有成交時為未定義；ohlcv 中是 K 棒開始時間。",
    "ts_recv": "Databento 擷取伺服器收到訊息的時間，UNIX epoch 奈秒 (UTC)。是 Databento 的主索引時間，檔案依它排序。"
               "-1s / -1m 取樣 schema 中為對齊到秒／分鐘的取樣時間點。",
    "ts_in_delta": "交易所送出時間比 ts_recv 早多少奈秒（ts_recv − 交易所 sending time）。",
    "ts_out": "Databento 閘道送出時間（只有 live 資料且開啟 ts_out 時才會附加在每筆紀錄最後 8 bytes）。",
    "sequence": "交易所訊息序號 (venue sequence number)，可用來檢查缺包。",
    "price": "價格，定點數：實際值 = 整數 ÷ 1e9。INT64_MAX (9223372036854775807) 表示未定義。MBO = 委託價；"
             "trades/tbbo = 成交價；mbp = 該事件價格；cbbo/bbo = 最近一筆成交價。",
    "size": "數量（股數／合約數）。MBO = 該事件的委託量；取消 (C) 時是被取消的量。",
    "action": "事件類型：A 新增、C 取消、M 修改、R 清空訂單簿、T 成交、F 成交回報 (fill)、N 無。",
    "side": "B = 買方／bid、A = 賣方／ask、N = 無。成交 (T) 時表示主動方 (aggressor)：B = 主動買。",
    "flags": "位元旗標：128 LAST（同一事件的最後一筆）、64 TOB（top-of-book 訊息）、32 SNAPSHOT（來自快照）、"
             "16 MBP（由聚合價位合成）、8 BAD_TS_RECV、4 MAYBE_BAD_BOOK（可能有缺包）、2 PUBLISHER_SPECIFIC。",
    "depth": "此事件影響的簿深度層級（0 = 最優價）。",
    "order_id": "委託單 ID（交易所指派），同一張單的 A / M / C / F 共用此 ID。",
    "channel_id": "交易所 multicast 頻道 ID。",
    "open": "K 棒開盤價（定點 1e-9）。", "high": "K 棒最高價。", "low": "K 棒最低價。", "close": "K 棒收盤價。",
    "volume": "K 棒成交量。",
    "ts_ref": "統計值所指的參考時間（例如結算價對應的交易日）。",
    "quantity": "統計數量（例如未平倉量、成交量），整數最大值表示未定義。",
    "stat_type": "統計類型：1 開盤價、3 結算價、4/5 盤中低/高、6 清算成交量、9 未平倉量、11 收盤價…（見「格式說明」）。",
    "update_action": "1 = 新增、2 = 刪除（撤回先前公布的統計）。",
    "stat_flags": "交易所自訂的統計旗標。",
    "raw_symbol": "交易所原始代碼，例如 OPRA 的 \"SPY   260116C00690000\"（root 補空白到 6 字元 + YYMMDD + C/P + 履約價×1000 八位數）。",
    "expiration": "到期時間 (UNIX ns)。", "activation": "上市／開始交易時間 (UNIX ns)。",
    "strike_price": "履約價（定點 1e-9）。", "instrument_class": "商品類別：C 買權、P 賣權、F 期貨、K 股票、S 期貨價差…",
    "underlying": "標的代碼。", "underlying_id": "標的的 instrument_id。",
    "min_price_increment": "最小跳動價位 (tick size，定點 1e-9)。",
    "contract_multiplier": "合約乘數（例如美股期權 100）。", "display_factor": "顯示價格的乘數（定點 1e-9）。",
    "unit_of_measure_qty": "合約單位數量（定點 1e-9）。", "security_type": "證券類型，例如 OOF、FUT、OPT。",
    "asset": "資產代碼。", "currency": "計價幣別。", "exchange": "交易所 MIC。",
    "high_limit_price": "漲停價。", "low_limit_price": "跌停價。",
    "stype_in_symbol": "訂閱時使用的代碼（輸入 symbology）。", "stype_out_symbol": "對應到的輸出代碼（通常是 raw symbol）。",
    "start_ts": "此 mapping 生效開始時間。", "end_ts": "此 mapping 生效結束時間。",
    "msg": "系統訊息文字（heartbeat、訂閱確認…）。", "err": "錯誤訊息文字。", "code": "訊息代碼。",
    "is_last": "是否為最後一則錯誤訊息。",
    "is_trading": "是否可交易：Y / N / ~（未知）。", "is_quoting": "是否可報價：Y / N / ~。",
    "is_short_sell_restricted": "是否限制放空：Y / N / ~。",
    "reason": "狀態變更原因代碼。", "trading_event": "附加交易事件代碼。",
    "ref_price": "集合競價參考價。", "paired_qty": "已配對數量。", "total_imbalance_qty": "總失衡量。",
    "auction_type": "競價類型。",
    "_rec": "（viewer 加的）此筆在檔案中的序號，從 0 起算。",
    "symbol": "（viewer 加的）由 instrument_id 經 metadata mappings 查到的代碼。",
}

LEVEL = {
    "best": "最優（第 1 檔）",
    "nth": "第 {n} 檔",
    "bid": "買",
    "ask": "賣",
    "px": "{lvl}{side}價（定點 1e-9；未定義 = INT64_MAX）。",
    "sz": "{lvl}{side}方總量。",
    "ct": "{lvl}{side}方的委託筆數。",
    "pb": "{lvl}{side}價來自哪個交易所（publisher_id）。合併資料中用來看 NBBO 由誰提供。",
}

RESERVED = "保留／對齊用的填充位元組，沒有資料。"

SCHEMA_DOC = {
    "mbo": "逐筆委託 (Market by Order, L3)：每張委託單的新增／修改／取消／成交事件各一筆，可完整重建訂單簿。",
    "mbp-1": "最優一檔 (L1)：每個改變最優買賣價或產生成交的事件一筆，附帶事件「之後」的最優買賣價量。",
    "mbp-10": "前 10 檔 (L2)：每個簿變動事件一筆，附帶事件之後的 10 檔買賣價量與委託筆數。",
    "tbbo": "成交 + 成交「之前」的最優買賣 (trades with BBO)：每筆成交一列。",
    "trades": "逐筆成交：每筆成交一列。",
    "ohlcv-1s": "每秒 K 棒；只有該區間有成交才有紀錄，ts_event 是區間開始時間。",
    "ohlcv-1m": "每分鐘 K 棒；只有該區間有成交才有紀錄，ts_event 是區間開始時間。",
    "ohlcv-1h": "每小時 K 棒。", "ohlcv-1d": "日 K 棒（UTC 日界）。", "ohlcv-eod": "以交易所收盤為界的日 K。",
    "definition": "商品定義：到期日、履約價、乘數、tick size、標的…（OPRA 期權很適合用來解析合約規格）。",
    "statistics": "交易所公布的統計：開／收盤價、結算價、未平倉量、成交量…，看 stat_type 分辨。",
    "status": "交易狀態變化：暫停、恢復、開盤、收盤、放空限制等。", "imbalance": "集合競價的買賣失衡資訊。",
    "cmbp-1": "跨交易所合併的 L1 (consolidated MBP-1)：任一交易所報價變動就一筆，附帶合併後的 NBBO，"
              "以及提供最優價的交易所 (bid_pb / ask_pb)。資料量非常大。",
    "cbbo-1s": "每秒取樣的合併 NBBO：只有該秒有報價更新的商品才有紀錄（需要 forward-fill）。"
               "price / size / ts_event 是最近一筆成交，可能是很久以前的。",
    "cbbo-1m": "每分鐘取樣的合併 NBBO：只有該分鐘有報價更新的商品才有紀錄（需要 forward-fill）。"
               "price / size / ts_event 是最近一筆成交，可能是很久以前的，沒成交過就是未定義。",
    "tcbbo": "成交 + 成交之前的合併 NBBO：每筆成交一列。",
    "bbo-1s": "單一交易所的 L1 每秒取樣。", "bbo-1m": "單一交易所的 L1 每分鐘取樣。",
}

STYPE_DOC = {
    "instrument_id": "數字 instrument_id",
    "raw_symbol": "交易所原始代碼（例如 ESH4、SPY   260116C00690000）",
    "parent": "母代碼：一個代碼展開成整串合約，例如 QQQ.OPT = QQQ 全部期權、ES.FUT = ES 全部期貨",
    "continuous": "連續合約，例如 ES.v.0 = 依成交量排名第一的 ES 期貨、ES.c.0 = 依日曆最近月",
    "nasdaq_symbol": "Nasdaq 代碼", "cms_symbol": "CMS 代碼", "isin": "ISIN", "us_code": "CUSIP", "figi": "FIGI",
}

ENUMS = [
    ("action", [("A", "Add 新增委託／報價"), ("C", "Cancel 取消（部分或全部）"), ("M", "Modify 修改價或量"),
                ("R", "Clear 清空訂單簿（常見於快照開頭）"), ("T", "Trade 成交（主動方）"), ("F", "Fill 被動方成交回報"),
                ("N", "None 無動作（例如只更新 flags）")]),
    ("side", [("B", "Bid 買方"), ("A", "Ask 賣方"), ("N", "None（例如沒有方向的成交、取樣紀錄）")]),
    ("flags（位元）", [("128", "LAST：同一個交易所事件拆成多筆時，最後一筆才設；重建簿時應在 LAST 後才讀取狀態"),
                    ("64", "TOB：top-of-book 訊息（該價位整層取代）"), ("32", "SNAPSHOT：來自快照／重播"),
                    ("16", "MBP：由聚合價位資料合成"), ("8", "BAD_TS_RECV：ts_recv 不準"),
                    ("4", "MAYBE_BAD_BOOK：可能有缺包，簿可能錯"), ("2", "PUBLISHER_SPECIFIC：交易所自訂")]),
    ("stat_type", [("1", "開盤價"), ("2", "指示性開盤價"), ("3", "結算價"), ("4", "盤中最低價"), ("5", "盤中最高價"),
                   ("6", "清算成交量"), ("7", "最低賣價"), ("8", "最高買價"), ("9", "未平倉量 (open interest)"),
                   ("10", "定盤價 (fixing)"), ("11", "收盤價"), ("12", "漲跌"), ("13", "VWAP"), ("14", "波動率"),
                   ("15", "Delta")]),
    ("未定義值 (sentinel)", [("INT64_MAX", "價格未定義 9223372036854775807（顯示為 —）"),
                          ("UINT64_MAX", "時間戳未定義 18446744073709551615"),
                          ("UINT32_MAX", "數量未定義 4294967295")]),
]

TIPS = [
    "價格一律是整數 ÷ 1e9；9223372036854775807 代表「沒有值」，不能直接當價格算。",
    "時間都是 UTC 奈秒；美股盤中 09:30–16:00 ET = 14:30–21:00 UTC（夏令 13:30–20:00）。工具列可切時區。",
    "ts_recv 是檔案排序用的時間；ts_event 是交易所時間，可能亂序或未定義。",
    "MBO 的 T／F 不改變訂單簿，真正減量的是後續的 C／M；重建簿要等 flags 含 LAST 才算一個完整事件。",
    "OPRA 的 instrument_id 可能每天不同，跨日要用 symbol 對齊，不要用 id。",
    "-1s / -1m 取樣 schema 只在有更新時出現，要自己 forward-fill；price/size 是「最近一次成交」，不是該區間的成交。",
    "DBN v1 → v2 → v3：symbol 長度 22 → 71；InstrumentDef 360 → 400 → 520 bytes；StatMsg 的 quantity 在 v3 由 i32 "
    "改成 i64（64 → 80 bytes）。這個 viewer 依檔頭版本自動切換。",
    ".zst 是整條串流壓縮，不能隨機跳到中間；看檔案後段要從頭解（可用時間篩選，只保留需要的列）。",
]


# --- added after the docs audit: remaining stat_type codes and the corrected statistics sentinel
def _patch():
    extra = ['拍賣撮合價（非正式開/收盤）', '漲停價（盤中上限）', '跌停價（盤中下限）', '鉅額交易量', '指示性收盤價', '熔斷第 1 級門檻 (7%)', '熔斷第 2 級門檻 (13%)', '熔斷第 3 級門檻 (20%)', '競價區間參考價', '競價區間上限', '競價區間下限', '交易所自訂成交量 1', '交易所自訂價格 1']
    for title, rows in ENUMS:
        codes = [c for c, _ in rows]
        if "15" in codes and "16" not in codes:
            rows.extend((str(c), d) for c, d in zip([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 10001, 10002], extra))
        if "UINT32_MAX" in codes:
            i = codes.index("UINT32_MAX")
            rows[i] = ('INT32_MAX / INT64_MAX', 'statistics 的 quantity 未定義（v1/v2 為 INT32_MAX，v3 為 INT64_MAX）')


_patch()
