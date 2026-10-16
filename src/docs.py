"""Documentation of DBN fields, schemas and enums, localized (see locales/)."""
import importlib
import re

RTYPE_DOC = [(0x00, "trade / mbp-0"), (0x01, "mbp-1 / tbbo"), (0x0A, "mbp-10"), (0x12, "status"),
             (0x13, "definition"), (0x14, "imbalance"), (0x15, "error"), (0x16, "symbol mapping"),
             (0x17, "system"), (0x18, "statistics"), (0x20, "ohlcv-1s"), (0x21, "ohlcv-1m"), (0x22, "ohlcv-1h"),
             (0x23, "ohlcv-1d"), (0x24, "ohlcv-eod"), (0xA0, "mbo"), (0xB1, "cmbp-1"), (0xC0, "cbbo-1s"),
             (0xC1, "cbbo-1m"), (0xC2, "tcbbo"), (0xC3, "bbo-1s"), (0xC4, "bbo-1m")]

FLAGS = [(128, "LAST", "L"), (64, "TOB", "T"), (32, "SNAPSHOT", "S"), (16, "MBP", "M"),
         (8, "BAD_TS_RECV", "!t"), (4, "MAYBE_BAD_BOOK", "!b"), (2, "PUBLISHER_SPECIFIC", "P")]

_L = None


def set_lang(code):
    global _L
    try:
        _L = importlib.import_module("locales." + code)
    except ImportError:
        _L = importlib.import_module("locales.en")


def _loc():
    if _L is None:
        set_lang("zh_Hant")
    return _L


def field_doc(name):
    L = _loc()
    if name in L.FIELD_DOC:
        return L.FIELD_DOC[name]
    m = re.match(r"^(bid|ask)_(px|sz|ct|pb)_(\d\d)$", name)
    if m:
        lv = int(m.group(3))
        lvl = L.LEVEL["best"] if lv == 0 else L.LEVEL["nth"].format(n=lv + 1)
        return L.LEVEL[m.group(2)].format(lvl=lvl, side=L.LEVEL[m.group(1)])
    if re.match(r"^_reserved|^_dummy|padding", name):
        return L.RESERVED
    return ""


def schema_doc(schema, default=""):
    return _loc().SCHEMA_DOC.get(schema, default)


def stype_doc(stype):
    return _loc().STYPE_DOC.get(stype, "")


def enums():
    return _loc().ENUMS


def tips():
    return _loc().TIPS


def flag_names(f):
    return " | ".join(n for b, n, _ in FLAGS if f & b) or "0"


def flag_short(f):
    return "".join(s for b, _, s in FLAGS if f & b)
