"""UI string translation.

`T(key)` returns the text for the current language. Keys are the English text; translations live in `strings.py`
as {key: {lang: text}}. A key "context|Text" separates words that read the same in English but translate
differently ("price|Open" vs "Open"); English shows "Text". When adding a UI string, wrap it in T(...) and add an
entry with the 6 other languages — tests/test_i18n.py fails otherwise.
"""
import locale
import os

LANGS = [("zh_Hant", "繁體中文"), ("zh_Hans", "简体中文"), ("en", "English"), ("ja", "日本語"),
         ("de", "Deutsch"), ("ko", "한국어"), ("es", "Español")]
_lang = "zh_Hant"

from .strings import STRINGS


def system_lang():
    """Best guess from the OS locale (macOS AppleLanguages first)."""
    cands = []
    try:
        from PySide6.QtCore import QLocale
        cands += list(QLocale.system().uiLanguages())
    except Exception:  # noqa: BLE001
        pass
    cands += [os.environ.get("LANG", ""), (locale.getlocale()[0] or "")]
    for c in cands:
        c = c.replace("-", "_")
        lc = c.lower()
        if lc.startswith("zh"):
            if "hant" in lc or lc.endswith(("_tw", "_hk", "_mo")):
                return "zh_Hant"
            return "zh_Hans"
        for code in ("en", "ja", "de", "ko", "es"):
            if lc.startswith(code):
                return code
    return "en"


def set_lang(code):
    global _lang
    _lang = code if code in dict(LANGS) else "en"


def get_lang():
    return _lang


def T(key):
    d = STRINGS.get(key) or {}
    return d.get(_lang) or d.get("en") or key.rpartition("|")[2]
