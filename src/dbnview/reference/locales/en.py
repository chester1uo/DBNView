"""English documentation strings for dbnview."""

FIELD_DOC = {
    "length": "Record length in units of 4 bytes (actual bytes = length × 4). The decoder uses it to skip to the next record.",
    "rtype": "Record type; determines the layout of the fields that follow, e.g. 0xA0 = MBO, 0xB1 = CMBP-1.",
    "publisher_id": "Data source ID = dataset + venue, e.g. 30 = OPRA.PILLAR.OPRA, 1 = GLBX.MDP3.GLBX.",
    "instrument_id": "Numeric instrument ID assigned by the venue/Databento. Mapping it back to a symbol requires the "
                     "symbology mappings in the metadata (date-dependent).",
    "ts_event": "Event time at the venue's matching engine, UNIX epoch nanoseconds (UTC). In the cbbo/bbo sampled schemas "
                "it is the time of the most recent trade, undefined if there has been no trade; in ohlcv it is the bar "
                "start time.",
    "ts_recv": "Time the Databento capture server received the message, UNIX epoch nanoseconds (UTC). This is Databento's "
               "primary index timestamp; files are sorted by it. In the -1s / -1m sampled schemas it is the sampling "
               "time aligned to the second/minute.",
    "ts_in_delta": "How many nanoseconds the venue's send time precedes ts_recv (ts_recv − venue sending time).",
    "ts_out": "Databento gateway send time (appended as the last 8 bytes of each record only for live data with ts_out "
              "enabled).",
    "sequence": "Venue message sequence number; can be used to detect dropped packets.",
    "price": "Price, fixed-point: actual value = integer ÷ 1e9. INT64_MAX (9223372036854775807) means undefined. "
             "MBO = order price; trades/tbbo = trade price; mbp = price of the event; cbbo/bbo = most recent trade price.",
    "size": "Quantity (shares/contracts). MBO = order quantity of the event; for a cancel (C) it is the canceled quantity.",
    "action": "Event type: A add, C cancel, M modify, R clear book, T trade, F fill, N none.",
    "side": "B = buy/bid, A = sell/ask, N = none. For a trade (T) it indicates the aggressor: B = aggressive buy.",
    "flags": "Bit flags: 128 LAST (last record of the same event), 64 TOB (top-of-book message), 32 SNAPSHOT (from a "
             "snapshot), 16 MBP (synthesized from aggregated price levels), 8 BAD_TS_RECV, 4 MAYBE_BAD_BOOK (possible "
             "packet loss), 2 PUBLISHER_SPECIFIC.",
    "depth": "Book depth level affected by this event (0 = best price).",
    "order_id": "Order ID (assigned by the venue); the A / M / C / F events of the same order share this ID.",
    "channel_id": "Venue multicast channel ID.",
    "open": "Bar open price (fixed-point 1e-9).", "high": "Bar high price.", "low": "Bar low price.",
    "close": "Bar close price.",
    "volume": "Bar volume.",
    "ts_ref": "Reference time the statistic refers to (e.g. the trading date of a settlement price).",
    "quantity": "Statistic quantity (e.g. open interest, volume); the maximum integer value means undefined.",
    "stat_type": "Statistic type: 1 open, 3 settlement, 4/5 session low/high, 6 cleared volume, 9 open interest, "
                 "11 close… (see \"Format notes\").",
    "update_action": "1 = add, 2 = delete (retracts a previously published statistic).",
    "stat_flags": "Venue-specific statistic flags.",
    "raw_symbol": "Raw venue symbol, e.g. OPRA \"SPY   260116C00690000\" (root space-padded to 6 characters + YYMMDD "
                  "+ C/P + strike×1000 as 8 digits).",
    "expiration": "Expiration time (UNIX ns).", "activation": "Listing/trading start time (UNIX ns).",
    "strike_price": "Strike price (fixed-point 1e-9).",
    "instrument_class": "Instrument class: C call, P put, F future, K stock, S future spread…",
    "underlying": "Underlying symbol.", "underlying_id": "instrument_id of the underlying.",
    "min_price_increment": "Minimum price increment (tick size, fixed-point 1e-9).",
    "contract_multiplier": "Contract multiplier (e.g. 100 for US equity options).",
    "display_factor": "Multiplier for displayed prices (fixed-point 1e-9).",
    "unit_of_measure_qty": "Contract unit-of-measure quantity (fixed-point 1e-9).",
    "security_type": "Security type, e.g. OOF, FUT, OPT.",
    "asset": "Asset code.", "currency": "Quote currency.", "exchange": "Exchange MIC.",
    "high_limit_price": "Upper price limit (limit up).", "low_limit_price": "Lower price limit (limit down).",
    "stype_in_symbol": "Symbol used when subscribing (input symbology).",
    "stype_out_symbol": "Corresponding output symbol (usually the raw symbol).",
    "start_ts": "Start of the period this mapping is in effect.", "end_ts": "End of the period this mapping is in effect.",
    "msg": "System message text (heartbeat, subscription acknowledgement…).", "err": "Error message text.",
    "code": "Message code.",
    "is_last": "Whether this is the last error message.",
    "is_trading": "Whether trading is allowed: Y / N / ~ (unknown).", "is_quoting": "Whether quoting is allowed: Y / N / ~.",
    "is_short_sell_restricted": "Whether short selling is restricted: Y / N / ~.",
    "reason": "Status change reason code.", "trading_event": "Additional trading event code.",
    "ref_price": "Auction reference price.", "paired_qty": "Paired quantity.",
    "total_imbalance_qty": "Total imbalance quantity.",
    "auction_type": "Auction type.",
    "_rec": "(Added by the viewer) Index of this record in the file, starting from 0.",
    "symbol": "(Added by the viewer) Symbol resolved from instrument_id via the metadata mappings.",
}

LEVEL = {
    "best": "Best (level 1)",
    "nth": "Level {n}",
    "bid": "bid",
    "ask": "ask",
    "px": "{lvl} {side} price (fixed-point 1e-9; undefined = INT64_MAX).",
    "sz": "{lvl} {side} total size.",
    "ct": "{lvl} {side} order count.",
    "pb": "{lvl} {side} price source: venue (publisher_id). In consolidated data, shows who is setting the NBBO.",
}

RESERVED = "Reserved/alignment padding bytes; no data."

SCHEMA_DOC = {
    "mbo": "Market by Order (L3): one record per add/modify/cancel/fill event of each order; allows full order book "
           "reconstruction.",
    "mbp-1": "Top of book (L1): one record per event that changes the best bid/ask or produces a trade, with the best "
             "bid/ask prices and sizes after the event.",
    "mbp-10": "Top 10 levels (L2): one record per book-changing event, with the prices, sizes and order counts of the "
              "10 bid/ask levels after the event.",
    "tbbo": "Trades + the best bid/ask before the trade (trades with BBO): one row per trade.",
    "trades": "Tick-by-tick trades: one row per trade.",
    "ohlcv-1s": "1-second bars; a record exists only if the interval had trades; ts_event is the interval start time.",
    "ohlcv-1m": "1-minute bars; a record exists only if the interval had trades; ts_event is the interval start time.",
    "ohlcv-1h": "1-hour bars.", "ohlcv-1d": "Daily bars (UTC day boundaries).",
    "ohlcv-eod": "Daily bars bounded by the venue's close.",
    "definition": "Instrument definitions: expiration, strike, multiplier, tick size, underlying… (well suited to "
                  "parsing OPRA option contract specifications).",
    "statistics": "Venue-published statistics: open/close price, settlement price, open interest, volume…; "
                  "distinguish them by stat_type.",
    "status": "Trading status changes: halts, resumptions, open, close, short-sale restrictions, etc.",
    "imbalance": "Auction buy/sell imbalance information.",
    "cmbp-1": "Consolidated L1 across venues (consolidated MBP-1): one record whenever any venue's quote changes, with "
              "the consolidated NBBO and the venues providing the best prices (bid_pb / ask_pb). Very large data volume.",
    "cbbo-1s": "Consolidated NBBO sampled every second: only instruments with a quote update in that second get a "
               "record (forward-fill required). price / size / ts_event are the most recent trade, which may be long ago.",
    "cbbo-1m": "Consolidated NBBO sampled every minute: only instruments with a quote update in that minute get a "
               "record (forward-fill required). price / size / ts_event are the most recent trade, which may be long "
               "ago; undefined if there has never been a trade.",
    "tcbbo": "Trades + the consolidated NBBO before the trade: one row per trade.",
    "bbo-1s": "Single-venue L1 sampled every second.", "bbo-1m": "Single-venue L1 sampled every minute.",
}

STYPE_DOC = {
    "instrument_id": "Numeric instrument_id",
    "raw_symbol": "Raw venue symbol (e.g. ESH4, SPY   260116C00690000)",
    "parent": "Parent symbol: one symbol expands to a whole set of contracts, e.g. QQQ.OPT = all QQQ options, "
              "ES.FUT = all ES futures",
    "continuous": "Continuous contract, e.g. ES.v.0 = the ES future ranked first by volume, ES.c.0 = nearest by calendar",
    "nasdaq_symbol": "Nasdaq symbol", "cms_symbol": "CMS symbol", "isin": "ISIN", "us_code": "CUSIP", "figi": "FIGI",
}

ENUMS = [
    ("action", [("A", "Add: new order/quote"), ("C", "Cancel: partial or full"), ("M", "Modify: price or size"),
                ("R", "Clear: clear the order book (common at the start of a snapshot)"),
                ("T", "Trade: trade (aggressor side)"), ("F", "Fill: passive-side fill report"),
                ("N", "None: no action (e.g. only flags updated)")]),
    ("side", [("B", "Bid: buy side"), ("A", "Ask: sell side"), ("N", "None (e.g. trades without a side, sampled records)")]),
    ("flags (bits)", [("128", "LAST: when one venue event is split into several records, only the last one has it set; "
                              "when rebuilding the book, read the state only after LAST"),
                      ("64", "TOB: top-of-book message (replaces the whole price level)"),
                      ("32", "SNAPSHOT: from a snapshot/replay"),
                      ("16", "MBP: synthesized from aggregated price-level data"),
                      ("8", "BAD_TS_RECV: ts_recv is inaccurate"),
                      ("4", "MAYBE_BAD_BOOK: possible packet loss; the book may be wrong"),
                      ("2", "PUBLISHER_SPECIFIC: venue-specific")]),
    ("stat_type", [("1", "Opening price"), ("2", "Indicative opening price"), ("3", "Settlement price"),
                   ("4", "Session low"), ("5", "Session high"), ("6", "Cleared volume"), ("7", "Lowest offer"),
                   ("8", "Highest bid"), ("9", "Open interest"), ("10", "Fixing price"), ("11", "Closing price"),
                   ("12", "Net change"), ("13", "VWAP"), ("14", "Volatility"), ("15", "Delta")]),
    ("Undefined values (sentinels)", [("INT64_MAX", "Undefined price 9223372036854775807 (shown as —)"),
                                      ("UINT64_MAX", "Undefined timestamp 18446744073709551615"),
                                      ("UINT32_MAX", "Undefined quantity 4294967295")]),
]

TIPS = [
    "Prices are always integer ÷ 1e9; 9223372036854775807 means \"no value\" and must not be used as a price directly.",
    "All times are UTC nanoseconds; US regular trading hours 09:30–16:00 ET = 14:30–21:00 UTC (13:30–20:00 during "
    "daylight saving time). The time zone can be switched in the toolbar.",
    "ts_recv is the time the file is sorted by; ts_event is venue time and may be out of order or undefined.",
    "In MBO, T/F do not change the order book; the actual size reduction comes from the subsequent C/M. When rebuilding "
    "the book, an event is complete only once flags include LAST.",
    "OPRA instrument_id values may differ from day to day; align across days by symbol, not by id.",
    "The -1s / -1m sampled schemas only emit a record when there is an update, so you must forward-fill yourself; "
    "price/size are the \"most recent trade\", not trades within that interval.",
    "DBN v1 → v2 → v3: symbol length 22 → 71; InstrumentDef 360 → 400 → 520 bytes; StatMsg quantity changed from i32 "
    "to i64 in v3 (64 → 80 bytes). This viewer switches automatically based on the header version.",
    ".zst compresses the entire stream, so you cannot jump to the middle at random; viewing the later part of a file "
    "requires decoding from the start (use the time filter to keep only the rows you need).",
]


# --- added after the docs audit: remaining stat_type codes and the corrected statistics sentinel
def _patch():
    extra = ['Uncrossing price (auctions other than official open/close)', 'Upper price limit', 'Lower price limit', 'Block volume', 'Indicative close price', 'MWCB level 1 threshold (7%)', 'MWCB level 2 threshold (13%)', 'MWCB level 3 threshold (20%)', 'Auction collar reference price', 'Auction collar upper price', 'Auction collar lower price', 'Venue-specific volume 1', 'Venue-specific price 1']
    for title, rows in ENUMS:
        codes = [c for c, _ in rows]
        if "15" in codes and "16" not in codes:
            rows.extend((str(c), d) for c, d in zip([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 10001, 10002], extra))
        if "UINT32_MAX" in codes:
            i = codes.index("UINT32_MAX")
            rows[i] = ('INT32_MAX / INT64_MAX', 'statistics quantity undefined (INT32_MAX in v1/v2, INT64_MAX in v3)')


_patch()
