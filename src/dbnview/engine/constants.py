"""DBN constants, record-type table and the embedded record layouts (spec.json)."""
import json
from importlib import resources

import numpy as np

SPEC = json.loads(resources.files("dbnview.engine").joinpath("spec.json").read_text(encoding="utf-8"))
PUBLISHERS = {int(k): v for k, v in SPEC["pubs"].items()}


UNDEF_PRICE = np.iinfo(np.int64).max


UNDEF_TS = np.iinfo(np.uint64).max


UNDEF_U32 = np.iinfo(np.uint32).max


PRICE_SCALE = 1e9


SCHEMAS = ["mbo", "mbp-1", "mbp-10", "tbbo", "trades", "ohlcv-1s", "ohlcv-1m", "ohlcv-1h",
           "ohlcv-1d", "definition", "statistics", "status", "imbalance", "ohlcv-eod",
           "cmbp-1", "cbbo-1s", "cbbo-1m", "tcbbo", "bbo-1s", "bbo-1m"]


STYPES = ["instrument_id", "raw_symbol", "smart", "continuous", "parent", "nasdaq_symbol",
          "cms_symbol", "isin", "us_code", "bbg_comp_id", "bbg_comp_ticker", "figi", "figi_ticker"]


RTYPES = {  # rtype -> (record class in spec, display name)
    0x00: ("TradeMsg", "trade"),
    0x01: ("MBP1Msg", "mbp-1"),
    0x0A: ("MBP10Msg", "mbp-10"),
    0x11: ("OHLCVMsg", "ohlcv"),
    0x12: ("StatusMsg", "status"),
    0x13: ("InstrumentDefMsg", "definition"),
    0x14: ("ImbalanceMsg", "imbalance"),
    0x15: ("ErrorMsg", "error"),
    0x16: ("SymbolMappingMsg", "symbol-mapping"),
    0x17: ("SystemMsg", "system"),
    0x18: ("StatMsg", "statistics"),
    0x20: ("OHLCVMsg", "ohlcv-1s"),
    0x21: ("OHLCVMsg", "ohlcv-1m"),
    0x22: ("OHLCVMsg", "ohlcv-1h"),
    0x23: ("OHLCVMsg", "ohlcv-1d"),
    0x24: ("OHLCVMsg", "ohlcv-eod"),
    0xA0: ("MBOMsg", "mbo"),
    0xB1: ("CMBP1Msg", "cmbp-1"),
    0xC0: ("CBBO1SMsg", "cbbo-1s"),
    0xC1: ("CBBO1MMsg", "cbbo-1m"),
    0xC2: ("TCBBOMsg", "tcbbo"),
    0xC3: ("BBO1SMsg", "bbo-1s"),
    0xC4: ("BBO1MMsg", "bbo-1m"),
}


HEADER_FIELDS = [["length", "u1"], ["rtype", "u1"], ["publisher_id", "u2"],
                 ["instrument_id", "u4"], ["ts_event", "u8"]]


FLAG_BITS = [(128, "LAST"), (64, "TOB"), (32, "SNAPSHOT"), (16, "MBP"),
             (8, "BAD_TS_RECV"), (4, "MAYBE_BAD_BOOK"), (2, "PUBLISHER_SPECIFIC")]


NULL_MAX_CLASSES = {"InstrumentDefMsg", "StatMsg", "ErrorMsg", "SystemMsg", "StatusMsg", "ImbalanceMsg"}

