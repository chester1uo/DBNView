import ast
import pathlib
import re

import pytest

from dbnview import i18n, reference
from dbnview.i18n.strings import STRINGS

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "dbnview"
LANGS = [c for c, _ in i18n.LANGS]
PH = re.compile(r"%(?:\.\d+)?[sdfx%]|%0\dx")


def literal_keys():
    for f in SRC.rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "T" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                yield f.name, n.args[0].value


def test_every_ui_string_is_translated():
    missing = [(f, k) for f, k in literal_keys() if k not in STRINGS]
    assert not missing, missing


@pytest.mark.parametrize("key", sorted(STRINGS))
def test_translation_complete_and_placeholders_match(key):
    entry = STRINGS[key]
    assert set(entry) == set(LANGS)
    for lang, text in entry.items():
        assert text, (key, lang)
        assert PH.findall(text) == PH.findall(key), (key, lang)
        assert set(re.findall(r"\{\w+\}", text)) == set(re.findall(r"\{\w+\}", key)), (key, lang)


@pytest.mark.parametrize("lang", LANGS)
def test_reference_locales_share_keys(lang):
    reference.set_lang("zh_Hant")
    base = (set(reference._loc().FIELD_DOC), set(reference._loc().SCHEMA_DOC), [len(r) for _, r in reference.enums()])
    reference.set_lang(lang)
    loc = reference._loc()
    assert (set(loc.FIELD_DOC), set(loc.SCHEMA_DOC), [len(r) for _, r in reference.enums()]) == base
    assert reference.field_doc("ask_ct_03")
    assert len(reference.tips()) == len(reference._loc().TIPS)


def test_switching_language():
    i18n.set_lang("en")
    assert i18n.T("掃描") == "Scan"
    i18n.set_lang("ja")
    assert i18n.T("掃描") == "スキャン"
    i18n.set_lang("zh_Hant")
