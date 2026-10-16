"""Simplified Chinese (mainland) documentation strings for dbnview."""

FIELD_DOC = {
    "length": "记录长度，以 4 bytes 为单位（实际字节数 = length × 4）。解码器靠它跳到下一条记录。",
    "rtype": "记录类型 (record type)，决定后面字段的布局，例如 0xA0 = MBO、0xB1 = CMBP-1。",
    "publisher_id": "数据来源编号 = dataset + 交易所 (venue)，例如 30 = OPRA.PILLAR.OPRA、1 = GLBX.MDP3.GLBX。",
    "instrument_id": "交易所／Databento 分配的品种数字 ID。要映射回 symbol 需查 metadata 的 symbology mappings（随日期而定）。",
    "ts_event": "交易所撮合引擎的事件时间，UNIX epoch 纳秒 (UTC)。cbbo/bbo 采样 schema 中是「最近一笔成交」的时间，"
                "没有成交时为未定义；ohlcv 中是 K 线开始时间。",
    "ts_recv": "Databento 采集服务器收到消息的时间，UNIX epoch 纳秒 (UTC)。是 Databento 的主索引时间，文件按它排序。"
               "-1s / -1m 采样 schema 中为对齐到秒／分钟的采样时间点。",
    "ts_in_delta": "交易所发送时间比 ts_recv 早多少纳秒（ts_recv − 交易所 sending time）。",
    "ts_out": "Databento 网关发送时间（只有 live 数据且开启 ts_out 时才会附加在每条记录最后 8 bytes）。",
    "sequence": "交易所消息序号 (venue sequence number)，可用来检查丢包。",
    "price": "价格，定点数：实际值 = 整数 ÷ 1e9。INT64_MAX (9223372036854775807) 表示未定义。MBO = 委托价；"
             "trades/tbbo = 成交价；mbp = 该事件价格；cbbo/bbo = 最近一笔成交价。",
    "size": "数量（股数／合约数）。MBO = 该事件的委托量；撤单 (C) 时是被撤销的数量。",
    "action": "事件类型：A 新增、C 撤单、M 修改、R 清空订单簿、T 成交、F 成交回报 (fill)、N 无。",
    "side": "B = 买方／bid、A = 卖方／ask、N = 无。成交 (T) 时表示主动方 (aggressor)：B = 主动买。",
    "flags": "位标志：128 LAST（同一事件的最后一条）、64 TOB（top-of-book 消息）、32 SNAPSHOT（来自快照）、"
             "16 MBP（由聚合价位合成）、8 BAD_TS_RECV、4 MAYBE_BAD_BOOK（可能有丢包）、2 PUBLISHER_SPECIFIC。",
    "depth": "此事件影响的订单簿深度档位（0 = 最优价）。",
    "order_id": "委托单 ID（交易所分配），同一张单的 A / M / C / F 共用此 ID。",
    "channel_id": "交易所 multicast 频道 ID。",
    "open": "K 线开盘价（定点 1e-9）。", "high": "K 线最高价。", "low": "K 线最低价。", "close": "K 线收盘价。",
    "volume": "K 线成交量。",
    "ts_ref": "统计值所指的参考时间（例如结算价对应的交易日）。",
    "quantity": "统计数量（例如持仓量、成交量），整数最大值表示未定义。",
    "stat_type": "统计类型：1 开盘价、3 结算价、4/5 盘中低/高、6 清算成交量、9 持仓量、11 收盘价…（见「格式说明」）。",
    "update_action": "1 = 新增、2 = 删除（撤回先前公布的统计）。",
    "stat_flags": "交易所自定义的统计标志。",
    "raw_symbol": "交易所原始代码，例如 OPRA 的 \"SPY   260116C00690000\"（root 补空格到 6 个字符 + YYMMDD + C/P + 行权价×1000 八位数）。",
    "expiration": "到期时间 (UNIX ns)。", "activation": "上市／开始交易时间 (UNIX ns)。",
    "strike_price": "行权价（定点 1e-9）。", "instrument_class": "品种类别：C 看涨期权、P 看跌期权、F 期货、K 股票、S 期货价差…",
    "underlying": "标的代码。", "underlying_id": "标的的 instrument_id。",
    "min_price_increment": "最小变动价位 (tick size，定点 1e-9)。",
    "contract_multiplier": "合约乘数（例如美股期权 100）。", "display_factor": "显示价格的乘数（定点 1e-9）。",
    "unit_of_measure_qty": "合约单位数量（定点 1e-9）。", "security_type": "证券类型，例如 OOF、FUT、OPT。",
    "asset": "资产代码。", "currency": "计价币种。", "exchange": "交易所 MIC。",
    "high_limit_price": "涨停价。", "low_limit_price": "跌停价。",
    "stype_in_symbol": "订阅时使用的代码（输入 symbology）。", "stype_out_symbol": "对应的输出代码（通常是 raw symbol）。",
    "start_ts": "此 mapping 生效开始时间。", "end_ts": "此 mapping 生效结束时间。",
    "msg": "系统消息文本（heartbeat、订阅确认…）。", "err": "错误消息文本。", "code": "消息代码。",
    "is_last": "是否为最后一条错误消息。",
    "is_trading": "是否可交易：Y / N / ~（未知）。", "is_quoting": "是否可报价：Y / N / ~。",
    "is_short_sell_restricted": "是否限制卖空：Y / N / ~。",
    "reason": "状态变更原因代码。", "trading_event": "附加交易事件代码。",
    "ref_price": "集合竞价参考价。", "paired_qty": "已配对数量。", "total_imbalance_qty": "总不平衡量。",
    "auction_type": "竞价类型。",
    "_rec": "（viewer 添加）此条记录在文件中的序号，从 0 起算。",
    "symbol": "（viewer 添加）由 instrument_id 经 metadata mappings 查到的代码。",
}

LEVEL = {
    "best": "最优（第 1 档）",
    "nth": "第 {n} 档",
    "bid": "买",
    "ask": "卖",
    "px": "{lvl}{side}价（定点 1e-9；未定义 = INT64_MAX）。",
    "sz": "{lvl}{side}方总量。",
    "ct": "{lvl}{side}方的委托笔数。",
    "pb": "{lvl}{side}价来自哪个交易所（publisher_id）。合并数据中用来看 NBBO 由谁提供。",
}

RESERVED = "保留／对齐用的填充字节，没有数据。"

SCHEMA_DOC = {
    "mbo": "逐笔委托 (Market by Order, L3)：每张委托单的新增／修改／撤单／成交事件各一条，可完整重建订单簿。",
    "mbp-1": "最优一档 (L1)：每个改变最优买卖价或产生成交的事件一条，附带事件「之后」的最优买卖价量。",
    "mbp-10": "前 10 档 (L2)：每个订单簿变动事件一条，附带事件之后的 10 档买卖价量与委托笔数。",
    "tbbo": "成交 + 成交「之前」的最优买卖 (trades with BBO)：每笔成交一行。",
    "trades": "逐笔成交：每笔成交一行。",
    "ohlcv-1s": "每秒 K 线；只有该区间有成交才有记录，ts_event 是区间开始时间。",
    "ohlcv-1m": "每分钟 K 线；只有该区间有成交才有记录，ts_event 是区间开始时间。",
    "ohlcv-1h": "每小时 K 线。", "ohlcv-1d": "日 K 线（UTC 日界）。", "ohlcv-eod": "以交易所收盘为界的日 K 线。",
    "definition": "品种定义：到期日、行权价、乘数、tick size、标的…（很适合用来解析 OPRA 期权的合约规格）。",
    "statistics": "交易所公布的统计：开／收盘价、结算价、持仓量、成交量…，看 stat_type 区分。",
    "status": "交易状态变化：暂停、恢复、开盘、收盘、卖空限制等。", "imbalance": "集合竞价的买卖不平衡信息。",
    "cmbp-1": "跨交易所合并的 L1 (consolidated MBP-1)：任一交易所报价变动就一条，附带合并后的 NBBO，"
              "以及提供最优价的交易所 (bid_pb / ask_pb)。数据量非常大。",
    "cbbo-1s": "每秒采样的合并 NBBO：只有该秒有报价更新的品种才有记录（需要 forward-fill）。"
               "price / size / ts_event 是最近一笔成交，可能是很久以前的。",
    "cbbo-1m": "每分钟采样的合并 NBBO：只有该分钟有报价更新的品种才有记录（需要 forward-fill）。"
               "price / size / ts_event 是最近一笔成交，可能是很久以前的，没成交过就是未定义。",
    "tcbbo": "成交 + 成交之前的合并 NBBO：每笔成交一行。",
    "bbo-1s": "单一交易所的 L1 每秒采样。", "bbo-1m": "单一交易所的 L1 每分钟采样。",
}

STYPE_DOC = {
    "instrument_id": "数字 instrument_id",
    "raw_symbol": "交易所原始代码（例如 ESH4、SPY   260116C00690000）",
    "parent": "母代码：一个代码展开成整串合约，例如 QQQ.OPT = QQQ 全部期权、ES.FUT = ES 全部期货",
    "continuous": "连续合约，例如 ES.v.0 = 按成交量排名第一的 ES 期货、ES.c.0 = 按日历最近月",
    "nasdaq_symbol": "Nasdaq 代码", "cms_symbol": "CMS 代码", "isin": "ISIN", "us_code": "CUSIP", "figi": "FIGI",
}

ENUMS = [
    ("action", [("A", "Add 新增委托／报价"), ("C", "Cancel 撤单（部分或全部）"), ("M", "Modify 修改价格或数量"),
                ("R", "Clear 清空订单簿（常见于快照开头）"), ("T", "Trade 成交（主动方）"), ("F", "Fill 被动方成交回报"),
                ("N", "None 无动作（例如只更新 flags）")]),
    ("side", [("B", "Bid 买方"), ("A", "Ask 卖方"), ("N", "None（例如没有方向的成交、采样记录）")]),
    ("flags（位）", [("128", "LAST：同一个交易所事件拆成多条时，只有最后一条才设置；重建订单簿时应在 LAST 之后才读取状态"),
                   ("64", "TOB：top-of-book 消息（该价位整档替换）"), ("32", "SNAPSHOT：来自快照／重放"),
                   ("16", "MBP：由聚合价位数据合成"), ("8", "BAD_TS_RECV：ts_recv 不准确"),
                   ("4", "MAYBE_BAD_BOOK：可能有丢包，订单簿可能有误"), ("2", "PUBLISHER_SPECIFIC：交易所自定义")]),
    ("stat_type", [("1", "开盘价"), ("2", "指示性开盘价"), ("3", "结算价"), ("4", "盘中最低价"), ("5", "盘中最高价"),
                   ("6", "清算成交量"), ("7", "最低卖价"), ("8", "最高买价"), ("9", "持仓量 (open interest)"),
                   ("10", "定盘价 (fixing)"), ("11", "收盘价"), ("12", "涨跌"), ("13", "VWAP"), ("14", "波动率"),
                   ("15", "Delta")]),
    ("未定义值 (sentinel)", [("INT64_MAX", "价格未定义 9223372036854775807（显示为 —）"),
                          ("UINT64_MAX", "时间戳未定义 18446744073709551615"),
                          ("UINT32_MAX", "数量未定义 4294967295")]),
]

TIPS = [
    "价格一律是整数 ÷ 1e9；9223372036854775807 代表「没有值」，不能直接当价格计算。",
    "时间都是 UTC 纳秒；美股盘中 09:30–16:00 ET = 14:30–21:00 UTC（夏令时 13:30–20:00）。工具栏可切换时区。",
    "ts_recv 是文件排序用的时间；ts_event 是交易所时间，可能乱序或未定义。",
    "MBO 的 T／F 不改变订单簿，真正减量的是后续的 C／M；重建订单簿要等 flags 含 LAST 才算一个完整事件。",
    "OPRA 的 instrument_id 可能每天不同，跨日要用 symbol 对齐，不要用 id。",
    "-1s / -1m 采样 schema 只在有更新时出现，要自己 forward-fill；price/size 是「最近一次成交」，不是该区间的成交。",
    "DBN v1 → v2 → v3：symbol 长度 22 → 71；InstrumentDef 360 → 400 → 520 bytes；StatMsg 的 quantity 在 v3 由 i32 "
    "改成 i64（64 → 80 bytes）。这个 viewer 根据文件头版本自动切换。",
    ".zst 是整条流压缩，不能随机跳到中间；看文件后段要从头解码（可用时间筛选，只保留需要的行）。",
]


# --- added after the docs audit: remaining stat_type codes and the corrected statistics sentinel
def _patch():
    extra = ['集合竞价撮合价（非正式开/收盘）', '涨停价（盘中上限）', '跌停价（盘中下限）', '大宗交易量', '指示性收盘价', '熔断第 1 级阈值 (7%)', '熔断第 2 级阈值 (13%)', '熔断第 3 级阈值 (20%)', '竞价区间参考价', '竞价区间上限', '竞价区间下限', '交易所自定义成交量 1', '交易所自定义价格 1']
    for title, rows in ENUMS:
        codes = [c for c, _ in rows]
        if "15" in codes and "16" not in codes:
            rows.extend((str(c), d) for c, d in zip([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 10001, 10002], extra))
        if "UINT32_MAX" in codes:
            i = codes.index("UINT32_MAX")
            rows[i] = ('INT32_MAX / INT64_MAX', 'statistics 的 quantity 未定义（v1/v2 为 INT32_MAX，v3 为 INT64_MAX）')


_patch()
